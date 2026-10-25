"""Dòng nhập liệu tài khoản: `email|password|token`."""

STATUS_ACTIVE = "Hoạt động"
STATUS_INACTIVE = "Không hoạt động"
STATUS_UNCHECKED = "Chưa kiểm tra"
FILTER_STATUSES = (STATUS_ACTIVE, STATUS_INACTIVE, STATUS_UNCHECKED)
# Các key meta không phải dữ liệu hồ sơ do Parks2 trả về.
PROFILE_META_KEYS = frozenset({
    "email", "password", "status", "last_check", "profile_fetch_status",
    "parks2_handoff_status",
})


def parse_account_line(line):
    """
    Tách một dòng nhập liệu.

    Định dạng của list tài khoản là `email|password|token` (token là mã riêng của
    từng tài khoản, không dùng để đăng nhập). Mật khẩu là trường thứ hai, KHÔNG phải
    "mọi thứ sau dấu |" - lấy cả token vào mật khẩu thì server từ chối credentials.
    Trả về dict account, hoặc None khi dòng thiếu email/password.
    """
    text = (line or "").strip()
    if "|" not in text:
        return None
    parts = [part.strip() for part in text.split("|")]
    email = parts[0]
    password = parts[1] if len(parts) > 1 else ""
    if not email or not password:
        return None
    account = {"email": email, "password": password, "status": STATUS_UNCHECKED,
               "last_check": None}
    token = "|".join(parts[2:]).strip() if len(parts) > 2 else ""
    if token:
        account["token"] = token
    return account


def migrate_split_passwords(accounts):
    """
    Tách token ra khỏi mật khẩu cho dữ liệu lưu bởi bản cũ.

    Bản cũ nhập bằng `split('|', 1)` nên mật khẩu chứa luôn phần token phía sau,
    khiến server từ chối credentials của mọi tài khoản. Sửa tại chỗ, trả về số
    tài khoản đã đổi.
    """
    migrated = 0
    for account in accounts:
        password = account.get("password") or ""
        if "|" not in password:
            continue
        head, _, tail = password.partition("|")
        account["password"] = head
        if tail and not account.get("token"):
            account["token"] = tail
        migrated += 1
    return migrated

def new_account(email, password, token=None):
    """Một dòng danh sách tài khoản bản trong bộ nhớ."""
    account = {"email": email, "password": password, "status": STATUS_UNCHECKED,
               "last_check": None}
    if token:
        account["token"] = token
    return account


def to_line(account):
    """Đại biểu một tài khoản thành dòng `email|password[|token]` để export."""
    line = f"{account['email']}|{account['password']}"
    if account.get("token"):
        line += f"|{account['token']}"
    return line


def matches_filters(account, query="", status=""):
    """Lọc theo trạng thái và chuỗi tìm kiếm (chỉ so với email, không lộ mật khẩu)."""
    if status and account.get("status") != status:
        return False
    text = (query or "").strip().lower()
    return not text or text in (account.get("email") or "").lower()


def count_by_status(accounts):
    total = len(accounts)
    active = sum(1 for account in accounts if account.get("status") == STATUS_ACTIVE)
    inactive = sum(1 for account in accounts if account.get("status") == STATUS_INACTIVE)
    return {"total": total, "active": active, "inactive": inactive,
            "unchecked": total - active - inactive}


def preview_lines(lines, existing_emails):
    """
    Đếm trước kết quả dán/nhập: thêm bao nhiêu, trùng bao nhiêu, sai định dạng bao nhiêu.

    Không sửa danh sách - dùng cho bảng xem thời gian thực trên UI.
    """
    seen = set(existing_emails)
    added = skipped = bad = 0
    for line in lines:
        account = parse_account_line(line)
        if account is None:
            if line.strip():
                bad += 1
            continue
        if account["email"] in seen:
            skipped += 1
        else:
            seen.add(account["email"])
            added += 1
    return {"added": added, "skipped": skipped, "bad": bad}


def profile_fields(profile):
    """Chỉ những trường hồ sơ thật sự đọc được từ Parks2."""
    return {key: value for key, value in (profile or {}).items()
            if key not in PROFILE_META_KEYS and value not in (None, "")}
