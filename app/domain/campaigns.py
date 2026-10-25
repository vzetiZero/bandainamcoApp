"""Model chiến dịch: mọi trạng thái suy ra từ ngày, không nhập tay."""
from datetime import datetime, timedelta


CAMPAIGN_TIME_FORMATS = ("%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d")
CAMPAIGN_STATUS_UNDETERMINED = "Chưa rõ"
CAMPAIGN_STATUS_NOT_STARTED = "Chưa mở"
CAMPAIGN_STATUS_OPEN = "Đang mở"
CAMPAIGN_STATUS_CLOSED = "Đã đóng"
CAMPAIGN_SOON_WINDOW = timedelta(hours=24)
CAMPAIGN_STATUS_COLORS = {
    CAMPAIGN_STATUS_OPEN: "#28a745",
    CAMPAIGN_STATUS_NOT_STARTED: "#c8860d",
    CAMPAIGN_STATUS_CLOSED: "#8a94a6",
    CAMPAIGN_STATUS_UNDETERMINED: "#8a94a6",
}


def parse_campaign_time(text):
    """Parse 'YYYY-MM-DD HH:MM' and friends into datetime; None when blank or invalid."""
    raw = str(text or "").strip()
    if not raw:
        return None
    for fmt in CAMPAIGN_TIME_FORMATS:
        try:
            return datetime.strptime(raw, fmt)
        except ValueError:
            continue
    return None


def campaign_status(campaign, now=None):
    """Derive a campaign's state from its open/close times."""
    now = now or datetime.now()
    opens_at = parse_campaign_time(campaign.get("opens_at"))
    closes_at = parse_campaign_time(campaign.get("closes_at"))
    if opens_at is None and closes_at is None:
        return CAMPAIGN_STATUS_UNDETERMINED
    if closes_at is not None and closes_at <= now:
        return CAMPAIGN_STATUS_CLOSED
    if opens_at is not None and opens_at > now:
        return CAMPAIGN_STATUS_NOT_STARTED
    return CAMPAIGN_STATUS_OPEN


def format_campaign_remaining(campaign, now=None):
    """Human-readable countdown to the next deadline, or an empty string."""
    now = now or datetime.now()
    opens_at = parse_campaign_time(campaign.get("opens_at"))
    closes_at = parse_campaign_time(campaign.get("closes_at"))
    if campaign_status(campaign, now) == CAMPAIGN_STATUS_UNDETERMINED:
        return ""
    target = opens_at if opens_at and opens_at > now else closes_at
    if target is None:
        return ""
    delta = target - now
    days, seconds = divmod(int(abs(delta).total_seconds()), 86400)
    hours, _ = divmod(seconds, 3600)
    span = "%dd" % days if hours == 0 else ("%dd %dh" % (days, hours) if days else "%dh" % hours)
    return "còn %s" % span if delta.total_seconds() > 0 else "quá hạn %s" % span
