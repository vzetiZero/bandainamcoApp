"""Client đăng nhập BANDAI NAMCO ID bằng requests thuần.

Luồng đi đúng theo những gì JS của site làm (PROJECT_CONTEXT.md mục 5):
login page -> v3/login/init -> v3/login/idpw -> passkey handoff -> hồ sơ Parks2.
Không tạo passkey. Không Selenium.
"""
from dataclasses import dataclass, field
from typing import Callable, Optional

import requests

from app.config import (
    ACCOUNT_COOKIE_DOMAIN, API_URL, CLIENT_ID, ENV_INFO, LOGIN_URL, REDIRECT_URI,
)
from app.domain.login_rules import describe_login_error
from app.infrastructure.bandai_profile import (
    REQUEST_TIMEOUT, HandoffResult, complete_parks2_handoff, fetch_member_profile,
)
from app.infrastructure.web import apply_response_cookies, cookie_payload, request_headers
from proxy_manager import new_session


@dataclass
class AuthenticatedSession:
    """Phiên đã vượt qua bước xác thận; dùng tiếp cho handoff và các trang thành viên."""
    session: requests.Session
    headers: dict
    language: str
    redirect: str


@dataclass
class LoginOutcome:
    """Kết quả một lần 'đăng nhập + đọc hồ sơ', chưa kèm câu chữ hiển thị (việc của UI)."""
    success: bool
    reason: str = ""
    profile: dict = field(default_factory=dict)
    profile_fields: int = 0
    handoff: Optional[HandoffResult] = None


def parse_json(response):
    try:
        return response.json()
    except ValueError:
        return {"result": "NG", "data": {"msg": "Phản hồi không phải JSON"}}


class BandaiAuthClient:
    """Thay mặt người dùng nói chuyện với account-api; mọi request đi qua session_factory."""

    def __init__(self, session_factory: Callable[[], requests.Session] = new_session,
                 timeout: int = REQUEST_TIMEOUT):
        self._session_factory = session_factory
        self._timeout = timeout

    def login(self, email: str, password: str,
              on_progress: Optional[Callable[[int], None]] = None):
        """Xác thực và trả (session, reason). session is None khi server từ chối credentials."""
        report = on_progress or (lambda percent: None)
        session = self._session_factory()
        headers = request_headers()

        report(10)
        session.get(LOGIN_URL, params={"client_id": CLIENT_ID, "redirect_uri": REDIRECT_URI},
                    headers=headers, timeout=self._timeout)
        language = session.cookies.get("language") or "ja"
        # getLanguage() của site luôn tự ghi cookie language; server cần nhìn thấy nó.
        session.cookies.set("language", language, domain=ACCOUNT_COOKIE_DOMAIN,
                            path="/")

        report(40)
        # init cấp cookie challengeProd. Bỏ qua bước này thì Parks2 không trả URL nối
        # tiếp và không bao giờ đọc được hồ sơ.
        init_payload = parse_json(session.get(
            f"{API_URL}v3/login/init", params={
                "client_id": CLIENT_ID, "redirect_uri": REDIRECT_URI, "customize_id": "",
                "language": language, "prompt": "", "sns_not_found": "", "lockout_child": "",
                "cookie": cookie_payload(session), "backto": "", "response_type": "",
                "scope": "", "state": "", "nonce": "",
            }, headers=headers, timeout=self._timeout))
        apply_response_cookies(session, init_payload)

        report(55)
        login_payload = parse_json(session.post(
            f"{API_URL}v3/login/idpw", data={
                "client_id": CLIENT_ID, "redirect_uri": REDIRECT_URI, "backto": "",
                "customize_id": "", "login_id": email, "password": password,
                "env_info": ENV_INFO, "retention": 1, "language": language,
                "cookie": cookie_payload(session), "prompt": "",
            }, headers=headers, timeout=self._timeout))
        apply_response_cookies(session, login_payload)

        report(70)
        reason = describe_login_error(login_payload)
        if reason:
            return None, reason
        redirect = login_payload.get("redirect") or login_payload.get("redirect_no-cache") or ""
        return AuthenticatedSession(session, headers, language, redirect), ""

    def authenticate(self, email: str, password: str,
                     on_progress: Optional[Callable[[int], None]] = None) -> LoginOutcome:
        """Đăng nhập rồi nối tiếp sang Parks2 và đọc hồ sơ thành viên."""
        report = on_progress or (lambda percent: None)
        auth, reason = self.login(email, password, report)
        if auth is None:
            return LoginOutcome(success=False, reason=reason)

        handoff = complete_parks2_handoff(auth.session, auth.headers, auth.redirect,
                                          auth.language, self._timeout)
        profile = {"email": email, "password": password}
        if handoff.gender_code:
            profile["gender_code"] = handoff.gender_code

        report(85)
        # Handoff fail không đồng nghĩa Parks2 không dùng được: luôn thử đọc mypage.
        member_profile = fetch_member_profile(auth.session, auth.headers, self._timeout)
        if member_profile:
            profile.update(member_profile)
            profile["profile_fetch_status"] = "Profile loaded from Parks2"
            if handoff.status:
                profile["parks2_handoff_status"] = handoff.status
        else:
            profile["profile_fetch_status"] = (
                handoff.status or "Parks2 login complete; no profile fields were parsed"
            )
        report(100)
        return LoginOutcome(success=True, profile=profile,
                            profile_fields=len(member_profile), handoff=handoff)
