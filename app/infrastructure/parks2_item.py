"""Đọc trang item Parks2 để lấy danh sách 種類 (ngày/giờ nhận) thật của chiến dịch.

Dùng `new_session()` của proxy_manager nên request đi qua proxy như mọi chỗ khác; trang
item không cần đăng nhập, nên lấy được mã trước khi chạy mà không mở Chrome.
"""
from app.config import USER_AGENT
from app.domain import campaign_slot
from app.domain.ip_rules import is_ip_lockout
from proxy_manager import new_session


class ItemPageError(Exception):
    """Không tải được trang item hoặc không đọc được danh sách 種類."""


def fetch_item_html(url, timeout=25):
    session = new_session()
    try:
        response = session.get(url, headers={"User-Agent": USER_AGENT,
                                             "Accept-Language": "ja,en-US;q=0.9,en;q=0.8"},
                               timeout=timeout)
    finally:
        session.close()
    if response.status_code != 200:
        raise ItemPageError("Trang chiến dịch trả HTTP %d" % response.status_code)
    if is_ip_lockout(response.text):
        raise ItemPageError("Bị chặn IP — bật proxy rồi thử lại")
    return response.text


def fetch_slot_options(url):
    """Trả danh sách 種類 của trang: [{'value', 'label', 'when'}]."""
    if not (url or "").strip():
        raise ItemPageError("Chiến dịch chưa có link")
    options = campaign_slot.parse_options(fetch_item_html(url.strip()))
    if not options:
        raise ItemPageError("Trang không có ô chọn 種類 (có thể chiến dịch khác dạng)")
    return options
