"""Recipe thao tác trình duyệt cho chiến dịch 抽選 — quy tắc thuần, không Qt/network.

Recipe là dữ liệu JSON mô tả *các bước* thao tác trên trang, để khi site đổi
layout chỉ phải sửa file JSON trong `recipes/`, không phải sửa code Python.

Cấu trúc:

```json
{
  "name": "parks2_campaign",
  "login": {
    "url": "https://account.bandainamcoid.com/login.html?client_id=...",
    "logged_in_selector": "css chỉ ra đã đăng nhập",
    "steps": [ {"action": "fill", "selector": "#login_id", "value": "{email}"} ]
  },
  "entry": {
    "steps": [ {"action": "click", "selector": "..."} ]
  },
  "verification": {
    "success_text": ["受付が完了"],
    "already_text": ["すでに"],
    "closed_text": ["受付期間外"],
    "error_text": ["エラー"]
  }
}
```

Bước (`steps`) là dict có `action`:

| action | field bắt buộc | việc làm |
|---|---|---|
| `goto` | `value` (URL) | điều hướng tới URL (hỗ trợ `{email}`) |
| `fill` | `selector`, `value` | điền text (hỗ trợ `{email}`, `{password}`) |
| `select` | `selector`, `value` | chọn option theo value/label |
| `check` | `selector` | tick checkbox/radio |
| `click` | `selector` | bấm |
| `press` | `key` (+ `selector` tuỳ chọn) | gõ phím |
| `wait_text` | `value` | chờ text xuất hiện |
| `wait_selector` | `selector` | chờ phần tử xuất hiện |
| `sleep` | `value` (giây) | nghỉ có chủ đích (trang chờ JS) |
| `screenshot` | `value` (tên file) | chụp ảnh mốc giữa luồng |
| `dismiss` | `selectors` (danh sách) hoặc `selector`, tuỳ chọn `check` | đóng popup/quảng cáo: nếu có `check` thì tick checkbox đó trước, rồi bấm cái đang hiện (không có thì bỏ qua, không chờ timeout) |
| `pause` | — | **dừng tại đây và để cửa sổ Chrome mở** cho người dùng tự làm tiếp (vd: bước thanh toán) |
| `submit` | — | điểm bấm gửi: **chỉ chạy khi bật submit** |

Mọi bước có thể đặt `"optional": true` để bỏ qua khi phần tử không có (ví dụ
hộp thoại cookie/đồng ý điều khoản chỉ xuất hiện lần đầu),
`"requires_submit": true` để chỉ chạy khi người dùng bật submit,
`"when": "{bien}"` để chỉ chạy khi biến đó có giá trị (rỗng/0/false ⇒ bỏ bước), và
`"only_if_empty": true` cho `fill`/`select` để KHÔNG ghi đè dữ liệu site đã điền sẵn.
"""
import json
import re

STEP_ACTIONS = (
    "goto", "fill", "select", "check", "click", "press",
    "wait_text", "wait_selector", "sleep", "screenshot", "dismiss", "pause", "submit",
)
# Trường bắt buộc theo từng action.
REQUIRED_FIELDS = {
    "goto": ("value",),
    "fill": ("selector", "value"),
    "select": ("selector", "value"),
    "check": ("selector",),
    "click": ("selector",),
    "press": ("key",),
    "wait_text": ("value",),
    "wait_selector": ("selector",),
    "sleep": ("value",),
    "screenshot": ("value",),
    "dismiss": (),
    "pause": (),
    "submit": (),
}
# Dấu hiệu recipe còn là bản nháp: chưa dò selector thật trên trang.
PLACEHOLDER_MARKERS = ("TODO", "<", "selector-that")
VERIFICATION_KEYS = ("success_text", "already_text", "closed_text", "error_text")
# Giá trị của `when` bị coi là "không bật".
FALSE_VALUES = frozenset({"", "0", "false", "no", "off", "none", "null"})


def truthy(text):
    """True khi `when`/biến có nội dung thật sự bật bước."""
    return str(text if text is not None else "").strip().lower() not in FALSE_VALUES


class RecipeNotReady(Exception):
    """Recipe thiếu/sai cấu trúc, hoặc còn placeholder chưa thay bằng selector thật."""


def load_recipe(path):
    """Đọc file recipe JSON; lỗi đọc/parse đều thành RecipeNotReady."""
    try:
        with open(path, "r", encoding="utf-8-sig") as handle:
            recipe = json.load(handle)
    except OSError as exc:
        raise RecipeNotReady("Không đọc được recipe %s: %s" % (path, exc)) from exc
    except ValueError as exc:
        raise RecipeNotReady("Recipe %s không phải JSON hợp lệ: %s" % (path, exc)) from exc
    errors = validate_recipe(recipe)
    if errors:
        raise RecipeNotReady("Recipe %s chưa dùng được:\n- %s" % (path, "\n- ".join(errors)))
    return recipe


