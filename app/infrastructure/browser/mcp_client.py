"""Client MCP tối giản cho `chrome-devtools-mcp` (stdio JSON-RPC 2.0).

Vì sao cần lớp này: `chrome-devtools-mcp` là MCP server viết bằng Node, không phải
thư viện Python. Nó không tạo Chrome mới mà **gắn vào Chrome đang chạy** qua
`--browser-url`, nên app tự mở Chrome riêng cho từng tài khoản rồi trỏ MCP vào
đúng cổng remote-debugging của tài khoản đó.

Dùng cho: dò selector (`take_snapshot`), chụp ảnh xác nhận, đọc console/network
khi trang đổi layout, và `evaluate_script` để kiểm tra nhanh DOM. Luồng chạy hàng
loạt thì dùng Playwright trực tiếp (xem `browser_session.py`) vì uid của snapshot
đổi sau mỗi lần chụp, không hợp để replay cứng.

Giao thức: mỗi message JSON-RPC là **một dòng** JSON trên stdin/stdout của process
con; handshake gồm `initialize` rồi notification `notifications/initialized`.
"""
import json
import os
import queue
import shutil
import subprocess
import threading

from app.config import CHROME_DEVTOOLS_MCP_JS, CHROME_DEVTOOLS_MCP_NPM_PACKAGE

PROTOCOL_VERSION = "2024-11-05"
CLIENT_INFO = {"name": "namco-account-manager", "version": "1.0"}
DEFAULT_TIMEOUT = 90.0
# Tắt thống kê/telemetry và kiểm tra cập nhật của server: app chạy offline-friendly.
BASE_ARGS = ("--no-usage-statistics", "--no-performance-crux")


class McpError(Exception):
    """Không khởi động được server MCP hoặc tool trả lỗi."""


def _candidate_js_paths():
    """Các vị trí cài đặt phổ biến của server MCP (npm global trên Windows)."""
    appdata = os.environ.get("APPDATA", "")
    relative = os.path.join("node_modules", CHROME_DEVTOOLS_MCP_NPM_PACKAGE, "out",
                            "Default", "gen", "src", "bin", "chrome-devtools-mcp.js")
    candidates = []
    if CHROME_DEVTOOLS_MCP_JS:
        candidates.append(CHROME_DEVTOOLS_MCP_JS)
    if appdata:
        candidates.append(os.path.join(appdata, "npm", relative))
        candidates.append(os.path.join(appdata, "npm", "node_modules",
                                       CHROME_DEVTOOLS_MCP_NPM_PACKAGE, "build", "src",
                                       "bin", "chrome-devtools-mcp.js"))
    program_files = os.environ.get("ProgramFiles", r"C:\Program Files")
    candidates.append(os.path.join(program_files, "nodejs", relative))
    return candidates


def resolve_command():
    """Trả (argv, mô tả) để chạy server MCP, hoặc raise McpError nếu không tìm thấy."""
    for path in _candidate_js_paths():
        if path and os.path.isfile(path):
            node = shutil.which("node") or shutil.which("node.exe")
            if not node:
                raise McpError("Có server MCP nhưng không tìm thấy node.exe trong PATH")
            return [node, path], path
    appdata = os.environ.get("APPDATA", "")
    shim = os.path.join(appdata, "npm", CHROME_DEVTOOLS_MCP_NPM_PACKAGE + ".cmd") if appdata else ""
    if shim and os.path.isfile(shim):
        return [shim], shim
    npx = shutil.which("npx") or shutil.which("npx.cmd")
    if npx:
        return [npx, "-y", CHROME_DEVTOOLS_MCP_NPM_PACKAGE + "@latest"], npx
    raise McpError("Chưa cài chrome-devtools-mcp. Chạy: npm i -g chrome-devtools-mcp")


