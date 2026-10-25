"""Header và cookie dùng chung cho mọi request của luồng sessions (requests thuần).

Site không nhận cookie qua header suồng sã: JS của nó nhét `JSON.stringify($.cookie())`
vào trường `cookie` của mọi request, nên cookie jar và payload phải luôn khớp nhau.
"""
import json

from app.config import ACCOUNT_ORIGIN, LOGIN_URL, USER_AGENT


def request_headers():
    """Header gốc của trang đăng nhập - dùng cho cả account-api lẫn parks2."""
    return {
        "User-Agent": USER_AGENT,
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
        "Origin": ACCOUNT_ORIGIN,
        "Referer": LOGIN_URL,
    }


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
