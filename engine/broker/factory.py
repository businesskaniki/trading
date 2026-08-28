from __future__ import annotations

from typing import Any

from backend.app.broker.mt5 import MT5Adapter
from engine.broker.exceptions import BrokerConfigurationError
from engine.broker.manager import BrokerManager


class BrokerFactory:

    @staticmethod
    def create(
        broker: str,
        *,
        bridge_url: str,
        timeout: float = 10.0,
        **kwargs: Any,
    ) -> BrokerManager:

        if not broker:
            raise BrokerConfigurationError("Broker identifier is required.")

        broker_name = broker.strip().lower()

        if broker_name == "mt5":

            adapter = MT5Adapter(
                bridge_url=bridge_url,
                timeout=timeout,
                **kwargs,
            )

            return BrokerManager(
                adapter=adapter,
            )

        raise BrokerConfigurationError(f"Unsupported broker: {broker}")


def create_broker(
    broker: str,
    *,
    bridge_url: str,
    timeout: float = 10.0,
    **kwargs: Any,
) -> BrokerManager:

    return BrokerFactory.create(
        broker,
        bridge_url=bridge_url,
        timeout=timeout,
        **kwargs,
    )
