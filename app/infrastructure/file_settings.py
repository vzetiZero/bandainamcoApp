"""Tuỳ chọn người dùng cho chế độ web/API — cùng interface với `SettingsStore` (Qt).

Bản Qt cũ dùng QSettings/INI; API không phụ thuộc Qt nên ở đây
đọc/ghi một file JSON `web_settings.json` với đúng các method mà services đang
gọi (`get`, `get_bool`, `get_int`, `set`, `get_json`, `set_json`).

Lần đầu chạy, nếu có `ui_settings.ini` của bản desktop thì chép giá trị sang
(best-effort) để không mất danh sách chiến dịch đang dùng.
"""
import configparser
import json
import os
import threading
from typing import Any


class FileSettingsStore:
    """Lưu tuỳ chọn vào JSON; an toàn khi nhiều thread cùng ghi."""

    def __init__(self, path: str, legacy_ini: str = ""):
        self.path = path
        self.legacy_ini = legacy_ini
        self._lock = threading.RLock()
        self._data = {}
        self._load()

    # ---------------- nạp/ghi ----------------
    def _load(self):
        if os.path.exists(self.path):
            try:
                with open(self.path, "r", encoding="utf-8") as handle:
                    self._data = json.load(handle) or {}
                return
            except (OSError, ValueError):
                self._data = {}
        if self.legacy_ini and os.path.exists(self.legacy_ini):
            self._data = self._read_legacy_ini()
            if self._data:
                self._flush()

    def _read_legacy_ini(self):
        """Đọc `ui_settings.ini` của bản desktop (QSettings INI, mục [General])."""
        parser = configparser.ConfigParser(interpolation=None)
        try:
            parser.read(self.legacy_ini, encoding="utf-8")
        except (OSError, UnicodeDecodeError, configparser.Error):
            return {}
        if not parser.has_section("General"):
            return {}
        data = {}
        for key, value in parser.items("General"):
            # QSettings bọc chuỗi trong dấu nháy kép và escape "\" khi cần.
            if len(value) >= 2 and value.startswith('"') and value.endswith('"'):
                value = value[1:-1].replace('\\"', '"').replace("\\\\", "\\")
            if value in ("true", "false"):
                data[key] = value == "true"
                continue
            try:
                data[key] = int(value) if value.lstrip("-").isdigit() else value
            except ValueError:
                data[key] = value
        return data

    def _flush(self):
        with self._lock:
            try:
                os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
                with open(self.path, "w", encoding="utf-8") as handle:
                    json.dump(self._data, handle, ensure_ascii=False, indent=2)
            except OSError:
                pass

    # ---------------- API giống SettingsStore ----------------
    def get(self, key: str, default: Any = None) -> Any:
        with self._lock:
            return self._data.get(key, default)

    def get_bool(self, key: str, default: bool = False) -> bool:
        value = self.get(key, default)
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.strip().lower() in ("1", "true", "yes", "on")
        return bool(value)

    def get_int(self, key: str, default: int = 0) -> int:
        try:
            return int(self.get(key, default))
        except (TypeError, ValueError):
            return default

    def set(self, **values: Any) -> None:
        with self._lock:
            self._data.update(values)
        self._flush()

    def get_json(self, key: str, default: str):
        value = self.get(key, default)
        if isinstance(value, str):
            try:
                return json.loads(value)
            except ValueError:
                return json.loads(default)
        return value if value is not None else json.loads(default)

    def set_json(self, key: str, value: Any) -> None:
        self.set(**{key: json.dumps(value, ensure_ascii=False)})

    # ---------------- phụ trợ ----------------
    def as_dict(self) -> dict:
        with self._lock:
            return dict(self._data)

