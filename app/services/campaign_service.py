"""Nghiệp vụ chiến dịch 抽選: danh sách chiến dịch và ghi nhận tài khoản đã đăng ký."""
from datetime import datetime
from typing import List, Optional
from urllib.parse import urlparse

CAMPAIGN_KEY = "%s|%s"


class CampaignService:
    """Lưu chiến dịch trong QSettings qua SettingsStore; UI chỉ hiển thị."""

    def __init__(self, settings):
        self.settings = settings
        self.campaigns: List[dict] = []
        self.signups: dict = {}

    def load(self):
        campaigns = self.settings.get_json("campaigns", "[]")
        self.campaigns = campaigns if isinstance(campaigns, list) else []
        signups = self.settings.get_json("campaign_signups", "{}")
        self.signups = signups if isinstance(signups, dict) else {}

    def save(self):
        self.settings.set_json("campaigns", self.campaigns)
        self.prune_orphan_signups()

    def save_signups(self):
        self.settings.set_json("campaign_signups", self.signups)

    @staticmethod
    def key(campaign: dict) -> str:
        """Khoá ổn định của chiến dịch, không đổi khi thứ tự dòng thay đổi."""
        return CAMPAIGN_KEY % (campaign.get("name", ""), campaign.get("url", ""))

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

    def mark(self, campaign: dict, email: str) -> bool:
        """Ghi nhận một tài khoản cho chiến dịch; False khi đã ghi nhận rồi."""
        if self.is_registered(campaign, email):
            return False
        entries = self.signups.setdefault(self.key(campaign), [])
        entries.append({"email": email,
                        "at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")})
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
