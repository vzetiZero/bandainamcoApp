"""Hồ sơ đặt hàng + thanh toán do người dùng nhập trong UI — quy tắc thuần.

Không có thông tin nào ở đây bị hard-code vào code: người dùng điền trong tab
Cấu hình, đổi lúc nào cũng được, và recipe chỉ tham chiếu bằng biến:

| Nhóm | Biến | Ý nghĩa |
|---|---|---|
| Người nhận | `{l_name}` `{f_name}` `{l_kana}` `{f_kana}` | 姓/名 (kanji) và セイ/メイ (kana) |
| Địa chỉ | `{zip}` `{pref}` `{city}` `{street}` `{building}` | 郵便番号 / 都道府県 / 市区町村 / 丁目・番地 / ビル名 |
| Địa chỉ | `{building_none}` | `1` khi tick 「ビル・マンション名・部屋番号なし」, ngược lại rỗng |
| Liên hệ | `{tel}` | 携帯電話番号 |
| Thẻ | `{card_holder}` `{card_number}` `{card_exp}` `{card_exp_month}` `{card_exp_year}` `{card_cvv}` | thông tin thẻ |

Dữ liệu thẻ là dữ liệu nhạy cảm: chỉ `summary()` và `mask_card()` được dùng để
ghi ra UI/log. `profile_vars()` trả số thẻ đầy đủ vì nó chỉ dùng để điền form.
"""
import re
from datetime import date

# (tên field, nhãn UI, nhóm)
FIELDS = (
    ("l_name", "Họ (姓 kanji)", "Người nhận"),
    ("f_name", "Tên (名 kanji)", "Người nhận"),
    ("l_kana", "Họ kana (セイ)", "Người nhận"),
    ("f_kana", "Tên kana (メイ)", "Người nhận"),
    ("zip", "Mã bưu điện (郵便番号)", "Địa chỉ"),
    ("pref", "Tỉnh/Thành (都道府県)", "Địa chỉ"),
    ("city", "Quận/Huyện (市区町村)", "Địa chỉ"),
    ("street", "Số nhà (丁目・番地)", "Địa chỉ"),
    ("building", "Toà nhà / phòng (ビル・マンション名)", "Địa chỉ"),
    ("tel", "Điện thoại (携帯電話番号)", "Liên hệ"),
)
CARD_FIELDS = (
    ("card_holder", "Tên in trên thẻ"),
    ("card_number", "Số thẻ"),
    ("card_exp", "Hạn dùng (MM/YY)"),
    ("card_cvv", "CVV/CVC"),
)
TEXT_FIELDS = tuple(name for name, _, _ in FIELDS)
ALL_FIELDS = TEXT_FIELDS + tuple(name for name, _ in CARD_FIELDS)
SENSITIVE_FIELDS = ("card_number", "card_cvv")
# Trường bắt buộc trên form ご注文情報入力 (site đánh dấu 必須).
REQUIRED_FIELDS = ("zip", "pref", "city", "street", "tel")

BRANDS = (
    ("Visa", re.compile(r"^4")),
    ("Mastercard", re.compile(r"^(5[1-5]|2[2-7])")),
    ("JCB", re.compile(r"^35")),
    ("American Express", re.compile(r"^3[47]")),
    ("Diners", re.compile(r"^3(0[0-5]|[68])")),
    ("Discover", re.compile(r"^6(011|5)")),
)
PREFECTURES = (
    "北海道", "青森県", "岩手県", "宮城県", "秋田県", "山形県", "福島県", "茨城県",
    "栃木県", "群馬県", "埼玉県", "千葉県", "東京都", "神奈川県", "新潟県", "富山県",
    "石川県", "福井県", "山梨県", "長野県", "岐阜県", "静岡県", "愛知県", "三重県",
    "滋賀県", "京都府", "大阪府", "兵庫県", "奈良県", "和歌山県", "鳥取県", "島根県",
    "岡山県", "広島県", "山口県", "徳島県", "香川県", "愛媛県", "高知県", "福岡県",
    "佐賀県", "長崎県", "熊本県", "大分県", "宮崎県", "鹿児島県", "沖縄県",
)


def digits_only(text):
    return re.sub(r"\D", "", text or "")


def luhn_ok(number):
    """Kiểm tra checksum Luhn — bắt lỗi gõ nhầm số thẻ."""
    digits = digits_only(number)
    if not 12 <= len(digits) <= 19:
        return False
    total = 0
    for index, char in enumerate(reversed(digits)):
        value = int(char)
        if index % 2 == 1:
            value *= 2
            if value > 9:
                value -= 9
        total += value
    return total % 10 == 0


def card_brand(number):
    digits = digits_only(number)
    for name, pattern in BRANDS:
        if pattern.match(digits):
            return name
    return ""


def mask_card(number):
    """`**** **** **** 1234` — dạng duy nhất được phép ghi ra UI/log."""
    digits = digits_only(number)
    return "**** **** **** %s" % digits[-4:] if digits else ""


