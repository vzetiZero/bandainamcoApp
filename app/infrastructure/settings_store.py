"""Nơi chứa tuỳ chọn người dùng (QSettings) để UI/services không tự chạm QSettings."""
import json
from typing import Any

from PySide6.QtCore import QSettings


class SettingsStore:
    def __init__(self, organization: str = "NAMCO", application: str = "AccountManager"):
        self._settings = QSettings(organization, application)

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
