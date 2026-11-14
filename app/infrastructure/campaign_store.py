"""Kho chiến dịch 抽選 dùng chung giữa các thiết bị: `campaigns.json` ở gốc dự án.

Vì sao tách khỏi `web_settings.json`: file đó là cấu hình của **từng máy** (proxy,
số worker, đường dẫn recipe) và bị git-ignore, nên danh sách chiến dịch nằm trong
đó sẽ mất khi chuyển app sang máy khác. Chiến dịch là dữ liệu dùng chung, phải đi
theo dự án như `recipes/*.json` — nên ở đây là file JSON riêng, **được commit**.

Ghi nhận đăng ký (`campaign_signups`) thì vẫn ở `web_settings.json` của từng máy:
nó gắn với email tài khoản, mà mỗi máy giữ một bộ tài khoản riêng.

Định dạng file (dễ đọc và diff trong git):

```json
{
  "version": 1,
  "updated_at": "2026-11-14 08:30:00",
  "campaigns": [
    {"name": "…", "url": "https://…", "opens_at": "2026-11-21 11:00",
     "closes_at": "2026-11-22 23:59", "notes": "…"}
  ]
}
```

Đọc được cả dạng cũ để lần chạy đầu tự chuyển dữ liệu: một mảng JSON thuần, hoặc
khoá `campaigns` của `web_settings.json` (xem `migrate_legacy_campaigns`).
"""
import json
import os
import threading
from datetime import datetime

from app.config import CAMPAIGNS_FILE
from app.domain.campaigns import normalize_campaign_time

FORMAT_VERSION = 1
# Trường của một chiến dịch; trường lạ do người dùng tự thêm trong file vẫn được
# giữ nguyên khi ghi lại (không xoá dữ liệu của ai).
CAMPAIGN_FIELDS = ("name", "url", "opens_at", "closes_at", "notes")


def normalize_campaigns(items):
    """Chuẩn hoá danh sách chiến dịch đọc từ file: chuỗi đã trim, bỏ dòng rỗng."""
    result = []
    for raw in items or []:
        if not isinstance(raw, dict):
            continue
        campaign = {field: str(raw.get(field) or "").strip() for field in CAMPAIGN_FIELDS}
        # Ô chọn ngày/giờ của UI gửi "YYYY-MM-DDTHH:MM"; file chung chỉ giữ một dạng
        # duy nhất để diff git sạch và so sánh chuỗi được.
        campaign["opens_at"] = normalize_campaign_time(campaign["opens_at"])
        campaign["closes_at"] = normalize_campaign_time(campaign["closes_at"])
        if not campaign["name"] and not campaign["url"]:
            continue
        for key, value in raw.items():
            if key not in campaign:
                campaign[str(key)] = value
        result.append(campaign)
    return result


class CampaignStore:
    """Đọc/ghi `campaigns.json`; an toàn khi nhiều thread cùng dùng."""

    def __init__(self, path: str = CAMPAIGNS_FILE):
        self.path = path
        self._lock = threading.RLock()
        self._seen_mtime = None

    # ---------------- trạng thái file ----------------
    def exists(self) -> bool:
        return os.path.isfile(self.path)

    def _mtime(self):
        try:
            return os.path.getmtime(self.path)
        except OSError:
            return None

    def changed(self) -> bool:
        """True khi file bị sửa từ ngoài (git pull, sửa tay) kể từ lần đọc trước."""
        return self._mtime() != self._seen_mtime

    # ---------------- nạp/ghi ----------------
    def _read(self):
        if not self.exists():
            return []
        try:
            with open(self.path, "r", encoding="utf-8-sig") as handle:
                data = json.load(handle)
        except (OSError, ValueError):
            return []
        if isinstance(data, dict):
            data = data.get("campaigns") or []
        return data if isinstance(data, list) else []

    def load(self):
        """Danh sách chiến dịch đã chuẩn hoá; file thiếu/hỏng thì trả danh sách rỗng."""
        with self._lock:
            self._seen_mtime = self._mtime()
            raw = self._read()
        return normalize_campaigns(raw)

    def save(self, campaigns) -> int:
        """Ghi cả danh sách; trả về số dòng đã ghi (0 khi không ghi được)."""
        items = normalize_campaigns(campaigns)
        payload = {
            "version": FORMAT_VERSION,
            "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "campaigns": items,
        }
        with self._lock:
            try:
                os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
                with open(self.path, "w", encoding="utf-8") as handle:
                    json.dump(payload, handle, ensure_ascii=False, indent=2)
                    handle.write("\n")
            except OSError:
                return 0
            self._seen_mtime = self._mtime()
        return len(items)


def migrate_legacy_campaigns(store: CampaignStore, settings) -> int:
    """Chuyển danh sách chiến dịch của bản cũ (`web_settings.json`) sang file chung.

    Chỉ chạy một lần: sau khi xong đánh dấu `campaigns_migrated` để danh sách cũ
    không quay lại khi người dùng cố ý xoá hết chiến dịch. Trả về số chiến dịch đã
    chuyển (0 = không có gì để chuyển).
    """
    if settings.get_bool("campaigns_migrated", False):
        return 0
    if store.exists() and store.load():
        # Đã có file chung rồi thì file đó là nguồn đúng, không ghi đè.
        settings.set(campaigns_migrated=True)
        return 0
    legacy = settings.get_json("campaigns", "[]")
    if not isinstance(legacy, list) or not legacy:
        settings.set(campaigns_migrated=True)
        return 0
    count = store.save(legacy)
    settings.set(campaigns_migrated=True)
    return count
