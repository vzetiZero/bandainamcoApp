"""Dò trang thật để viết recipe: HTML, ảnh, danh sách input và snapshot MCP.

Đây là công cụ *soạn recipe*, không phải luồng chạy hàng loạt: mở Chrome của một
tài khoản, vào trang chiến dịch, rồi đổ ra thư mục `browser_artifacts/` những gì
cần để điền selector vào `recipes/parks2_campaign.json`:

| File | Dùng để |
|---|---|
| `page.html` | tìm form/action/name của framework Interfactory |
| `text.txt` | câu thông báo thật (dùng cho `verification.*_text`) |
| `screenshot.png` | nhìn trang bằng mắt |
| `elements.json` | danh sách input/button kèm selector gợi ý |
| `a11y_snapshot.txt` | snapshot của chrome-devtools-mcp (uid + role + name) |

Snapshot MCP là thứ trả lời câu "phần tử này bấm được bằng gì", nên nếu server MCP
không chạy thì các file còn lại vẫn đủ để viết recipe bằng CSS selector.
"""
import json
import os
from datetime import datetime

from app.config import BROWSER_ARTIFACTS_DIR
from app.infrastructure.browser.browser_session import profile_slug
from app.infrastructure.browser.mcp_client import DevtoolsMcpClient, McpError

# Liệt kê mọi phần tử tương tác kèm selector gợi ý (id/name > CSS theo vị trí).
ELEMENTS_SCRIPT = """
() => {
  const cssEscape = (value) => (window.CSS && CSS.escape) ? CSS.escape(value) : value;
  const selectorFor = (el) => {
    if (el.id) return '#' + cssEscape(el.id);
    const name = el.getAttribute('name');
    if (name) return el.tagName.toLowerCase() + '[name="' + name + '"]';
    const type = el.getAttribute('type');
    if (type) return el.tagName.toLowerCase() + '[type="' + type + '"]';
    return el.tagName.toLowerCase();
  };
  const nodes = Array.from(document.querySelectorAll(
    'input, select, textarea, button, a, form, label'));
  return nodes.slice(0, 400).map((el) => ({
    tag: el.tagName.toLowerCase(),
    type: el.getAttribute('type') || '',
    id: el.id || '',
    name: el.getAttribute('name') || '',
    action: el.getAttribute('action') || '',
    placeholder: el.getAttribute('placeholder') || '',
    value: (el.value || '').slice(0, 60),
    text: (el.innerText || '').replace(/\\s+/g, ' ').trim().slice(0, 80),
    selector: selectorFor(el),
    visible: !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length),
  }));
}
"""


def _output_dir(label):
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = os.path.join(BROWSER_ARTIFACTS_DIR, "discover_%s_%s" % (profile_slug(label), stamp))
    os.makedirs(path, exist_ok=True)
    return path


def _write(path, text):
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text or "")
    return path


def dump_with_mcp(cdp_url, out_dir, on_log=None):
    """Snapshot a11y + console qua chrome-devtools-mcp; trả dict đường dẫn (có thể rỗng)."""
    paths = {}
    client = DevtoolsMcpClient(cdp_url=cdp_url, on_log=on_log)
    try:
        client.start()
    except McpError as exc:
        if on_log:
            on_log("Bỏ qua snapshot MCP: %s" % exc)
        return paths
    try:
        pages = client.list_pages()
        paths["pages"] = _write(os.path.join(out_dir, "mcp_pages.txt"), pages)
        snapshot = ""
        for candidate in (1, 0, 2, 3):
            try:
                snapshot = client.snapshot(page_id=candidate)
                if snapshot:
                    paths["snapshot"] = _write(
                        os.path.join(out_dir, "a11y_snapshot.txt"), snapshot)
                    break
            except McpError:
                continue
    finally:
        client.close()
    return paths


def discover_page(email, url, session, on_log=None, with_mcp=True):
    """Đổ HTML/text/ảnh/elements của trang hiện tại ra thư mục artifacts."""
    out_dir = _output_dir(email)
    page = session.page
    paths = {"dir": out_dir}
    paths["html"] = _write(os.path.join(out_dir, "page.html"), page.content())
    paths["text"] = _write(os.path.join(out_dir, "text.txt"), session.page_text())
    image = session.screenshot(os.path.join(out_dir, "screenshot.png"), full_page=True)
    if image:
        paths["screenshot"] = image
    try:
        elements = page.evaluate(ELEMENTS_SCRIPT)
        paths["elements"] = _write(os.path.join(out_dir, "elements.json"),
                                   json.dumps(elements, ensure_ascii=False, indent=2))
    except Exception as exc:  # noqa: BLE001 - chỉ là công cụ soạn recipe
        if on_log:
            on_log("Không lấy được danh sách phần tử: %s" % exc)
    if with_mcp and session.cdp_url:
        paths.update(dump_with_mcp(session.cdp_url, out_dir, on_log=on_log))
    summary = (
        "Đã dò trang cho %s\n"
        "  URL      : %s\n"
        "  Thư mục  : %s\n"
        "  HTML     : %s\n"
        "  Text     : %s\n"
        "  Ảnh      : %s\n"
        "  Elements : %s\n"
        "  Snapshot : %s\n"
        % (email, page.url, out_dir, os.path.basename(paths.get("html", "")),
           os.path.basename(paths.get("text", "")),
           os.path.basename(paths.get("screenshot", "")),
           os.path.basename(paths.get("elements", "")),
           os.path.basename(paths.get("snapshot", "")) or "(không có)"))
    if on_log:
        on_log(summary)
    return paths
