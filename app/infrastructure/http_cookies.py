"""Cầu nối giữa cookie jar của requests và trường `cookie` dạng JSON mà site yêu cầu."""
import json


def cookie_payload(session):
    """JSON của các cookie đang có - site yêu cầu trường `cookie` ở mọi request."""
    return json.dumps({cookie.name: cookie.value for cookie in session.cookies})


def apply_response_cookies(session, payload):
    """Giống cookie_processing() của site: đặt cookie có value, xoá cookie chỉ có tên."""
    for cookie_data in (payload or {}).get("cookie", {}).values():
        name = cookie_data.get("name")
        if not name:
            continue
        if "value" in cookie_data:
            kwargs = {"path": cookie_data.get("path") or "/"}
            if cookie_data.get("domain"):
                kwargs["domain"] = cookie_data["domain"]
            session.cookies.set(name, cookie_data["value"], **kwargs)
            continue
        for existing in list(session.cookies):
            if existing.name == name:
                try:
                    session.cookies.clear(existing.domain, existing.path, name)
                except KeyError:
                    pass
