"""Client đổi tên thành viên Parks2 qua form member_regist.html?request=edit."""
import re
from dataclasses import dataclass
from typing import Callable, Dict, Optional
from urllib.parse import urljoin

import requests

from app.config import PARKS2_HOST
from app.domain.names import NameForm
from app.infrastructure.bandai_auth import BandaiAuthClient
from app.infrastructure.bandai_profile import REQUEST_TIMEOUT, complete_parks2_handoff

MEMBER_REGIST_URL = f"{PARKS2_HOST}/member_regist.html?request=edit"
# Trang edit gửi form "memberFrm" với request=confirm; trang xác nhận gửi form
# "confirmForm" với request=execute + token. Chỉ POST bước đầu thì tên chưa đổi.
EDIT_FORM = "memberFrm"
CONFIRM_FORM = "confirmForm"

FORM_BLOCK = re.compile(r"<form\b[^>]*>.*?</form>", re.S | re.I)
FORM_OPEN = re.compile(r"<form\b[^>]*>", re.I)
INPUT_TAG = re.compile(r"<input\b([^>]*)>", re.I)
ATTRIBUTE = re.compile(r'([\w:.\-]+)\s*=\s*"([^"]*)"')

# Tên field của site tương ứng từng thuộc tính NameForm.
FIELD_NAMES = {
    "L_NAME": "last_name",
    "F_NAME": "first_name",
    "L_KANA": "last_kana",
    "F_KANA": "first_kana",
    "NICKNAME": "nickname",
}


@dataclass
class NameOutcome:
    """Kết quả một lần đổi tên; message là thông báo kỹ thuật, chưa phải câu chữ UI."""
    success: bool
    message: str
    form: Optional[NameForm] = None


def form_block_html(html: str, form_name: str) -> str:
    """
    Trả về khối `<form name="form_name">...</form>`.

    Trang hồ sơ có thêm form tìm kiếm ở header và menu mobile; lấy form đầu tiên thì
    POST sẽ gửi sang item_list.html và không sửa được gì.
    """
    blocks = FORM_BLOCK.findall(html)
    for block in blocks:
        open_tag = FORM_OPEN.search(block)
        if open_tag and f'name="{form_name}"' in open_tag.group(0):
            return block
    for block in blocks:
        if 'name="L_NAME"' in block:
            return block
    return html


def _tag_attributes(tag_attrs: str) -> Dict[str, str]:
    return dict(ATTRIBUTE.findall(tag_attrs))


def parse_name_form(html: str, page_url: str, form_name: str = EDIT_FORM) -> NameForm:
    """Đọc giá trị hiện tại, action, hidden input và nút submit từ một form của trang."""
    scope = form_block_html(html, form_name)
    values = {}
    hidden = {}
    submit = None
    for match in INPUT_TAG.finditer(scope):
        attributes = _tag_attributes(match.group(1))
        name = attributes.get("name")
        if not name:
            continue
        input_type = (attributes.get("type") or "text").lower()
        field = FIELD_NAMES.get(name)
        # Field tên xuất hiện cả ở input lẫn hidden; tag đầu tiên là giá trị thật.
        if field and field not in values:
            values[field] = attributes.get("value", "")
        if input_type == "hidden":
            hidden.setdefault(name, attributes.get("value", ""))
        elif input_type == "submit" and submit is None:
            submit = (name, attributes.get("value", ""))
    open_tag = FORM_OPEN.search(scope)
    action_match = re.search(r'action="([^"]*)"', open_tag.group(0)) if open_tag else None
    return NameForm(
        page=page_url,
        action=urljoin(page_url, action_match.group(1)) if action_match else page_url,
        hidden=hidden,
        submit=submit,
        **values,
    )


def describe_submit_result(response) -> NameOutcome:
    """HTML trả về có khối lỗi thì báo thất bại kèm nội dung lỗi; còn lại coi là đã gửi."""
    error_match = re.search(r'class="[^"]*error[^"]*"[^>]*>([^<]*)<', response.text)
    if response.status_code != 200:
        return NameOutcome(False, f"HTTP Error: {response.status_code}")
    if error_match and error_match.group(1).strip():
        return NameOutcome(False, f"Lỗi: {error_match.group(1).strip()}")
    return NameOutcome(True, "Đã gửi form")


