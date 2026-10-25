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

Nếu site trả lỗi chặn IP (`UnexpectedRemoteAddress`), proxy vừa dùng bị cho nghỉ
và request được gửi lại bằng proxy kế tiếp (xem `ProxySession.request`).
"""
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import quote, urlsplit

import requests

from app.config import (
    ACCOUNT_ORIGIN, API_URL, CLIENT_ID, LOGIN_URL, REDIRECT_URI, USER_AGENT,
)
from app.domain.ip_rules import IPLockoutError, is_ip_lockout

APP_DIR = os.path.dirname(os.path.abspath(__file__))
PROXY_FILE = os.path.join(APP_DIR, "proxy.txt")

MODE_PER_REQUEST = "per_request"
MODE_PER_SESSION = "per_session"

# Proxy check gọi v3/login/init của account-api (endpoint app thật sự dùng) thay vì
# trang login tĩnh: trang login trả 200 cho mọi IP nên không nói lên điều gì, còn
# init xác nhận proxy thông được tới account-api và trả JSON đúng định dạng. Nếu
# body có dấu hiệu chặn IP thì proxy bị đánh dấu hỏng và vào danh sách tạm nghỉ.
CHECK_PARAMS = {
    "client_id": CLIENT_ID, "redirect_uri": REDIRECT_URI, "customize_id": "",
    "language": "ja", "prompt": "", "sns_not_found": "", "lockout_child": "",
    "cookie": "{}", "backto": "", "response_type": "", "scope": "", "state": "",
    "nonce": "",
}
CHECK_HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
    "Origin": ACCOUNT_ORIGIN,
    "Referer": LOGIN_URL,
}
CHECK_OK_MESSAGE = "IP không bị chặn"
CHECK_BLOCKED_MESSAGE = "IP bị chặn (UnexpectedRemoteAddress)"

TEST_TIMEOUT = 12
TEST_WORKERS = 10

SUPPORTED_SCHEMES = ("http", "https", "socks4", "socks5", "socks5h")

# Số proxy tối đa thử cho MỘT request khi IP bị site chặn.
PROXY_ATTEMPTS = 5
# Proxy bị chặn được đưa vào danh sách tạm nghỉ bao nhiêu giây trước khi dùng lại.
# IP vào blacklist thường không hết nhanh, nên để dài hơn một lần kiểm tra.
BLOCK_COOLDOWN = 1800

# UI nối hàm nhận log vào đây (worker thread đẩy message, UI tự đổ ra QTextEdit).
_event_sink = None
# Nhãn tài khoản của thread đang chạy (email) để mỗi dòng log request biết thuộc
# tài khoản nào khi nhiều luồng chạy song song.
_event_context = threading.local()


def set_event_sink(sink):
    """Đặt hàm nhận log sự kiện proxy; gọi được từ worker thread."""
    global _event_sink
    _event_sink = sink


def set_event_context(label):
    """Gắn nhãn tài khoản cho log của thread hiện tại; truyền "" để bỏ nhãn."""
    _event_context.label = label or ""


def _emit_event(message):
    sink = _event_sink
    if sink is None:
        return
    label = getattr(_event_context, "label", "")
    if label:
        message = "[%s] %s" % (label, message)
    try:
        sink(message)
    except Exception:  # Log lỗi không được làm hỏng request
        pass


def request_label(method, url):
    """Host + path của request; KHÔNG lấy query vì init mang cookie trong query."""
    parts = urlsplit(url)
    return "%s %s%s" % (method, parts.netloc, parts.path)


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


def response_is_ip_lockout(response):
    """
    True khi body của response là lỗi chặn IP của site.

    Chỉ đọc body khi response là JSON hoặc có mã lỗi: trang HTML bình thường
    không chứa các dấu hiệu này, đọc hết mọi trang chỉ làm chậm.
    """
    content_type = (response.headers.get("Content-Type") or "").lower()
    if "json" not in content_type and response.status_code < 400:
        return False
    try:
        return is_ip_lockout(response.text)
    except (UnicodeDecodeError, ValueError, requests.RequestException):
        return False


def check_proxy(proxy, timeout=TEST_TIMEOUT):
    """Thử một proxy bằng account-api. Trả về (ok, message)."""
    session = requests.Session()
    session.trust_env = False  # Không để proxy hệ thống ảnh hưởng kết quả
    try:
        response = session.get(f"{API_URL}v3/login/init", params=CHECK_PARAMS,
                               headers=CHECK_HEADERS,
                               proxies=as_requests_proxies(proxy), timeout=timeout)
    except requests.RequestException as exc:
        message = str(exc).strip() or exc.__class__.__name__
        return False, message[:120]
    finally:
        session.close()
    if response.status_code >= 400:
        return False, "HTTP %d" % response.status_code
    try:
        payload = response.json()
    except ValueError:
        return False, "Phản hồi không phải JSON"
    if is_ip_lockout(payload):
        return False, CHECK_BLOCKED_MESSAGE
    if payload.get("result") != "OK":
        return False, "result=%s" % payload.get("result")
    return True, CHECK_OK_MESSAGE


def check_all_proxies(proxies, emit, is_running=None, timeout=TEST_TIMEOUT, manager=None):
    """
    Kiểm tra song song danh sách proxy.
    emit(index, ok, message) được gọi ngay khi từng proxy có kết quả.
    Proxy bị chặn IP được đưa luôn vào danh sách tạm nghỉ của `manager`
    (mặc định là proxy_manager dùng chung).
    """
    target = manager or proxy_manager

    def task(index):
        return index, check_proxy(proxies[index], timeout)

    with ThreadPoolExecutor(max_workers=TEST_WORKERS) as pool:
        futures = [pool.submit(task, index) for index in range(len(proxies))]
        for future in as_completed(futures):
            if is_running is not None and not is_running():
                break
            index, (ok, message) = future.result()
            proxy = as_requests_proxies(proxies[index])
            if ok:
                target.unblock(proxy)  # IP đã dùng được lại -> ra khỏi danh sách tạm nghỉ
            elif message == CHECK_BLOCKED_MESSAGE:
                target.mark_blocked(proxy)
            emit(index, ok, message)


class ProxySession(requests.Session):
    """
    Session tự gắn proxy cho request.
    - MODE_PER_REQUEST: mỗi request lấy proxy tiếp theo (luân phiên).
    - MODE_PER_SESSION: proxy được chọn một lần khi tạo session.

    Khi site báo chặn IP (`UnexpectedRemoteAddress`), proxy đó bị đánh dấu nghỉ và
    request được gửi lại ngay bằng proxy khác. Ở MODE_PER_SESSION, proxy mới thay
    luôn proxy cố định để các request sau của cùng tài khoản không quay lại IP chết.
    """

    def __init__(self, manager):
        super().__init__()
        self._proxy_manager = manager
        self._per_session = manager.mode == MODE_PER_SESSION
        self._fixed_proxies = manager.next_proxies() if self._per_session else None
        self._last_proxies = self._fixed_proxies

    @property
    def proxy_label(self):
        """Địa chỉ proxy đang dùng, rỗng khi không bật proxy."""
        return self._proxy_manager.label_of(self._last_proxies)

    def _current_proxies(self):
        """Proxy của lần gửi đầu tiên trong request hiện tại."""
        if self._per_session:
            if not self._fixed_proxies:
                self._fixed_proxies = self._proxy_manager.next_proxies()
            return self._fixed_proxies
        return self._proxy_manager.next_proxies()

    def _rotate_proxies(self):
        """Đổi sang proxy kế tiếp (bỏ qua proxy vừa bị chặn) rồi ghi nhớ proxy mới."""
        if self._per_session:
            self._fixed_proxies = self._proxy_manager.next_proxies()
            return self._fixed_proxies
        return self._proxy_manager.next_proxies()

    def request(self, method, url, **kwargs):
        manager = self._proxy_manager
        attempts = PROXY_ATTEMPTS if manager.rotatable() else 1
        proxies = self._current_proxies()
        last_error = None

        for attempt in range(1, attempts + 1):
            self._last_proxies = proxies
            request_kwargs = dict(kwargs)
            if proxies:
                request_kwargs["proxies"] = proxies
            response = super().request(method, url, **request_kwargs)

            if manager.enabled:
                _emit_event("%s · proxy %s · HTTP %d" % (
                    request_label(method, url),
                    manager.label_of(proxies) or "trực tiếp (proxy đang tắt)",
                    response.status_code))

            if not manager.enabled or not response_is_ip_lockout(response):
                return response

            # IP của proxy này đã bị blacklist: cho nghỉ rồi gửi lại bằng proxy khác.
            manager.mark_blocked(proxies)
            response.close()
            label = manager.label_of(proxies) or "?"
            _emit_event("⚠ %s bị chặn IP → đưa vào danh sách tạm nghỉ %d phút"
                        % (label, BLOCK_COOLDOWN // 60))
            last_error = IPLockoutError(proxy=label)
            if attempt < attempts:
                proxies = self._rotate_proxies()
                if not proxies:
                    break
                _emit_event("↻ gửi lại %s bằng proxy %s"
                            % (request_label(method, url),
                               manager.label_of(proxies) or "trực tiếp"))

        raise last_error or IPLockoutError()


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
        self._blocked = {}  # url proxy -> thời điểm hết tạm nghỉ (time.monotonic)

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
            # File mới thì bỏ mọi đánh dấu chặn của danh sách cũ.
            self._blocked.clear()
        return proxies, errors

    def rotatable(self):
        """Có nhiều hơn một proxy để đổi khi IP bị chặn hay không."""
        return self.enabled and len(self.proxies) > 1

    @staticmethod
    def label_of(proxies):
        """Địa chỉ (host:port) của dict proxies, không kèm user/pass."""
        url = (proxies or {}).get("https") or (proxies or {}).get("http") or ""
        return url.split("@", 1)[1] if "@" in url else url

    def mark_blocked(self, proxies, seconds=BLOCK_COOLDOWN):
        """Cho proxy vừa bị site chặn nghỉ một lúc để vòng luân phiên bỏ qua nó."""
        url = (proxies or {}).get("https") or (proxies or {}).get("http")
        if not url:
            return ""
        with self._lock:
            self._blocked[url] = time.monotonic() + seconds
        return self.label_of(proxies)

    def unblock(self, proxies):
        """Proxy vừa kiểm tra thấy dùng được: bỏ khỏi danh sách tạm nghỉ."""
        url = (proxies or {}).get("https") or (proxies or {}).get("http")
        if not url:
            return
        with self._lock:
            self._blocked.pop(url, None)

    def blocked_count(self):
        """Số proxy đang trong thời gian tạm nghỉ."""
        now = time.monotonic()
        with self._lock:
            return sum(1 for until in self._blocked.values() if until > now)

    def is_blocked(self, proxy):
        """Proxy có đang nằm trong danh sách tạm nghỉ hay không."""
        with self._lock:
            return self._blocked.get(proxy_url(proxy), 0.0) > time.monotonic()

    def blocked_remaining(self, proxy):
        """Số giây còn lại của proxy đang tạm nghỉ; 0 khi không bị chặn."""
        with self._lock:
            remaining = self._blocked.get(proxy_url(proxy), 0.0) - time.monotonic()
        return max(0, int(remaining))

    def blocked_entries(self):
        """Danh sách proxy đang tạm nghỉ: [(host:port, số giây còn lại)], sắp theo thời gian."""
        now = time.monotonic()
        with self._lock:
            entries = [(url, int(until - now)) for url, until in self._blocked.items()
                       if until > now]
        result = []
        for url, remaining in entries:
            label = url.split("@", 1)[1] if "@" in url else url.split("://", 1)[-1]
            result.append((label, remaining))
        return sorted(result, key=lambda item: item[1])

    def reset_blocks(self):
        """Bỏ toàn bộ danh sách tạm nghỉ để thử lại tất cả proxy ngay."""
        with self._lock:
            count = len(self._blocked)
            self._blocked.clear()
        return count

    def _pick_proxy(self, now):
        """Proxy kế tiếp chưa bị chặn. Gọi khi đã giữ `_lock`.

        Trả (proxy, reused_blocked): reused_blocked=True khi mọi proxy đều đang
        tạm nghỉ và phải dùng lại proxy hết hạn sớm nhất.
        """
        total = len(self.proxies)
        for _ in range(total):
            proxy = self.proxies[self._cursor % total]
            self._cursor += 1
            if self._blocked.get(proxy_url(proxy), 0.0) <= now:
                return proxy, False
        # Tất cả đang tạm nghỉ: mở lại proxy hết hạn sớm nhất để app không kẹt hẳn.
        stale = min(self._blocked, key=self._blocked.get)
        self._blocked.pop(stale, None)
        for proxy in self.proxies:
            if proxy_url(proxy) == stale:
                return proxy, True
        return self.proxies[0], True

    def next_proxies(self):
        """Lấy dict proxies của proxy kế tiếp; None khi proxy đang tắt."""
        if not self.enabled:
            return None
        with self._lock:
            if not self.proxies:
                return None
            proxy, reused_blocked = self._pick_proxy(time.monotonic())
        proxies = as_requests_proxies(proxy)
        if reused_blocked:
            _emit_event("⚠ tất cả proxy đang tạm nghỉ - dùng lại %s"
                        % self.label_of(proxies))
        return proxies

    def new_session(self):
        """Tạo session HTTP dùng proxy theo cấu hình hiện tại."""
        return ProxySession(self)

    def status_text(self):
        if not self.enabled:
            return "Proxy đang tắt - request đi thẳng"
        if not self.proxies:
            return "Proxy đang bật nhưng chưa có proxy nào trong file"
        text = "%d proxy sẵn sàng" % len(self.proxies)
        blocked = self.blocked_count()
        if blocked:
            text += " (%d tạm nghỉ do bị chặn IP)" % blocked
        return text


# Instance dùng chung cho toàn ứng dụng
proxy_manager = ProxyManager()


def new_session():
    """Tạo session HTTP dùng proxy theo cấu hình hiện tại."""
    return proxy_manager.new_session()
