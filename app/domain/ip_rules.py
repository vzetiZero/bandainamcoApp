"""Quy tắc nhận diện lỗi site chặn IP (UnexpectedRemoteAddress).

Khi IP của proxy nằm trong blacklist, site trả 403 kèm JSON dạng:

    {'title': 'UnexpectedRemoteAddress', 'status': 403,
     'result': {'summary': '予期しないIPアドレスからアクセスされました。...',
                'detail': 'Remote address(`...`) is lockouted.'}}

Đây **không** phải lỗi tài khoản: phải đổi sang proxy khác rồi gửi lại request.
Module này chỉ chứa quy tắc thuần (không Qt, không requests) để cả tầng proxy
lẫn `login_rules` dùng chung một danh sách dấu hiệu.
"""

# Dấu hiệu có trong body/JSON khi IP bị chặn. Giữ đủ cả bản tiếng Anh và tiếng Nhật
# vì site trả lẫn lộn tuỳ endpoint.
IP_LOCKOUT_MARKERS = (
    "UnexpectedRemoteAddress",
    "予期しないIPアドレス",
    "is lockouted",
    "ブラックリスト",
)

IP_LOCKOUT_REASON = "IP của proxy bị site chặn (UnexpectedRemoteAddress)"


class IPLockoutError(Exception):
    """Request bị site chặn IP và không còn proxy nào khác để gửi lại."""

    def __init__(self, message: str = "", proxy: str = ""):
        super().__init__(message or IP_LOCKOUT_REASON)
        self.proxy = proxy


def is_ip_lockout(value) -> bool:
    """True khi body/JSON của site chứa dấu hiệu IP bị chặn.

    Nhận mọi kiểu dữ liệu vì lỗi có thể nằm trực tiếp trong JSON, trong chuỗi
    `data.msg`, hoặc bị lồng trong dict `result` của site.
    """
    if value is None:
        return False
    if isinstance(value, dict):
        title = value.get("title")
        if isinstance(title, str) and title.strip().lower() == "unexpectedremoteaddress":
            return True
        return any(is_ip_lockout(item) for item in value.values())
    if isinstance(value, (list, tuple, set)):
        return any(is_ip_lockout(item) for item in value)
    if isinstance(value, bytes):
        value = value.decode("utf-8", "ignore")
    text = str(value)
    return any(marker in text for marker in IP_LOCKOUT_MARKERS)
