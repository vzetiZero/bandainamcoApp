"""Lưu hồ sơ đặt hàng + thẻ thanh toán do người dùng nhập.

Vì sao tách khỏi `ui_settings.ini`: đây là dữ liệu nhạy cảm. File riêng
`checkout_profile.json`, git-ignored, và **từng giá trị được mã hoá bằng DPAPI
của Windows** (`CryptProtectData`) nên chỉ tài khoản Windows đang đăng nhập giải
mã được. Nếu DPAPI không dùng được (không phải Windows/lỗi) thì vẫn lưu được
nhưng kèm cờ `encrypted: false` để UI cảnh báo rõ là đang ở dạng chữ thường.

Không hàm nào ở đây ghi log giá trị thẻ; nơi gọi chỉ dùng `checkout.summary()`.
"""
import base64
import ctypes
import json
import os
from ctypes import wintypes

from app.config import CHECKOUT_FILE
from app.domain import checkout as domain

DEFAULT_PROFILE = "default"


class _DataBlob(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]


def _make_blob(data):
    """Tạo DATA_BLOB và giữ buffer sống trong lúc gọi API (nếu GC thì segfault)."""
    buffer = ctypes.create_string_buffer(data, len(data))
    return _DataBlob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_char))), buffer


def _dpapi(data, protect):
    """Gọi CryptProtectData/CryptUnprotectData; None nếu không dùng được."""
    if os.name != "nt":
        return None
    try:
        crypt32 = ctypes.windll.crypt32
        kernel32 = ctypes.windll.kernel32
        blob_in, keep_in = _make_blob(data)
        blob_out = _DataBlob()
        if protect:
            ok = crypt32.CryptProtectData(ctypes.byref(blob_in), None, None, None, None, 0,
                                          ctypes.byref(blob_out))
        else:
            ok = crypt32.CryptUnprotectData(ctypes.byref(blob_in), None, None, None, None, 0,
                                            ctypes.byref(blob_out))
        del keep_in
        if not ok:
            return None
        try:
            return ctypes.string_at(blob_out.pbData, blob_out.cbData)
        finally:
            kernel32.LocalFree(blob_out.pbData)
    except Exception:  # noqa: BLE001 - thiếu DPAPI thì rơi về chế độ chữ thường
        return None


def encrypt_text(text):
    """Trả (giá trị để ghi file, đã_mã_hoá?)."""
    if not text:
        return "", True
    raw = _dpapi(str(text).encode("utf-8"), protect=True)
    if raw is None:
        return str(text), False
    return base64.b64encode(raw).decode("ascii"), True


def decrypt_text(text, encrypted):
    if not text:
        return ""
    if not encrypted:
        return str(text)
    try:
        raw = _dpapi(base64.b64decode(str(text).encode("ascii")), protect=False)
    except (ValueError, TypeError):
        return ""
    return raw.decode("utf-8", "replace") if raw is not None else ""


class CheckoutStore:
    """Đọc/ghi hồ sơ theo tên (mặc định 'default')."""

    def __init__(self, path=CHECKOUT_FILE, on_log=None):
        self.path = path
        self._log = on_log or (lambda message: None)
        self._cache = None

    # ---------------- đọc/ghi ----------------
    def load_all(self):
        if self._cache is not None:
            return self._cache
        profiles = {}
        if os.path.exists(self.path):
            try:
                with open(self.path, "r", encoding="utf-8") as handle:
                    raw = json.load(handle)
            except (OSError, ValueError) as exc:
                self._log("Không đọc được %s: %s" % (self.path, exc))
                raw = {}
            for name, item in (raw or {}).items():
                if not isinstance(item, dict):
                    continue
                encrypted = bool(item.get("encrypted", True))
                profile = {field: decrypt_text(item.get(field) or "", encrypted)
                           for field in domain.ALL_FIELDS}
                profile["building_none"] = str(item.get("building_none_value") or "") == "1"
                profile["encrypted"] = encrypted
                profiles[name] = profile
        self._cache = profiles
        return profiles

    def load(self, name=DEFAULT_PROFILE):
        return dict(self.load_all().get(name) or {})

    def status(self, name=DEFAULT_PROFILE):
        """'đã mã hoá' / 'chưa mã hoá' / 'chưa có' — để UI hiện cảnh báo."""
        profile = self.load(name)
        if not profile:
            return "chưa có"
        return "đã mã hoá" if profile.get("encrypted", True) else "CHƯA mã hoá"

    def save(self, data, name=DEFAULT_PROFILE):
        """Ghi hồ sơ; trả (ok, message)."""
        clean = domain.clean(data)
        errors = domain.validate(clean)
        if errors:
            return False, "\n".join(errors)
        profiles = dict(self.load_all())
        profiles[name] = clean
        payload = {}
        plaintext_fields = []
        for key, profile in profiles.items():
            item = {}
            for field in domain.ALL_FIELDS:
                value, encrypted = encrypt_text(profile.get(field, ""))
                item[field] = value
                if not encrypted and profile.get(field):
                    plaintext_fields.append(field)
            item["building_none_value"] = "1" if profile.get("building_none") else ""
            item["encrypted"] = not plaintext_fields
            payload[key] = item
        if not self._write(payload):
            return False, "Không ghi được %s" % self.path
        self._cache = None
        if plaintext_fields:
            return True, ("Đã lưu NHƯNG DPAPI không mã hoá được (%s) — dữ liệu đang ở dạng "
                          "chữ thường trong %s"
                          % (", ".join(sorted(set(plaintext_fields))), self.path))
        return True, "Đã lưu (mã hoá DPAPI của Windows): %s" % domain.summary(clean)

    def clear(self, name=DEFAULT_PROFILE):
        profiles = dict(self.load_all())
        if profiles.pop(name, None) is None:
            return False
        payload = {}
        for key, profile in profiles.items():
            item = {}
            for field in domain.ALL_FIELDS:
                item[field], _ = encrypt_text(profile.get(field, ""))
            item["building_none_value"] = "1" if profile.get("building_none") else ""
            item["encrypted"] = True
            payload[key] = item
        self._cache = None
        return self._write(payload)

    # ---------------- nội bộ ----------------
    def _write(self, payload):
        try:
            folder = os.path.dirname(self.path)
            if folder:
                os.makedirs(folder, exist_ok=True)
            with open(self.path, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, indent=2)
            if os.name == "nt":
                # Thắt quyền: chỉ user hiện tại đọc/ghi (DPAPI vẫn là lớp chính).
                try:
                    os.system('icacls "%s" /inheritance:r /grant:r "%%USERNAME%%:F" >nul 2>&1'
                              % self.path)
                except Exception:  # noqa: BLE001
                    pass
            return True
        except OSError as exc:
            self._log("Không ghi được %s: %s" % (self.path, exc))
            return False