def _steps_errors(steps, where):
    errors = []
    if not isinstance(steps, list):
        return ["%s: 'steps' phải là danh sách" % where]
    for index, step in enumerate(steps):
        label = "%s bước %d" % (where, index + 1)
        if not isinstance(step, dict):
            errors.append("%s: phải là object" % label)
            continue
        action = step.get("action")
        if action not in STEP_ACTIONS:
            errors.append("%s: action '%s' không hợp lệ (dùng: %s)"
                          % (label, action, ", ".join(STEP_ACTIONS)))
            continue
        for field in REQUIRED_FIELDS[action]:
            value = step.get(field)
            if value in (None, ""):
                errors.append("%s (%s): thiếu '%s'" % (label, action, field))
        if action == "dismiss":
            selectors = step.get("selectors")
            if not step.get("selector") and not selectors:
                errors.append("%s (dismiss): cần 'selector' hoặc 'selectors'" % label)
            elif selectors is not None and not isinstance(selectors, list):
                errors.append("%s (dismiss): 'selectors' phải là danh sách" % label)
            for text in (selectors or []):
                if isinstance(text, str) and any(mark in text for mark in PLACEHOLDER_MARKERS):
                    errors.append("%s (dismiss): '%s' còn là placeholder" % (label, text))
        when = step.get("when")
        if when is not None and not isinstance(when, str):
            errors.append("%s: 'when' phải là chuỗi (vd \"{zip}\")" % label)
        if "only_if_empty" in step and not isinstance(step.get("only_if_empty"), bool):
            errors.append("%s: 'only_if_empty' phải là true/false" % label)
        for field in ("selector", "value"):
            text = step.get(field)
            if isinstance(text, str) and any(mark in text for mark in PLACEHOLDER_MARKERS):
                errors.append("%s (%s): '%s' còn là placeholder — dò lại bằng "
                              "browser_campaign.py --discover" % (label, action, text))
    return errors


def validate_recipe(recipe):
    """Trả danh sách lỗi (rỗng = dùng được)."""
    if not isinstance(recipe, dict):
        return ["Recipe phải là một object JSON"]
    errors = []
    if not str(recipe.get("name") or "").strip():
        errors.append("Thiếu 'name'")
    entry = recipe.get("entry")
    if not isinstance(entry, dict):
        errors.append("Thiếu khối 'entry' (các bước trên trang chiến dịch)")
    else:
        errors.extend(_steps_errors(entry.get("steps"), "entry"))
    login = recipe.get("login")
    if login is not None:
        if not isinstance(login, dict):
            errors.append("'login' phải là object")
        else:
            if not str(login.get("url") or "").strip():
                errors.append("login: thiếu 'url'")
            errors.extend(_steps_errors(login.get("steps"), "login"))
    verification = recipe.get("verification") or {}
    if not isinstance(verification, dict):
        errors.append("'verification' phải là object")
    else:
        for key in VERIFICATION_KEYS:
            value = verification.get(key)
            if value not in (None,) and not isinstance(value, list):
                errors.append("verification.%s phải là danh sách chuỗi" % key)
    return errors


def render_value(template, email="", password="", context=None):
    """Thay `{email}`, `{password}` và các biến trong `context` (vd `{card_number}`).

    `context` là dict phẳng lấy từ `payment.card_vars()` hoặc nguồn khác; giá trị
    thiếu thì thay bằng chuỗi rỗng để form không bị dính chữ "{...}".
    """
    if not isinstance(template, str):
        return template
    text = template.replace("{email}", email or "").replace("{password}", password or "")
    for key, value in (context or {}).items():
        token = "{%s}" % key
        if token in text:
            text = text.replace(token, "" if value is None else str(value))
    # Biến không có trong context phải thành rỗng, không được để chữ "{building}"
    # dính vào form hay làm `when` tưởng là "có giá trị".
    return re.sub(r"\{[a-z_]+\}", "", text)


def phase_steps(recipe, phase):
    """Danh sách bước của một khối ('login' | 'entry'); [] nếu không có."""
    block = recipe.get(phase) or {}
    steps = block.get("steps") or []
    return [step for step in steps if isinstance(step, dict)]


def verification_texts(recipe, key):
    """Danh sách câu dấu hiệu (success/already/closed/error) đã khai báo."""
    values = (recipe.get("verification") or {}).get(key) or []
    return [str(value) for value in values if str(value).strip()]


def match_any(text, needles):
    """Câu dấu hiệu đầu tiên xuất hiện trong text (so khớp không phân biệt hoa thường)."""
    haystack = (text or "").lower()
    for needle in needles or []:
        if needle.lower() in haystack:
            return needle
    return ""


def classify_outcome(recipe, page_text):
    """Phân loại kết quả từ nội dung trang: 'registered'|'already'|'closed'|'error'|''.

    Thứ tự kiểm tra quan trọng: trang lỗi/đã đăng ký/ngoài hạn phải được nhận ra
    trước, nếu không một câu "受付が完了" còn sót trong trang lỗi sẽ bị tính là
    đăng ký thành công.
    """
    for status, key in (("error", "error_text"), ("closed", "closed_text"),
                        ("already", "already_text"), ("registered", "success_text")):
        if match_any(page_text, verification_texts(recipe, key)):
            return status
    return ""
