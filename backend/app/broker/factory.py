from __future__ import annotations

from uuid import UUID

from app.broker.base import BrokerAdapter
from app.broker.mt5.adapter import MT5Adapter
from app.broker.paper.adapter import PaperBroker
from app.core.config import settings


def get_broker_adapter(
    broker: str,
    *,
    bridge_url: str | None = None,
    account_id: UUID | str | None = None,
) -> BrokerAdapter:
    """
    Create the broker adapter for a specific trading account.

    The factory is responsible only for constructing the appropriate
    broker implementation.

    It does NOT:

        - authenticate the trading account
        - retrieve credentials
        - decrypt credentials
        - connect to the broker
        - place orders
        - perform risk checks
        - access PostgreSQL

    Broker credentials are supplied separately through the adapter's
    connect() method at runtime.

    Args:
        broker:
            Broker identifier, for example "mt5" or "paper".

        bridge_url:
            Optional MT5 Bridge URL. When omitted, the configured
            application bridge URL is used.

        account_id:
            AQE trading-account identifier. This is used to bind
            account-specific broker adapters to the correct account.

    Returns:
        A broker-specific BrokerAdapter instance.

    Raises:
        ValueError:
            If the broker type is unsupported.
    """

    broker_name = broker.lower().strip()

    if not broker_name:
        raise ValueError("Broker type cannot be empty.")

    if broker_name == "mt5":
        return MT5Adapter(
            bridge_url=(bridge_url or settings.MT5_BRIDGE_URL),
            account_id=(str(account_id) if account_id is not None else None),
        )

    if broker_name == "paper":
        return PaperBroker()

    raise ValueError(f"Unsupported broker: {broker!r}")
