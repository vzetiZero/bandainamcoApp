"""Quy tắc quyết định đăng nhập thành công hay không.

`result == "OK"` chỉ nghĩa là API xử lý được request, KHÔNG nghĩa là xác thực thành công.
"""
import re
from html import unescape

from app.domain.ip_rules import IP_LOCKOUT_REASON, is_ip_lockout


# Site trả lời bằng tiếng Nhật; dịch sẵn các lỗi thường gặp để log dễ đọc.
LOGIN_ERROR_TRANSLATIONS = [
    ("間違っている", "Sai email/mật khẩu, hoặc tài khoản chưa đăng ký"),
    ("ロック", "Tài khoản đang bị khoá tạm thời"),
]


def describe_login_error(payload):
    """
    Đổi response đăng nhập thành mô-típ lỗi; trả None khi đăng nhập thành công thật.

    `result == "OK"` KHÔNG đồng nghĩa đã xác thực: khi sai credentials server vẫn trả
    OK kèm input_error và không có redirect, nên chỉ nhìn result thì mọi tài khoản
    đều báo "thành công" mà không đọc được hồ sơ.
    """
    if payload.get("result") != "OK":
        data = payload.get("data")
        message = data.get("msg") if isinstance(data, dict) else None
        if is_ip_lockout(payload):
            return IP_LOCKOUT_REASON
        return str(message or "Server từ chối yêu cầu đăng nhập")
    error_map = (payload.get("input_error") or {}).get("error_msg")
    if isinstance(error_map, dict) and error_map:
        text = unescape(re.sub(r"<[^>]+>", " ", " ".join(str(value) for value in error_map.values())))
        text = re.sub(r"\s+", " ", text).strip()
        for needle, translation in LOGIN_ERROR_TRANSLATIONS:
            if needle in text:
                return translation
        return text
    redirect = payload.get("redirect") or payload.get("redirect_no-cache") or ""
    if not redirect or "error.html" in redirect:
        return "Không hoàn tất được phiên đăng nhập"
    return None
