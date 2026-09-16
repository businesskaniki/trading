from __future__ import annotations

from typing import Any

from app.events.bus import event_bus
from app.events.market import MarketCandleEvent, MarketTickEvent
from app.services.mt5_bridge_service import (
    MT5BridgeError,
    MT5BridgeService,
)

from .models import MarketCandle, MarketTick
from .normalizer import (
    MarketDataNormalizationError,
    MarketDataNormalizer,
)


class MarketDataError(Exception):
    """Raised when AQE market-data operations fail."""

    pass


class MarketDataService:
    """
    AQE application-level market-data service.

    Responsibilities:

    - Communicate with the MT5 bridge.
    - Normalize broker data.
    - Return MarketTick / MarketCandle objects.
    - Publish market-data events.

    This service does not know anything about strategies,
    risk management, or order execution.
    """

    def __init__(
        self,
        bridge: MT5BridgeService | None = None,
        normalizer: MarketDataNormalizer | None = None,
    ) -> None:
        self.bridge = bridge or MT5BridgeService()
        self.normalizer = normalizer or MarketDataNormalizer()

    # ------------------------------------------------------------------
    # TICKS
    # ------------------------------------------------------------------

    async def get_tick(
        self,
        symbol: str,
        publish_event: bool = True,
    ) -> MarketTick:
        """
        Retrieve and normalize the current broker tick.

        By default, a MarketTickEvent is published after successful
        normalization.

        publish_event=False can be used when a caller only wants
        the data without publishing an event.
        """

        symbol = self._validate_symbol(symbol)

        try:
            data = await self.bridge.get_tick(symbol)

            tick = self.normalizer.tick(
                data=data,
                symbol=symbol,
            )

        except MT5BridgeError as exc:
            raise MarketDataError(
                f"Failed to retrieve tick for {symbol}: {exc}"
            ) from exc

        except MarketDataNormalizationError as exc:
            raise MarketDataError(
                f"Failed to normalize tick for {symbol}: {exc}"
            ) from exc

        if publish_event:
            await self.publish_tick(tick)

        return tick

    async def get_latest_tick(
        self,
        symbol: str,
        publish_event: bool = True,
    ) -> MarketTick:
        """
        Retrieve the latest streamed tick from the MT5 bridge.

        By default, a MarketTickEvent is published after successful
        normalization.
        """

        symbol = self._validate_symbol(symbol)

        try:
            data = await self.bridge.get_latest_tick(symbol)

            tick = self.normalizer.tick(
                data=data,
                symbol=symbol,
            )

        except MT5BridgeError as exc:
            raise MarketDataError(
                f"Failed to retrieve latest tick for {symbol}: {exc}"
            ) from exc

        except MarketDataNormalizationError as exc:
            raise MarketDataError(
                f"Failed to normalize latest tick for {symbol}: {exc}"
            ) from exc

        if publish_event:
            await self.publish_tick(tick)

        return tick

    async def publish_tick(
        self,
        tick: MarketTick,
    ) -> None:
        """
        Publish a normalized market tick to the AQE Event Bus.
        """

        if not isinstance(tick, MarketTick):
            raise MarketDataError("Only MarketTick objects can be published.")

        event = MarketTickEvent.create(
            tick=tick,
        )

        await event_bus.publish(event)

    # ------------------------------------------------------------------
    # SUBSCRIPTIONS
    # ------------------------------------------------------------------

    async def subscribe(
        self,
        symbol: str,
    ) -> dict[str, Any]:
        """
        Subscribe the MT5 bridge market-data service to a symbol.
        """

        symbol = self._validate_symbol(symbol)

        try:
            return await self.bridge.subscribe_symbol(symbol)

        except MT5BridgeError as exc:
            raise MarketDataError(f"Failed to subscribe to {symbol}: {exc}") from exc

    async def unsubscribe(
        self,
        symbol: str,
    ) -> dict[str, Any]:
        """
        Remove a symbol from the MT5 bridge subscription set.
        """

        symbol = self._validate_symbol(symbol)

        try:
            return await self.bridge.unsubscribe_symbol(symbol)

        except MT5BridgeError as exc:
            raise MarketDataError(
                f"Failed to unsubscribe from {symbol}: {exc}"
            ) from exc

    async def subscriptions(self) -> dict[str, Any]:
        """
        Retrieve the current bridge market-data subscriptions.
        """

        try:
            response = await self.bridge.get_subscriptions()

            if not isinstance(response, dict):
                raise MarketDataError(
                    "MT5 bridge returned an invalid " "subscriptions response."
                )

            return response

        except MT5BridgeError as exc:
            raise MarketDataError(
                "Failed to retrieve market-data subscriptions: " f"{exc}"
            ) from exc

    # ------------------------------------------------------------------
    # CANDLES
    # ------------------------------------------------------------------

    async def get_candles(
        self,
        symbol: str,
        timeframe: str = "M15",
        count: int = 200,
        publish_event: bool = False,
    ) -> list[MarketCandle]:
        """
        Retrieve and normalize historical candles.

        Historical candles are not published individually by default.

        publish_event=True may be used by a future candle-streaming
        component when candles represent newly completed market data.
        """

        symbol = self._validate_symbol(symbol)

        timeframe = timeframe.strip().upper()

        if not timeframe:
            raise MarketDataError("Timeframe cannot be empty.")

        if count <= 0:
            raise MarketDataError("Candle count must be greater than zero.")

        try:
            data = await self.bridge.get_candles(
                symbol=symbol,
                timeframe=timeframe,
                count=count,
            )

            candles = self.normalizer.candles(
                data=data,
                symbol=symbol,
                timeframe=timeframe,
            )

        except MT5BridgeError as exc:
            raise MarketDataError(
                f"Failed to retrieve candles for {symbol}: {exc}"
            ) from exc

        except MarketDataNormalizationError as exc:
            raise MarketDataError(
                f"Failed to normalize candles for {symbol}: {exc}"
            ) from exc

        if publish_event:
            for candle in candles:
                await self.publish_candle(candle)

        return candles

    async def publish_candle(
        self,
        candle: MarketCandle,
    ) -> None:
        """
        Publish a normalized candle to the AQE Event Bus.
        """

        if not isinstance(candle, MarketCandle):
            raise MarketDataError("Only MarketCandle objects can be published.")

        event = MarketCandleEvent.create(
            candle=candle,
        )

        await event_bus.publish(event)

    # ------------------------------------------------------------------
    # VALIDATION
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_symbol(
        symbol: str,
    ) -> str:
        """
        Validate a broker symbol while preserving its exact casing.
        """

        if not isinstance(symbol, str):
            raise MarketDataError("Symbol must be a string.")

        symbol = symbol.strip()

        if not symbol:
            raise MarketDataError("Symbol cannot be empty.")

        return symbol


market_data_service = MarketDataService()
