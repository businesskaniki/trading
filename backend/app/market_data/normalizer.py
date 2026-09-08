from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .models import MarketCandle, MarketTick


class MarketDataNormalizationError(Exception):
    """
    Raised when broker market-data cannot be converted into
    an AQE-native market-data object.
    """

    pass


class MarketDataNormalizer:
    """
    Converts raw MT5 Bridge responses into AQE-native market data.

    The rest of AQE should not need to know the exact JSON structure
    returned by the MT5 Bridge.
    """

    @staticmethod
    def tick(
        data: Mapping[str, Any],
        symbol: str | None = None,
    ) -> MarketTick:
        """
        Normalize a bridge tick response.
        """

        if not isinstance(data, Mapping):
            raise MarketDataNormalizationError("Tick response must be a mapping.")

        resolved_symbol = str(symbol or data.get("symbol", "")).strip()

        if not resolved_symbol:
            raise MarketDataNormalizationError("Market tick does not contain a symbol.")

        try:
            timestamp = int(
                data.get(
                    "timestamp",
                    data.get(
                        "time",
                        0,
                    ),
                )
            )

            bid = float(
                data.get(
                    "bid",
                    0.0,
                )
            )

            ask = float(
                data.get(
                    "ask",
                    0.0,
                )
            )

            last = float(
                data.get(
                    "last",
                    0.0,
                )
            )

            volume = int(
                data.get(
                    "volume",
                    0,
                )
            )

            volume_real = float(
                data.get(
                    "volume_real",
                    0.0,
                )
            )

        except (
            TypeError,
            ValueError,
        ) as exc:
            raise MarketDataNormalizationError(
                f"Invalid tick data for {resolved_symbol}."
            ) from exc

        tick = MarketTick(
            symbol=resolved_symbol,
            timestamp=timestamp,
            bid=bid,
            ask=ask,
            last=last,
            volume=volume,
            volume_real=volume_real,
        )

        if not tick.is_valid():
            raise MarketDataNormalizationError(
                f"Invalid normalized tick for {resolved_symbol}."
            )

        return tick

    @staticmethod
    def candle(
        data: Mapping[str, Any],
        symbol: str,
        timeframe: str,
    ) -> MarketCandle:
        """
        Normalize a single bridge candle response.
        """

        if not isinstance(data, Mapping):
            raise MarketDataNormalizationError("Candle response must be a mapping.")

        resolved_symbol = symbol.strip()
        resolved_timeframe = timeframe.strip().upper()

        if not resolved_symbol:
            raise MarketDataNormalizationError("Candle symbol cannot be empty.")

        if not resolved_timeframe:
            raise MarketDataNormalizationError("Candle timeframe cannot be empty.")

        try:
            timestamp = int(
                data.get(
                    "timestamp",
                    data.get(
                        "time",
                        0,
                    ),
                )
            )

            open_price = float(
                data.get(
                    "open",
                    0.0,
                )
            )

            high = float(
                data.get(
                    "high",
                    0.0,
                )
            )

            low = float(
                data.get(
                    "low",
                    0.0,
                )
            )

            close = float(
                data.get(
                    "close",
                    0.0,
                )
            )

            volume = int(
                data.get(
                    "volume",
                    data.get(
                        "tick_volume",
                        0,
                    ),
                )
            )

            spread = int(
                data.get(
                    "spread",
                    0,
                )
            )

        except (
            TypeError,
            ValueError,
        ) as exc:
            raise MarketDataNormalizationError(
                f"Invalid candle data for " f"{resolved_symbol} {resolved_timeframe}."
            ) from exc

        candle = MarketCandle(
            symbol=resolved_symbol,
            timeframe=resolved_timeframe,
            timestamp=timestamp,
            open=open_price,
            high=high,
            low=low,
            close=close,
            volume=volume,
            spread=spread,
        )

        if not candle.is_valid():
            raise MarketDataNormalizationError(
                f"Invalid normalized candle for "
                f"{resolved_symbol} {resolved_timeframe}."
            )

        return candle

    @classmethod
    def candles(
        cls,
        data: Any,
        symbol: str,
        timeframe: str,
    ) -> list[MarketCandle]:
        """
        Normalize a list of bridge candle responses.
        """

        if not isinstance(data, list):
            raise MarketDataNormalizationError("Candle response must be a list.")

        result: list[MarketCandle] = []

        for index, item in enumerate(data):

            try:
                candle = cls.candle(
                    data=item,
                    symbol=symbol,
                    timeframe=timeframe,
                )

            except MarketDataNormalizationError as exc:
                raise MarketDataNormalizationError(
                    f"Invalid candle at index {index}: {exc}"
                ) from exc

            result.append(candle)

        return result
