"""Mã 種類 (slot ngày/giờ nhận hàng) của Parks2: `159016_1121_1100_1`.

Cấu trúc: `<mã_hàng>_<MMDD>_<HHMM>_<số_đơn_vị>` — ví dụ `159016_1121_1100_1` là hàng
159016, ngày 21/11, 11:00, 1 suất. Site chỉ mở một số khung giờ nhất định, nên UI cho
chọn ngày + khung giờ rồi ghép mã ở đây (không bắt người dùng gõ mã tay).

Chế độ chia giờ: mỗi tài khoản một khung giờ ngẫu nhiên, chia **đều** (xáo trộn rồi
lặp vòng) thay vì để cả loạt tài khoản cùng một giờ — giống người thật đặt từng suất
khác nhau, và không dồn hết vào một khung.
"""
import random

SLOT_ITEM_DEFAULT = "159016"
SLOT_UNITS = "1"


def slot_code(item, date_text, time_text):
    """Ghép mã slot từ mã hàng, ngày (`YYYY-MM-DD`) và giờ (`HH:MM`).

    Trả "" khi ngày/giờ không đọc được — nơi gọi coi như "không đổi slot".
    """
    day = str(date_text or "").strip()
    clock = str(time_text or "").strip().replace(":", "")
    if len(day) != 10 or len(clock) != 4 or not clock.isdigit():
        return ""
    month_day = day[5:7] + day[8:10]
    if len(month_day) != 4 or not month_day.isdigit():
        return ""
    item = str(item or SLOT_ITEM_DEFAULT).strip() or SLOT_ITEM_DEFAULT
    return "%s_%s_%s_%s" % (item, month_day, clock, SLOT_UNITS)


def split_slot_code(code):
    """Tách mã slot thành (mã hàng, ngày YYYY-MM-DD, giờ HH:MM); None khi sai dạng."""
    parts = str(code or "").strip().split("_")
    if len(parts) < 3:
        return None
    item, month_day, clock = parts[0], parts[1], parts[2]
    if len(month_day) != 4 or not month_day.isdigit():
        return None
    if len(clock) != 4 or not clock.isdigit():
        return None
    date_text = "____-%s-%s" % (month_day[:2], month_day[2:])
    return item, date_text, "%s:%s" % (clock[:2], clock[2:])


def plan_slots(emails, fixed="", item=SLOT_ITEM_DEFAULT, date_text="", times=()):
    """Ghép giờ nhận cho từng tài khoản: trả {email: mã slot}.

    - `fixed` khác rỗng: mọi tài khoản dùng đúng mã đó (người dùng đã chọn tay).
    - ngược lại, nếu có `date_text` + `times`: mỗi tài khoản một mã ngẫu nhiên, chia
      đều giữa các khung giờ (xáo trộn rồi lặp vòng) để không dồn hết vào một giờ.
    - không đủ dữ liệu: trả {} để recipe giữ nguyên giá trị mặc định của nó.
    """
    order = [email for email in emails if email]
    if fixed:
        return {email: fixed for email in order}
    if not order or not date_text:
        return {}
    codes = [slot_code(item, date_text, time_text) for time_text in (times or ())]
    codes = [code for code in codes if code]
    if not codes:
        return {}
    plan = {}
    pool = []
    for email in order:
        if not pool:
            pool = list(codes)
            random.shuffle(pool)
        plan[email] = pool.pop()
    return plan


def describe_plan(plan):
    """Chuỗi tóm tắt phân bổ slot cho log, ví dụ `1121_1100_1=12, 1121_1330_1=11`."""
    counts = {}
    for code in plan.values():
        short = code.split("_", 1)[1] if "_" in code else code
        counts[short] = counts.get(short, 0) + 1
    items = sorted(counts.items())
    return ", ".join("%s=%d" % (key, value) for key, value in items)
