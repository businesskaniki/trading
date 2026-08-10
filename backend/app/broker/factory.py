from app.core.config import settings
from app.broker.base import BrokerAdapter
from app.broker.mt5.adapter import MT5Adapter


def get_broker_adapter(broker: str) -> BrokerAdapter:
    """
    Create and return the appropriate broker adapter.
    """

    broker = broker.lower().strip()

    if broker == "mt5":
        return MT5Adapter(
            bridge_url=settings.MT5_BRIDGE_URL
        )

    raise ValueError(
        f"Unsupported broker: {broker}"
    )