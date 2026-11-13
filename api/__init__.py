"""API backend (FastAPI) cho giao diện web Next.js.

Toàn bộ nghiệp vụ vẫn nằm ở `app/` (domain + services + adapters); gói này chỉ mở
HTTP/JSON quanh chúng, thêm hàng đợi job để chạy tác vụ dài (kiểm tra tài khoản,
chạy chiến dịch bằng Chrome) ngoài request.
"""

__all__ = ["create_app"]


def create_app(*args, **kwargs):
    """Import muộn để `import api` không kéo theo FastAPI khi chỉ dùng bản desktop."""
    from api.app import create_app as factory

    return factory(*args, **kwargs)
