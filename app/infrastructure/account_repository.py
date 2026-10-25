"""Kho tài khoản: đọc/ghi `accounts_data.json`, không biết gì về Qt."""
import json
import os
from typing import Callable, List, Optional

from app.config import DATA_FILE
from app.domain.accounts import migrate_split_passwords


class AccountRepository:
    def __init__(self, path: str = DATA_FILE,
                 on_change: Optional[Callable[[str], None]] = None):
        self._path = path
        self._log = on_change or (lambda message: None)

    def exists(self) -> bool:
        return os.path.exists(self._path)

    def load(self) -> List[dict]:
        """Trả về danh sách tài khoản; tự sửa dữ liệu mật khẩu dính token."""
        if not self.exists():
            return []
        try:
            with open(self._path, "r", encoding="utf-8") as handle:
                accounts = json.load(handle)
        except (OSError, ValueError) as exc:
            self._log(f"Lỗi tải dữ liệu: {exc}")
            return []
        if not isinstance(accounts, list):
            self._log("Lỗi tải dữ liệu: file không chứa danh sách tài khoản")
            return []
        migrated = migrate_split_passwords(accounts)
        if migrated:
            self._log(
                "Đã sửa "
                f"{migrated} tài khoản bị lưu mật khẩu kèm token (định dạng email|password|token)"
            )
            self.save(accounts)
        return accounts

    def save(self, accounts: List[dict]) -> int:
        """Ghi file; trả về 0 khi lỗi để UI quyết định thông báo."""
        try:
            with open(self._path, "w", encoding="utf-8") as handle:
                json.dump(accounts, handle, ensure_ascii=False, indent=2)
        except OSError as exc:
            self._log(f"Lỗi lưu dữ liệu: {exc}")
            return 0
        self._log(f"Đã lưu {len(accounts)} tài khoản")
        return len(accounts)
