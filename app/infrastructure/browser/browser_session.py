"""Một cửa sổ Chrome riêng cho một tài khoản (Playwright + CDP).

Mỗi tài khoản cần **profile, proxy và cổng debug riêng** thì mới đăng nhập song
song được mà không giẫm cookie của nhau. Lớp này gói ba việc đó:

1. mở Chrome thật (`channel="chrome"`, không tải Chromium riêng) với
   `--user-data-dir` riêng và `--remote-debugging-port` riêng;
2. gắn proxy có user/pass của `proxy_manager` vào đúng phiên đó;
3. để `chrome-devtools-mcp` gắn vào cùng cửa sổ qua `cdp_url` khi cần dò trang.

Điều khiển flow đi qua Playwright (selector CSS ổn định, chạy được hàng trăm
tài khoản), MCP chỉ dùng để dò/chẩn đoán.
"""
import os
import re
import socket
import time

from app.config import (
    BROWSER_ACTION_TIMEOUT, BROWSER_CDP_BASE_PORT, BROWSER_NAV_TIMEOUT,
    BROWSER_PROFILE_DIR, CHROME_CANDIDATES,
)


class BrowserStartError(Exception):
    """Không mở được Chrome (thiếu Playwright, thiếu Chrome, profile đang bận...)."""


def profile_slug(email):
    """Tên thư mục profile an toàn cho Windows từ email."""
    slug = re.sub(r"[^0-9A-Za-z._-]+", "_", (email or "default").strip())
    return slug[:64].strip("._") or "default"


def find_chrome():
    """Đường dẫn chrome.exe, hoặc None nếu máy không có Chrome ở vị trí chuẩn."""
    candidates = list(CHROME_CANDIDATES)
    local_appdata = os.environ.get("LOCALAPPDATA")
    if local_appdata:
        candidates.append(os.path.join(local_appdata, "Google", "Chrome", "Application",
                                       "chrome.exe"))
    for path in candidates:
        if path and os.path.isfile(path):
            return path
    return None


def free_port(start=BROWSER_CDP_BASE_PORT, attempts=60):
    """Cổng TCP còn trống, bắt đầu từ cổng debug mặc định của app."""
    for offset in range(attempts):
        port = start + offset
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                probe.bind(("127.0.0.1", port))
            except OSError:
                continue
        return port
    raise BrowserStartError("Không còn cổng trống trong dải %d..%d"
                            % (start, start + attempts - 1))


def playwright_proxy(proxy):
    """Dict proxy của proxy_manager -> dict proxy của Playwright (có user/pass)."""
    if not proxy:
        return None
    scheme = proxy.get("scheme") or "http"
    server = "%s://%s:%s" % (scheme, proxy["host"], proxy["port"])
    payload = {"server": server}
    if proxy.get("username"):
        payload["username"] = proxy["username"]
        payload["password"] = proxy.get("password") or ""
    return payload


