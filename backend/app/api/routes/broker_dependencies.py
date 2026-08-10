from fastapi import Depends

from app.broker.broker_manager import BrokerManager
from app.broker.mt5.adapter import MT5Adapter
from app.core.config import settings


def get_broker_manager() -> BrokerManager:
    adapter = MT5Adapter(
        bridge_url=settings.MT5_BRIDGE_URL,
    )

    return BrokerManager(
        adapter=adapter,
    )