class DevtoolsMcpClient:
    """Một process MCP gắn vào một Chrome (theo `cdp_url`)."""

    def __init__(self, cdp_url=None, extra_args=(), timeout=DEFAULT_TIMEOUT, on_log=None):
        self.cdp_url = cdp_url or ""
        self.extra_args = tuple(extra_args)
        self.timeout = timeout
        self.on_log = on_log or (lambda message: None)
        self._process = None
        self._messages = queue.Queue()
        self._reader = None
        self._stderr = []
        self._next_id = 0
        self._tool_names = []

    # ---------------- vòng đời ----------------
    def start(self):
        argv, source = resolve_command()
        args = list(argv) + list(BASE_ARGS) + list(self.extra_args)
        if self.cdp_url:
            args.append("--browser-url=%s" % self.cdp_url)
        creation_flags = 0
        if os.name == "nt":
            creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        self.on_log("MCP: khởi động %s" % source)
        try:
            self._process = subprocess.Popen(
                args,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                creationflags=creation_flags,
            )
        except OSError as exc:
            raise McpError("Không chạy được server MCP (%s): %s" % (source, exc)) from exc
        self._reader = threading.Thread(target=self._read_stdout, name="mcp-reader", daemon=True)
        self._reader.start()
        threading.Thread(target=self._read_stderr, name="mcp-stderr", daemon=True).start()
        self._initialize()
        return self

    def close(self):
        process, self._process = self._process, None
        if not process:
            return
        try:
            if process.stdin:
                process.stdin.close()
        except OSError:
            pass
        try:
            process.terminate()
            process.wait(timeout=5)
        except Exception:  # noqa: BLE001 - dọn dẹp, không được ném lỗi
            try:
                process.kill()
            except OSError:
                pass

    def __enter__(self):
        return self.start()

    def __exit__(self, *exc_info):
        self.close()
        return False

    # ---------------- I/O ----------------
    def _read_stdout(self):
        process = self._process
        if not process or not process.stdout:
            return
        for line in process.stdout:
            line = line.strip()
            if not line:
                continue
            try:
                self._messages.put(json.loads(line))
            except ValueError:
                self.on_log("MCP stdout không phải JSON: %s" % line[:200])
        self._messages.put(None)  # EOF

    def _read_stderr(self):
        process = self._process
        if not process or not process.stderr:
            return
        for line in process.stderr:
            line = line.rstrip()
            if not line:
                continue
            self._stderr.append(line)
            del self._stderr[:-20]

    def _send(self, payload):
        process = self._process
        if not process or not process.stdin:
            raise McpError("Server MCP chưa chạy")
        try:
            process.stdin.write(json.dumps(payload, ensure_ascii=False) + "\n")
            process.stdin.flush()
        except (OSError, ValueError) as exc:
            raise McpError("Không gửi được lệnh tới server MCP: %s" % exc) from exc

    def _notify(self, method, params=None):
        payload = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            payload["params"] = params
        self._send(payload)

    def _request(self, method, params=None, timeout=None):
        self._next_id += 1
        request_id = self._next_id
        payload = {"jsonrpc": "2.0", "id": request_id, "method": method}
        if params is not None:
            payload["params"] = params
        self._send(payload)
        deadline = timeout or self.timeout
        while True:
            try:
                message = self._messages.get(timeout=deadline)
            except queue.Empty:
                raise McpError("Server MCP không trả lời '%s' sau %.0fs" % (method, deadline))
            if message is None:
                tail = "\n".join(self._stderr[-5:])
                raise McpError("Server MCP đã thoát khi đang chờ '%s'. %s" % (method, tail))
            if message.get("id") != request_id:
                continue  # notification/log của server, bỏ qua
            if "error" in message:
                error = message["error"] or {}
                raise McpError("%s: %s" % (method, error.get("message") or error))
            return message.get("result") or {}

    def _initialize(self):
        result = self._request("initialize", {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {},
            "clientInfo": CLIENT_INFO,
        })
        self._notify("notifications/initialized")
        server = result.get("serverInfo") or {}
        self.on_log("MCP: %s %s sẵn sàng" % (server.get("name", "chrome-devtools-mcp"),
                                             server.get("version", "")))
        try:
            tools = self._request("tools/list").get("tools") or []
            self._tool_names = [tool.get("name") for tool in tools if tool.get("name")]
        except McpError:
            self._tool_names = []

    # ---------------- tool ----------------
    def has_tool(self, name):
        return not self._tool_names or name in self._tool_names

    def call_tool(self, name, arguments=None, timeout=None):
        """Gọi một tool, trả text của kết quả (content dạng text ghép lại)."""
        result = self._request("tools/call", {"name": name, "arguments": arguments or {}},
                               timeout=timeout)
        content = result.get("content") or []
        chunks = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                chunks.append(item.get("text") or "")
            elif isinstance(item, dict) and item.get("type") == "image":
                chunks.append("[image %s]" % (item.get("mimeType") or "image"))
        if result.get("isError"):
            raise McpError("%s lỗi: %s" % (name, "\n".join(chunks)[:500]))
        return "\n".join(chunks)

    def list_pages(self):
        return self.call_tool("list_pages")

    def snapshot(self, page_id=None, path=None, timeout=None):
        """Snapshot a11y của trang: danh sách phần tử kèm uid để dò selector."""
        arguments = {}
        if page_id is not None:
            arguments["pageId"] = page_id
        if path:
            arguments["filePath"] = path
        return self.call_tool("take_snapshot", arguments, timeout=timeout)

    def screenshot(self, page_id, path, full_page=True):
        return self.call_tool("take_screenshot", {
            "pageId": page_id, "filePath": path, "fullPage": full_page})

    def evaluate(self, function, page_id=1):
        """Chạy JS trong trang; MCP bắt buộc có pageId nên mặc định trang 1."""
        return self.call_tool("evaluate_script", {
            "function": function, "pageId": page_id, "waitForStableDom": False})

    def console_messages(self, page_id):
        return self.call_tool("list_console_messages", {"pageId": page_id})