def parse_expiry(text):
    """'12/28' -> (12, 2028); trả (0, 0) khi không đọc được."""
    match = re.match(r"^\s*(\d{1,2})\s*[/\-]\s*(\d{2}|\d{4})\s*$", text or "")
    if not match:
        return 0, 0
    month, year = int(match.group(1)), int(match.group(2))
    if year < 100:
        year += 2000
    if not 1 <= month <= 12:
        return 0, 0
    return month, year


def clean(data):
    """Chuẩn hoá: bỏ khoảng trắng thừa, số điện thoại/thẻ chỉ giữ chữ số."""
    data = data or {}
    cleaned = {}
    for name in TEXT_FIELDS:
        cleaned[name] = (data.get(name) or "").strip()
    cleaned["zip"] = digits_only(data.get("zip"))
    cleaned["tel"] = digits_only(data.get("tel"))
    cleaned["pref"] = (data.get("pref") or "").strip()
    for name in ("card_holder",):
        cleaned[name] = (data.get(name) or "").strip()
    cleaned["card_number"] = digits_only(data.get("card_number"))
    cleaned["card_cvv"] = digits_only(data.get("card_cvv"))
    month, year = parse_expiry(data.get("card_exp"))
    cleaned["card_exp"] = "%02d/%02d" % (month, year % 100) if month else ""
    cleaned["building_none"] = bool(data.get("building_none"))
    return cleaned


def validate(data):
    """Danh sách lỗi (rỗng = lưu được). Chỉ bắt buộc nhóm địa chỉ/liên hệ."""
    data = data or {}
    errors = []
    if data.get("pref") and data["pref"] not in PREFECTURES:
        errors.append("pref: tỉnh/thành không nằm trong danh sách 都道府県")
    zip_code = digits_only(data.get("zip"))
    if zip_code and len(zip_code) != 7:
        errors.append("zip: 郵便番号 phải 7 chữ số")
    tel = digits_only(data.get("tel"))
    if tel and not 10 <= len(tel) <= 11:
        errors.append("tel: số điện thoại phải 10–11 chữ số")
    number = digits_only(data.get("card_number"))
    if number:
        if not luhn_ok(number):
            errors.append("card_number: số thẻ không hợp lệ (sai checksum Luhn)")
        month, year = parse_expiry(data.get("card_exp"))
        if not month:
            errors.append("card_exp: hạn dùng phải dạng MM/YY")
        else:
            today = date.today()
            if (year, month) < (today.year, today.month):
                errors.append("card_exp: thẻ đã hết hạn")
        if len(digits_only(data.get("card_cvv"))) not in (3, 4):
            errors.append("card_cvv: CVV phải 3 hoặc 4 chữ số")
        if len((data.get("card_holder") or "").strip()) < 2:
            errors.append("card_holder: nhập tên in trên thẻ")
    return errors


def missing_required(data):
    """Các trường 必須 còn trống (dùng để cảnh báo trước khi chạy)."""
    data = data or {}
    return [name for name in REQUIRED_FIELDS if not (data.get(name) or "").strip()]


def has_card(data):
    return bool(digits_only((data or {}).get("card_number")))


def summary(data):
    """Mô tả an toàn cho UI/log: không số thẻ đầy đủ, không CVV."""
    data = data or {}
    parts = []
    if has_card(data):
        brand = card_brand(data.get("card_number")) or "Thẻ"
        parts.append("%s %s – %s" % (brand, mask_card(data.get("card_number")),
                                     data.get("card_exp") or "??/??"))
    address = " ".join(filter(None, [data.get("pref"), data.get("city"),
                                     data.get("street")]))
    if address:
        parts.append("địa chỉ: " + address)
    if data.get("tel"):
        parts.append("SĐT: " + data.get("tel"))
    return " | ".join(parts) if parts else "Chưa có thông tin đặt hàng/thanh toán"


def short_summary(data, encrypted=True):
    """Một dòng thật ngắn cho nhãn UI (chi tiết xem ở tooltip)."""
    data = data or {}
    if not any(data.get(name) for name in ALL_FIELDS):
        return "Chưa nhập thông tin"
    parts = []
    if has_card(data):
        parts.append(mask_card(data.get("card_number")))
    place = " ".join(filter(None, [data.get("pref"), data.get("city")]))
    if place:
        parts.append(place)
    parts.append("đã mã hoá" if encrypted else "CHƯA mã hoá")
    return " · ".join(parts)


def profile_vars(data):
    """Biến cho recipe. Mọi trường văn bản đều có mặt (rỗng nếu chưa nhập) để
    `when` hiểu đúng là "chưa có"; riêng nhóm thẻ chỉ xuất hiện khi có số thẻ."""
    data = clean(data or {})
    variables = {name: (data.get(name) or "") for name in TEXT_FIELDS}
    variables["building_none"] = "1" if data.get("building_none") else ""
    if has_card(data):
        month, year = parse_expiry(data.get("card_exp"))
        variables.update({
            "card_holder": data.get("card_holder", ""),
            "card_number": data.get("card_number", ""),
            "card_exp": data.get("card_exp", ""),
            "card_exp_month": "%02d" % month if month else "",
            "card_exp_year": "%02d" % (year % 100) if year else "",
            "card_cvv": data.get("card_cvv", ""),
        })
    return variables