class BandaiNameClient:
    """
    Đổi tên thành viên qua flow 2 bước của site: member_regist (confirm) ->
    member_regist_confirm (execute) -> đọc lại trang để xác nhận tên đã đổi.
    """

    def __init__(self, auth_client: Optional[BandaiAuthClient] = None,
                 timeout: int = REQUEST_TIMEOUT):
        self._auth = auth_client or BandaiAuthClient()
        self._timeout = timeout

    def open_edit_page(self, email: str, password: str,
                       on_progress: Optional[Callable[[int], None]] = None):
        """Trả (session, headers, NameForm, message). form is None khi không vào được trang."""
        report = on_progress or (lambda percent: None)
        report(10)
        auth, reason = self._auth.login(email, password, report)
        if auth is None:
            return None, None, None, f"Đăng nhập thất bại: {reason}"
        report(45)
        handoff = complete_parks2_handoff(auth.session, auth.headers, auth.redirect,
                                          auth.language, self._timeout)
        if not handoff.ok:
            return None, None, None, handoff.status or "Không nối tiếp được phiên Parks2"
        report(60)
        form, message = self.read_form(auth.session, auth.headers)
        if form is None:
            return None, None, None, message
        return auth.session, auth.headers, form, ""

    def read_form(self, session, headers) -> tuple:
        """Mở lại trang sửa hồ sơ bằng session đang có."""
        page_headers = dict(headers)
        page_headers["Referer"] = f"{PARKS2_HOST}/member_mypage.html"
        try:
            response = session.get(MEMBER_REGIST_URL, headers=page_headers,
                                   timeout=self._timeout)
        except requests.RequestException as exc:
            return None, f"Lỗi lấy trang: {exc}"
        if response.status_code != 200:
            return None, (
                f"Không thể truy cập trang đổi thông tin (Status: {response.status_code})")
        return parse_name_form(response.text, response.url), ""

    def submit(self, session, headers, form: NameForm,
               overrides: Optional[Dict[str, str]] = None) -> NameOutcome:
        """POST form đã nạp sẵn giá trị hiện tại; overrides là các field site dùng làm tên."""
        submit_headers = dict(headers)
        submit_headers["Content-Type"] = "application/x-www-form-urlencoded"
        submit_headers["Referer"] = form.page
        try:
            response = session.post(form.action, data=form.form_data(overrides),
                                    headers=submit_headers, timeout=self._timeout)
        except requests.RequestException as exc:
            return NameOutcome(False, f"Lỗi gửi request: {exc}", form)
        outcome = describe_submit_result(response)
        outcome.form = parse_name_form(response.text, response.url, CONFIRM_FORM)
        return outcome

    def change_profile(self, email: str, password: str, overrides: Dict[str, str],
                       on_progress: Optional[Callable[[int], None]] = None) -> NameOutcome:
        """
        Gửi các override rồi đọc lại trang để xác minh, vì site không báo "đã lưu".

        Để trống một trường nghĩa là giữ giá trị cũ (NameForm lo phần đó).
        """
        report = on_progress or (lambda percent: None)
        session, headers, form, message = self.open_edit_page(email, password, report)
        if form is None:
            return NameOutcome(False, message, None)
        payload = form.form_data(overrides)
        wanted = {field: payload[field] for field in overrides}

        report(75)
        confirm = self.submit(session, headers, form, overrides)
        if not confirm.success or confirm.form is None or not confirm.form.action:
            return NameOutcome(False, confirm.message, form)

        report(88)
        executed = self.submit(session, headers, confirm.form, {})
        if not executed.success:
            return NameOutcome(False, executed.message, form)

        report(94)
        recheck, message = self.read_form(session, headers)
        if recheck is None:
            return NameOutcome(True, "Đã gửi form (không đọc lại được trang)", form)
        unchanged = {field: value for field, value in wanted.items()
                     if recheck.current(field) != value}
        if unchanged:
            return NameOutcome(
                False,
                "Trang vẫn hiển thị: " + ", ".join(f"{name}={value}"
                                                   for name, value in unchanged.items()),
                recheck)
        report(100)
        return NameOutcome(True, "Đổi thông tin đã được lưu", recheck)
