"""
Quản lý proxy cho toàn bộ request của ứng dụng.

Định dạng mỗi dòng trong proxy.txt:
    ip:port:username:pass

Các định dạng cũng được chấp nhận:
    ip:port                          (proxy không cần tài khoản)
    username:pass@ip:port
    http://ip:port:username:pass     (hoặc https://, socks4://, socks5://)

Khi proxy được bật, mỗi request sẽ lấy một proxy theo cấu hình:
    - MODE_PER_REQUEST : luân phiên theo từng request
    - MODE_PER_SESSION : mỗi session (mỗi tài khoản) dùng đúng một proxy
"""
import os
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import quote

import requests

APP_DIR = os.path.dirname(os.path.abspath(__file__))
PROXY_FILE = os.path.join(APP_DIR, "proxy.txt")

MODE_PER_REQUEST = "per_request"
MODE_PER_SESSION = "per_session"

# Trang dùng để thử proxy: chính là trang đăng nhập của ứng dụng.
TEST_URL = "https://account.bandainamcoid.com/login.html"
TEST_TIMEOUT = 12
TEST_WORKERS = 10

SUPPORTED_SCHEMES = ("http", "https", "socks4", "socks5", "socks5h")


def parse_proxy(line):
    """
    Đọc một dòng proxy.

    Trả về (proxy, error):
        (None, None) : dòng trống hoặc chú thích -> bỏ qua
        (dict, None) : dòng hợp lệ
        (None, str)  : dòng sai định dạng, kèm lý do
    """
    raw = (line or "").strip().lstrip("\ufeff")
    if not raw or raw.startswith("#") or raw.startswith("//"):
        return None, None

    body = raw
    scheme = "http"
    if "://" in body:
        candidate, remainder = body.split("://", 1)
        candidate = candidate.lower()
        if candidate in SUPPORTED_SCHEMES:
            scheme, body = candidate, remainder
        else:
            body = raw  # Không phải scheme thật (vd: mật khẩu chứa "://")

    username = password = ""
    host_port = None

    # username:password@ip:port - chỉ nhận khi phần sau @ đúng dạng host:port
    if "@" in body:
        credentials, tail = body.rsplit("@", 1)
        tail_parts = tail.split(":")
        if len(tail_parts) == 2 and tail_parts[1].strip().isdigit():
            host_port = tail
            if ":" in credentials:
                username, password = credentials.split(":", 1)
            else:
                username = credentials

    if host_port is not None:
        host, port = host_port.split(":")
    else:
        parts = body.split(":")
        if len(parts) >= 4 and parts[1].strip().isdigit():
            # ip:port:username:pass (mật khẩu có thể chứa dấu ":" và "@")
            host, port, username, password = parts[0], parts[1], parts[2], ":".join(parts[3:])
        elif len(parts) >= 2:
            host, port = parts[0], parts[1]
        else:
            return None, "Thiếu cổng (port)"

    host = host.strip()
    port = port.strip()
    if not host:
        return None, "Thiếu địa chỉ IP"
    if not port.isdigit() or not 1 <= int(port) <= 65535:
        return None, "Cổng không hợp lệ: %s" % port

    return {
        "host": host,
        "port": int(port),
        "username": username.strip(),
        "password": password,
        "scheme": scheme,
        "raw": raw,
    }, None


def proxy_url(proxy):
    """Xây URL dạng scheme://user:pass@ip:port để requests sử dụng."""
    auth = ""
    if proxy.get("username"):
        auth = "%s:%s@" % (quote(proxy["username"], safe=""), quote(proxy["password"], safe=""))
    return "%s://%s%s:%s" % (proxy.get("scheme", "http"), auth, proxy["host"], proxy["port"])


def as_requests_proxies(proxy):
    """Chuyển một proxy thành dict proxies của requests."""
    url = proxy_url(proxy)
    return {"http": url, "https": url}


