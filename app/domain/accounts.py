"""Dòng nhập liệu tài khoản: `email|password|token`."""


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
    account = {"email": email, "password": password, "status": "Chưa kiểm tra", "last_check": None}
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

