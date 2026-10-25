"""Chai (composition root): dựng hạ tầng và services một lần, UI chỉ nhận chai.

Mọi phụ thuộc mạng/dữ liệu đều đi qua đây nên test thay được bằng đối tượng giả
mà không phải sửa code UI hay logic nghiệp vụ.
"""
from dataclasses import dataclass
from typing import Callable, Optional

import requests

from app.config import DATA_FILE
from app.infrastructure.account_repository import AccountRepository
from app.infrastructure.bandai_auth import BandaiAuthClient
from app.infrastructure.settings_store import SettingsStore
from proxy_manager import new_session


@dataclass
class Container:
    auth_client: BandaiAuthClient
    accounts: AccountRepository
    settings: SettingsStore


def build_container(data_file: str = DATA_FILE,
                    session_factory: Optional[Callable[[], requests.Session]] = None,
                    on_log: Optional[Callable[[str], None]] = None,
                    settings: Optional[SettingsStore] = None) -> Container:
    factory = session_factory or new_session
    return Container(
        auth_client=BandaiAuthClient(session_factory=factory),
        accounts=AccountRepository(path=data_file, on_change=on_log),
        settings=settings or SettingsStore(),
    )