class BrowserSession:
    """Chrome riêng của một tài khoản. Dùng như context manager."""

    def __init__(self, email, proxy=None, headless=False, chrome_path=None,
                 profile_root=BROWSER_PROFILE_DIR, on_log=None):
        self.email = email
        self.proxy = proxy
        self.headless = headless
        self.chrome_path = chrome_path or find_chrome()
        self.profile_root = profile_root
        self.on_log = on_log or (lambda message: None)
        self.port = None
        self._playwright = None
        self._context = None
        self._page = None

    # ---------------- vòng đời ----------------
    @property
    def profile_dir(self):
        return os.path.join(self.profile_root, profile_slug(self.email))

    @property
    def cdp_url(self):
        return "http://127.0.0.1:%d" % self.port if self.port else ""

    @property
    def page(self):
        return self._page

    def start(self):
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:  # pragma: no cover - phụ thuộc môi trường
            raise BrowserStartError(
                "Thiếu Playwright. Chạy: python -m pip install playwright") from exc
        if not self.chrome_path:
            raise BrowserStartError(
                "Không tìm thấy chrome.exe. Cài Google Chrome hoặc đặt biến "
                "CHROME_PATH.")
        os.makedirs(self.profile_dir, exist_ok=True)
        self.port = free_port()
        args = [
            "--remote-debugging-port=%d" % self.port,
            "--remote-allow-origins=*",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-blink-features=AutomationControlled",
            # Chrome coi cửa sổ bị cửa sổ khác che là "occluded" rồi ngừng vẽ, làm
            # `page.screenshot()` trả ảnh trắng. Tắt hẳn cơ chế đó + throttling.
            "--disable-features=CalculateNativeWinOcclusion,Translate,MediaRouter",
            "--disable-backgrounding-occluded-windows",
            "--disable-renderer-backgrounding",
            "--disable-background-timer-throttling",
            "--window-size=1280,900",
        ]
        launch = {
            "user_data_dir": self.profile_dir,
            "headless": self.headless,
            "args": args,
            # Chrome do Playwright mở sẽ tự thêm --enable-automation và bật cờ
            # navigator.webdriver; bỏ nó để phiên giống trình duyệt thật hơn.
            "ignore_default_args": ["--enable-automation"],
            "locale": "ja-JP",
            "timezone_id": "Asia/Tokyo",
            "accept_downloads": False,
            "viewport": {"width": 1280, "height": 900},
        }
        proxy = playwright_proxy(self.proxy)
        if proxy:
            launch["proxy"] = proxy
        try:
            self._playwright = sync_playwright().start()
            if os.path.isfile(self.chrome_path):
                launch["executable_path"] = self.chrome_path
            else:
                launch["channel"] = "chrome"
            try:
                self._context = self._playwright.chromium.launch_persistent_context(
                    **launch)
            except Exception as exc:  # noqa: BLE001
                # Cửa sổ cũ còn giữ profile: chờ nó thoát rồi thử lại một lần.
                if "existing browser session" not in str(exc).lower():
                    raise
                self.on_log("%s: profile đang bị cửa sổ cũ giữ, chờ 4s rồi mở lại"
                            % self.email)
                time.sleep(4)
                self._context = self._playwright.chromium.launch_persistent_context(
                    **launch)
        except Exception as exc:  # noqa: BLE001 - Playwright ném nhiều loại lỗi
            self.close()
            message = str(exc)
            if "existing browser session" in message.lower():
                message = ("profile của %s đang bị cửa sổ Chrome khác giữ — đóng cửa sổ đó "
                           "(hoặc bấm Đóng tất cả) rồi chạy lại" % self.email)
            raise BrowserStartError("Không mở được Chrome cho %s: %s"
                                    % (self.email, message)) from exc
        self._context.set_default_timeout(BROWSER_ACTION_TIMEOUT)
        self._context.set_default_navigation_timeout(BROWSER_NAV_TIMEOUT)
        pages = self._context.pages
        self._page = pages[0] if pages else self._context.new_page()
        label = "không proxy" if not self.proxy else "%s:%s" % (self.proxy["host"],
                                                                self.proxy["port"])
        self.on_log("Chrome của %s: cổng %d, profile %s, %s"
                    % (self.email, self.port, profile_slug(self.email), label))
        return self

    def new_page(self):
        """Tab mới trong cùng phiên (dùng khi trang chiến dịch cần tab riêng)."""
        self._page = self._context.new_page()
        return self._page

    def close(self):
        context, playwright = self._context, self._playwright
        self._context = self._playwright = self._page = None
        if context is not None:
            try:
                context.close()
            except Exception:  # noqa: BLE001 - dọn dẹp, không được ném lỗi
                pass
        if playwright is not None:
            try:
                playwright.stop()
            except Exception:  # noqa: BLE001
                pass

    def __enter__(self):
        return self.start()

    def __exit__(self, *exc_info):
        self.close()
        return False

    # ---------------- tiện ích ----------------
    def goto(self, url):
        """Điều hướng chịu lỗi mạng (trả response hoặc None)."""
        try:
            return self._page.goto(url, wait_until="domcontentloaded",
                                   timeout=BROWSER_NAV_TIMEOUT)
        except Exception as exc:  # noqa: BLE001
            self.on_log("Điều hướng lỗi %s: %s" % (url, exc))
            return None

    def page_text(self):
        """Toàn bộ text nhìn thấy được của trang (để phân loại kết quả)."""
        try:
            return self._page.inner_text("body", timeout=BROWSER_ACTION_TIMEOUT)
        except Exception:  # noqa: BLE001
            return ""

    def screenshot(self, path, full_page=True):
        """Lưu ảnh màn hình, trả đường dẫn (hoặc '' nếu lỗi)."""
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            self._page.screenshot(path=path, full_page=full_page)
            return path
        except Exception as exc:  # noqa: BLE001
            self.on_log("Chụp ảnh lỗi: %s" % exc)
            return ""

