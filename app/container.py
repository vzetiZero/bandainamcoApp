"""Chai (composition root): dựng hạ tầng và services một lần, UI chỉ nhận chai.

Mọi phụ thuộc mạng/dữ liệu đều đi qua đây nên test thay được bằng đối tượng giả
mà không phải sửa code UI hay logic nghiệp vụ.
"""
from dataclasses import dataclass
from typing import Callable, Optional

import requests

from app.config import BROWSER_RECIPE_FILE, DATA_FILE, SETTINGS_FILE
from app.infrastructure.account_repository import AccountRepository
from app.infrastructure.bandai_auth import BandaiAuthClient
from app.infrastructure.bandai_name import BandaiNameClient
from app.infrastructure.checkout_store import CheckoutStore
from app.infrastructure.settings_store import SettingsStore
from app.services.account_service import AccountService
from app.services.browser_campaign_service import BrowserCampaignService
from app.services.campaign_service import CampaignService
from proxy_manager import new_session


@dataclass
class Container:
    settings: SettingsStore
    auth_client: BandaiAuthClient
    name_client: BandaiNameClient
    account_repository: AccountRepository
    account_service: AccountService
    campaign_service: CampaignService
    # Chạy chiến dịch bằng trình duyệt (Playwright + chrome-devtools-mcp).
    browser_service: BrowserCampaignService
    # Hồ sơ đặt hàng/thẻ do người dùng nhập trong UI (mã hoá DPAPI).
    checkout_store: CheckoutStore


def build_container(data_file: str = DATA_FILE,
                    session_factory: Optional[Callable[[], requests.Session]] = None,
                    on_log: Optional[Callable[[str], None]] = None,
                    settings: Optional[SettingsStore] = None,
                    recipe_path: str = BROWSER_RECIPE_FILE) -> Container:
    """
    Nối các phụ thuộc thật.

    `session_factory` và `on_log` là chỗ để test thay thế: truyền factory trả
    session giả thì toàn bộ client đi qua đó, không cần đụng tới UI.
    """
    factory = session_factory or new_session
    settings = settings or SettingsStore(path=SETTINGS_FILE)
    auth_client = BandaiAuthClient(session_factory=factory)
    repository = AccountRepository(path=data_file, on_change=on_log)
    campaign_service = CampaignService(settings)
    # Một store dùng chung: UI ghi, BrowserCampaignService đọc khi chạy.
    checkout_store = CheckoutStore(on_log=on_log)
    return Container(
        settings=settings,
        auth_client=auth_client,
        name_client=BandaiNameClient(auth_client=auth_client),
        account_repository=repository,
        account_service=AccountService(repository),
        campaign_service=campaign_service,
        browser_service=BrowserCampaignService(
            campaign_service=campaign_service,
            recipe_path=recipe_path,
            # Mặc định chưa gửi: UI bật theo cấu hình đã lưu trước khi chạy.
            submit=False,
            checkout_store=checkout_store,
        ),
        checkout_store=checkout_store,
    )
