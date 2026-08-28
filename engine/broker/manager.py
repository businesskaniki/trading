from __future__ import annotations

from typing import Any

from engine.broker.models import (
    BrokerAccount,
    BrokerConnection,
    BrokerConnectionStatus,
    BrokerDeal,
    BrokerOrder,
    BrokerOrderRequest,
    BrokerOrderResult,
    BrokerPosition,
    BrokerSymbol,
    BrokerTick,
)


class BrokerManager:
    """
    Engine-facing broker gateway.

    The engine talks to this class rather than directly communicating
    with MT5 or the MT5 bridge.
    """

    def __init__(
        self,
        adapter: Any,
    ):
        self.adapter = adapter

    async def connect(self) -> BrokerConnection:
        result = await self.adapter.connect()

        if isinstance(result, BrokerConnection):
            return result

        return BrokerConnection(
            broker="mt5",
            status=BrokerConnectionStatus.CONNECTED,
            message="Broker connected successfully.",
        )

    async def disconnect(self) -> None:
        await self.adapter.disconnect()

    async def health(self) -> BrokerConnection:
        result = await self.adapter.health()

        if isinstance(result, BrokerConnection):
            return result

        return BrokerConnection(
            broker="mt5",
            status=BrokerConnectionStatus.CONNECTED,
        )

    async def get_account(self) -> BrokerAccount:
        return await self.adapter.get_account()

    async def get_symbol(
        self,
        symbol: str,
    ) -> BrokerSymbol:
        return await self.adapter.get_symbol(symbol)

    async def get_symbols(self) -> list[BrokerSymbol]:
        return await self.adapter.get_symbols()

    async def get_tick(
        self,
        symbol: str,
    ) -> BrokerTick:
        return await self.adapter.get_tick(symbol)

    async def get_orders(self) -> list[BrokerOrder]:
        return await self.adapter.get_orders()

    async def get_positions(self) -> list[BrokerPosition]:
        return await self.adapter.get_positions()

    async def get_deals(
        self,
        start: Any = None,
        end: Any = None,
    ) -> list[BrokerDeal]:
        return await self.adapter.get_deals(
            start=start,
            end=end,
        )

    async def place_order(
        self,
        request: BrokerOrderRequest,
    ) -> BrokerOrderResult:
        return await self.adapter.place_order(request)

    async def cancel_order(
        self,
        ticket: int | str,
    ) -> BrokerOrderResult:
        return await self.adapter.cancel_order(ticket)

    async def close_position(
        self,
        ticket: int | str,
    ) -> BrokerOrderResult:
        return await self.adapter.close_position(ticket)
