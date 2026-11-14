"""Nghiệp vụ chiến dịch 抽選: danh sách dùng chung, ghi nhận đăng ký theo từng máy.

Hai kho dữ liệu, cố ý tách nhau:

- `store`       -> `campaigns.json` ở gốc dự án, **được git track**: chuyển app sang
  máy khác là có nguyên danh sách chiến dịch, không phải nhập lại.
- `signup_store` -> `web_settings.json` của từng máy: ghi nhận đăng ký gắn với email
  tài khoản, mà mỗi máy giữ một bộ tài khoản khác nhau (nên không chia sẻ).

Trạng thái chiến dịch không lưu ở đây — suy ra từ thời gian (`app/domain/campaigns`).
"""
from datetime import datetime
from typing import List, Optional
from urllib.parse import urlparse

CAMPAIGN_KEY = "%s|%s"
SIGNUPS_KEY = "campaign_signups"


class CampaignService:
    """Lưu chiến dịch trong `campaigns.json` (chung) và signups trong settings (máy)."""

    def __init__(self, campaign_store, signup_store=None):
        self.store = campaign_store
        # Không truyền `signup_store` thì dùng chung một store (một file duy nhất).
        self.signup_store = signup_store if signup_store is not None else campaign_store
        self.campaigns: List[dict] = []
        self.signups: dict = {}

    # ---------------- nạp/ghi ----------------
    def load(self):
        self.campaigns = self._dedupe(self.store.load())
        signups = self.signup_store.get_json(SIGNUPS_KEY, "{}")
        self.signups = signups if isinstance(signups, dict) else {}
        self._migrate_signup_keys()

    def reload_if_changed(self) -> bool:
        """Nạp lại khi `campaigns.json` bị sửa từ ngoài (git pull, sửa tay)."""
        check = getattr(self.store, "changed", None)
        if check is None or not check():
            return False
        self.load()
        return True

    def save(self):
        self.store.save(self.campaigns)
        self.prune_orphan_signups()

    def save_signups(self):
        self.signup_store.set_json(SIGNUPS_KEY, self.signups)

    def _dedupe(self, campaigns) -> List[dict]:
        """Bỏ dòng trùng khoá (do gộp file khi git pull); giữ dòng xuất hiện sau."""
        last = {}
        for index, campaign in enumerate(campaigns):
            last[self.key(campaign)] = index
        if len(last) == len(campaigns):
            return list(campaigns)
        return [campaign for index, campaign in enumerate(campaigns)
                if last[self.key(campaign)] == index]

    @staticmethod
    def key(campaign: dict) -> str:
        """Khoá ổn định của chiến dịch: dùng LINK để đổi tên không mất ghi nhận."""
        url = str(campaign.get("url") or "").strip().lower()
        if url:
            return url
        return str(campaign.get("name") or "").strip().lower()

    def _migrate_signup_keys(self):
        """Chuyển ghi nhận của khoá cũ `tên|link` sang khoá link (giữ nguyên dữ liệu)."""
        changed = False
        for campaign in self.campaigns:
            new_key = self.key(campaign)
            if not new_key or new_key in self.signups:
                continue
            legacy = CAMPAIGN_KEY % (campaign.get("name", ""), campaign.get("url", ""))
            entries = self.signups.pop(legacy, None)
            if entries:
                self.signups[new_key] = entries
                changed = True
        if changed:
            self.save_signups()

    @staticmethod
    def is_valid(campaign: dict) -> bool:
        return bool(campaign.get("name")) and urlparse(campaign.get("url", "")).scheme in {"http", "https"}

    def add(self, campaign: dict):
        self.campaigns.append(campaign)
        self.save()

    def update(self, row: int, campaign: dict) -> bool:
        if not 0 <= row < len(self.campaigns):
            return False
        self.campaigns[row] = campaign
        self.save()
        return True

    def remove(self, row: int) -> Optional[dict]:
        if not 0 <= row < len(self.campaigns):
            return None
        removed = self.campaigns.pop(row)
        self.save()
        return removed

    def prune_orphan_signups(self):
        """Xoá ghi nhận của chiến dịch đã bị xoá, để dữ liệu không phình vô hạn."""
        live = {self.key(campaign) for campaign in self.campaigns}
        stale = [key for key in self.signups if key not in live]
        for key in stale:
            del self.signups[key]
        if stale:
            self.save_signups()
        return len(stale)

    def signups_for(self, campaign: dict) -> List[dict]:
        return list(self.signups.get(self.key(campaign), []))

    def is_registered(self, campaign: dict, email: str) -> bool:
        return any(entry.get("email") == email for entry in self.signups_for(campaign))

    def mark(self, campaign: dict, email: str, note: str = "") -> bool:
        """Ghi nhận một tài khoản cho chiến dịch; False khi đã ghi nhận rồi.

        `note` để phân biệt "đăng ký mới" với "đã mua trước đó" trong danh sách.
        """
        if self.is_registered(campaign, email):
            return False
        entries = self.signups.setdefault(self.key(campaign), [])
        entry = {"email": email,
                 "at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
        if note:
            entry["note"] = note
        entries.append(entry)
        self.save_signups()
        return True

    def unmark(self, campaign: dict, email: str) -> bool:
        """Bỏ ghi nhận; False khi tài khoản chưa từng được ghi nhận cho chiến dịch."""
        key = self.key(campaign)
        entries = self.signups.get(key, [])
        kept = [entry for entry in entries if entry.get("email") != email]
        if len(kept) == len(entries):
            return False
        self.signups[key] = kept
        self.save_signups()
        return True
