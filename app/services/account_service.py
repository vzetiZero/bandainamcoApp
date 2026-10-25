"""Nghiệp vụ danh sách tài khoản: mọi thay đổi dữ liệu đi qua đây, không qua UI."""
from datetime import datetime
from typing import Iterable, List, Optional

from app.domain.accounts import (
    STATUS_ACTIVE, STATUS_INACTIVE, count_by_status, matches_filters, new_account,
    parse_account_line, preview_lines, profile_fields, to_line,
)


class AccountService:
    """Giữ danh sách tài khoản đang làm việc và lưu nó qua repository."""

    def __init__(self, repository):
        self.repository = repository
        self.accounts: List[dict] = []

    # ---- nạp & lưu ----
    def load(self) -> int:
        self.accounts = self.repository.load()
        return len(self.accounts)

    def save(self):
        return self.repository.save(self.accounts)

    # ---- thêm / xoá ----
    def add(self, email: str, password: str, token: Optional[str] = None) -> bool:
        if self.find(email) is not None:
            return False
        self.accounts.append(new_account(email, password, token))
        return True

    def add_lines(self, lines: Iterable[str]):
        """Thêm một khối dòng `email|password|token`; trả số dòng thêm được và số trùng."""
        added = skipped = 0
        for line in lines:
            account = parse_account_line(line)
            if account is None:
                continue
            if self.add(account["email"], account["password"], account.get("token")):
                added += 1
            else:
                skipped += 1
        return {"added": added, "skipped": skipped}

    def preview(self, lines: Iterable[str]):
        return preview_lines(list(lines), {account["email"] for account in self.accounts})

    def delete_rows(self, rows: Iterable[int]) -> int:
        """Xoá theo thứ tự hàng giảm dần để index không đổi chỗ khi đang xoá."""
        targets = sorted({row for row in rows if 0 <= row < len(self.accounts)}, reverse=True)
        for row in targets:
            del self.accounts[row]
        return len(targets)

    # ---- tra cứu ----
    def find(self, email: str) -> Optional[dict]:
        return next((account for account in self.accounts
                     if account.get("email") == email), None)

    def visible(self, query: str = "", status: str = "") -> List[dict]:
        return [account for account in self.accounts
                if matches_filters(account, query, status)]

    def counts(self):
        return count_by_status(self.accounts)

    def export_lines(self) -> List[str]:
        return [to_line(account) for account in self.accounts]

    # ---- cập nhật trạng thái / hồ sơ ----
    def set_status(self, email: str, success: bool) -> bool:
        account = self.find(email)
        if account is None:
            return False
        account["status"] = STATUS_ACTIVE if success else STATUS_INACTIVE
        account["last_check"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        return True

    def apply_profile(self, email: str, profile: dict) -> int:
        """Gộp hồ sơ Parks2 vào tài khoản; trả số trường hồ sơ mới đọc được."""
        account = self.find(email)
        if account is None:
            return 0
        account.update(profile)
        return len(profile_fields(profile))