def check_proxy(proxy, url=TEST_URL, timeout=TEST_TIMEOUT):
    """Thử một proxy. Trả về (ok, message)."""
    session = requests.Session()
    session.trust_env = False  # Không để proxy hệ thống ảnh hưởng kết quả
    try:
        response = session.get(url, proxies=as_requests_proxies(proxy), timeout=timeout)
    except requests.RequestException as exc:
        message = str(exc).strip() or exc.__class__.__name__
        return False, message[:120]
    finally:
        session.close()
    if response.status_code < 400:
        return True, "HTTP %d" % response.status_code
    return False, "HTTP %d" % response.status_code


def check_all_proxies(proxies, emit, is_running=None, url=TEST_URL, timeout=TEST_TIMEOUT):
    """
    Kiểm tra song song danh sách proxy.
    emit(index, ok, message) được gọi ngay khi từng proxy có kết quả.
    """
    def task(index):
        return index, check_proxy(proxies[index], url, timeout)

    with ThreadPoolExecutor(max_workers=TEST_WORKERS) as pool:
        futures = [pool.submit(task, index) for index in range(len(proxies))]
        for future in as_completed(futures):
            if is_running is not None and not is_running():
                break
            index, (ok, message) = future.result()
            emit(index, ok, message)


class ProxySession(requests.Session):
    """
    Session tự gắn proxy cho request.
    - MODE_PER_REQUEST: mỗi request lấy proxy tiếp theo (luân phiên).
    - MODE_PER_SESSION: proxy được chọn một lần khi tạo session.
    """

    def __init__(self, manager):
        super().__init__()
        self._proxy_manager = manager
        self._per_session = manager.mode == MODE_PER_SESSION
        self._fixed_proxies = manager.next_proxies() if self._per_session else None

    @property
    def proxy_label(self):
        """Địa chỉ proxy đang dùng, rỗng khi không bật proxy."""
        proxies = self._fixed_proxies or {}
        url = proxies.get("https") or proxies.get("http") or ""
        if "@" in url:
            url = url.split("@", 1)[1]
        return url

    def request(self, method, url, **kwargs):
        if self._per_session:
            proxies = self._fixed_proxies
        else:
            proxies = self._proxy_manager.next_proxies()
        if proxies:
            kwargs.setdefault("proxies", proxies)
        return super().request(method, url, **kwargs)


class ProxyManager:
    """Giữ trạng thái proxy: file, bật/tắt, chế độ và con trỏ luân phiên."""

    def __init__(self, path=PROXY_FILE):
        self.path = path
        self.enabled = False
        self.mode = MODE_PER_REQUEST
        self.proxies = []
        self.errors = []  # list[(số dòng, nội dung, lý do)]
        self._cursor = 0
        self._lock = threading.Lock()

    def load(self, path=None):
        """Đọc lại file proxy. Trả về (số proxy hợp lệ, danh sách lỗi)."""
        if path:
            self.path = path
        proxies, errors = [], []
        if os.path.exists(self.path):
            try:
                with open(self.path, "r", encoding="utf-8-sig") as handle:
                    lines = handle.readlines()
            except OSError as exc:
                lines = []
                errors.append((0, self.path, str(exc)))
            for number, line in enumerate(lines, 1):
                proxy, error = parse_proxy(line)
                if proxy is not None:
                    proxies.append(proxy)
                elif error is not None:
                    errors.append((number, line.strip(), error))
        with self._lock:
            self.proxies = proxies
            self.errors = errors
            self._cursor = 0
        return proxies, errors

    def next_proxies(self):
        """Lấy dict proxies của proxy kế tiếp; None khi proxy đang tắt."""
        if not self.enabled:
            return None
        with self._lock:
            if not self.proxies:
                return None
            proxy = self.proxies[self._cursor % len(self.proxies)]
            self._cursor += 1
        return as_requests_proxies(proxy)

    def new_session(self):
        """Tạo session HTTP dùng proxy theo cấu hình hiện tại."""
        return ProxySession(self)

    def status_text(self):
        if not self.enabled:
            return "Proxy đang tắt - request đi thẳng"
        if not self.proxies:
            return "Proxy đang bật nhưng chưa có proxy nào trong file"
        return "%d proxy sẵn sàng" % len(self.proxies)


# Instance dùng chung cho toàn ứng dụng
proxy_manager = ProxyManager()


def new_session():
    """Tạo session HTTP dùng proxy theo cấu hình hiện tại."""
    return proxy_manager.new_session()
