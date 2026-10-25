"""Quy tắc quyết định đăng nhập thành công hay không.

`result == "OK"` chỉ nghĩa là API xử lý được request, KHÔNG nghĩa là xác thực thành công.
"""
import re
from html import unescape

from app.domain.ip_rules import IP_LOCKOUT_REASON, is_ip_lockout


# Site trả lời bằng tiếng Nhật; dịch sẵn các lỗi thường gặp để log dễ đọc.
# Thứ tự quan trọng: mẫu cụ thể (bị khoá do sai mật khẩu) phải đứng trước mẫu chung.
LOGIN_ERROR_TRANSLATIONS = [
    ("ログインを制限", "Tài khoản bị khoá đăng nhập do nhập sai mật khẩu quá số lần - "
                      "cần đặt lại mật khẩu qua email"),
    ("一定回数", "Tài khoản bị khoá tạm thời do nhập sai quá số lần - "
                "cần đặt lại mật khẩu qua email"),
    ("間違っている", "Sai email/mật khẩu, hoặc tài khoản chưa đăng ký"),
    ("ロック", "Tài khoản đang bị khoá tạm thời"),
]

# Dấu hiệu site báo khoá đăng nhập do nhập sai mật khẩu quá số lần (khác với sai
# mật khẩu thường). Tách riêng để luồng đăng nhập còn thử được đường khác.
PASSWORD_LOCKOUT_PATTERNS = ("ログインを制限", "一定回数")


def translate_login_error(text):
    """Dịch thông báo lỗi tiếng Nhật sang câu dễ hiểu; giữ nguyên nếu chưa có bản dịch."""
    for needle, translation in LOGIN_ERROR_TRANSLATIONS:
        if needle in text:
            return translation
    return text


def error_text(payload):
    """Gom mọi thông báo lỗi site trả về thành một chuỗi đã bỏ HTML."""
    error_map = (payload or {}).get("input_error") or {}
    message = error_map.get("error_msg") if isinstance(error_map, dict) else None
    if isinstance(message, dict) and message:
        text = " ".join(str(value) for value in message.values())
    else:
        data = (payload or {}).get("data")
        text = str((data.get("msg") if isinstance(data, dict) else "") or "")
    text = unescape(re.sub(r"<[^>]+>", " ", text))
    return re.sub(r"\s+", " ", text).strip()


def is_password_lockout(payload):
    """True khi site báo khoá đăng nhập vì nhập sai mật khẩu quá số lần.

    Khoá này chặn trước cả bước so mật khẩu, nên nó không nói gì về việc mật khẩu
    đúng hay sai - cần phân biệt với lỗi sai email/mật khẩu thông thường.
    """
    text = error_text(payload)
    return any(needle in text for needle in PASSWORD_LOCKOUT_PATTERNS)


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
        return translate_login_error(str(message or "Server từ chối yêu cầu đăng nhập"))
    error_map = (payload.get("input_error") or {}).get("error_msg")
    if isinstance(error_map, dict) and error_map:
        return translate_login_error(error_text(payload))
    redirect = payload.get("redirect") or payload.get("redirect_no-cache") or ""
    if not redirect or "error.html" in redirect:
        return "Không hoàn tất được phiên đăng nhập"
    return None
