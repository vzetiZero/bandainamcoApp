"""Nơi chứa tuỳ chọn người dùng (QSettings) để UI/services không tự chạm QSettings."""
import json
import os
from typing import Any

from PySide6.QtCore import QSettings


class SettingsStore:
    """Đọc/ghi tuỳ chọn qua QSettings.

    `path` khác rỗng: lưu thành file INI ngay trong thư mục dự án, nên copy cả
    thư mục sang máy khác (hoặc bản sao mới) vẫn giữ nguyên cấu hình. Lần chạy
    đầu tiên sẽ chép các giá trị cũ từ registry sang file để không mất cấu hình
    đang dùng. `path` rỗng: giữ hành vi cũ - chỉ dùng registry Windows.
    """

    def __init__(self, organization: str = "NAMCO", application: str = "AccountManager",
                 path: str = ""):
        self._legacy = QSettings(organization, application)
        if path:
            first_run = not os.path.exists(path)
            self._settings = QSettings(path, QSettings.Format.IniFormat)
            if first_run:
                self._copy_legacy_values()
        else:
            self._settings = self._legacy

    def _copy_legacy_values(self):
        """Chuyển cấu hình đang có trong registry sang file INI (chỉ lần đầu)."""
        for key in self._legacy.allKeys():
            self._settings.setValue(key, self._legacy.value(key))
        self._settings.sync()

    def get(self, key: str, default: Any = None) -> Any:
        return self._settings.value(key, default)

    def get_bool(self, key: str, default: bool = False) -> bool:
        return self._settings.value(key, default, type=bool)

    def get_int(self, key: str, default: int = 0) -> int:
        value = self._settings.value(key, default)
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    def set(self, **values: Any) -> None:
        for key, value in values.items():
            self._settings.setValue(key, value)
        self._settings.sync()

    def get_json(self, key: str, default: str):
        """Đọc giá trị lưu dạng JSON; trả về `default` đã parse khi thiếu hoặc hỏng."""
        stored = self._settings.value(key, default)
        try:
            return json.loads(stored) if isinstance(stored, str) else stored
        except (TypeError, ValueError):
            return json.loads(default)

    def set_json(self, key: str, value: Any) -> None:
        self.set(**{key: json.dumps(value, ensure_ascii=False)})
