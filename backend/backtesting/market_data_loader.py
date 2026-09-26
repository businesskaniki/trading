from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.database.models.historical_candle import HistoricalCandle

from .engine import BacktestConfig
from .market import BacktestCandle, BacktestMarketData

logger = logging.getLogger(__name__)


class HistoricalMarketDataLoadError(RuntimeError):
    """Raised when historical market data cannot be loaded for a backtest."""


SessionFactory = Callable[[], AsyncSession]


class HistoricalMarketDataLoader:
    """
    Loads persisted historical candles into the backtesting market-data store.

    The database model is intentionally converted into BacktestCandle objects
    so the backtesting engine remains independent of SQLAlchemy.
    """

    def __init__(
        self,
        *,
        session_factory: SessionFactory,
    ) -> None:
        if not callable(session_factory):
            raise TypeError("session_factory must be callable.")

        self._session_factory = session_factory

    async def load(
        self,
        config: BacktestConfig,
    ) -> BacktestMarketData:
        """
        Load historical candles required by a backtest configuration.

        The returned BacktestMarketData contains only candles matching the
        requested symbols, timeframes, and date range.
        """
        try:
            candles = await self._load_candles(config)

            if not candles:
                raise HistoricalMarketDataLoadError(
                    "No historical market data found for backtest: "
                    f"symbols={config.symbols}, "
                    f"timeframes={config.timeframes}, "
                    f"start={config.start}, "
                    f"end={config.end}"
                )

            market_data = BacktestMarketData()
            market_data.add_many(candles)
            market_data.finalize()

            logger.info(
                "Loaded historical market data for backtest: "
                "account_id=%s symbols=%s timeframes=%s candles=%d "
                "start=%s end=%s",
                config.account_id,
                config.symbols,
                config.timeframes,
                len(candles),
                config.start,
                config.end,
            )

            return market_data

        except HistoricalMarketDataLoadError:
            raise

        except Exception as exc:
            logger.exception(
                "Unexpected error while loading historical market data: "
                "account_id=%s symbols=%s timeframes=%s start=%s end=%s",
                config.account_id,
                config.symbols,
                config.timeframes,
                config.start,
                config.end,
            )

            raise HistoricalMarketDataLoadError(
                "Failed to load historical market data."
            ) from exc

    async def _load_candles(
        self,
        config: BacktestConfig,
    ) -> list[BacktestCandle]:
        symbols = tuple(
            str(symbol).strip().upper()
            for symbol in config.symbols
            if str(symbol).strip()
        )

        timeframes = tuple(
            str(timeframe).strip().upper()
            for timeframe in config.timeframes
            if str(timeframe).strip()
        )

        if not symbols:
            raise HistoricalMarketDataLoadError(
                "Backtest requires at least one symbol."
            )

        if not timeframes:
            raise HistoricalMarketDataLoadError(
                "Backtest requires at least one timeframe."
            )

        async with self._session_factory() as session:
            statement: Select[Any] = (
                select(HistoricalCandle)
                .options(joinedload(HistoricalCandle.symbol))
                .where(HistoricalCandle.timeframe.in_(timeframes))
                .order_by(
                    HistoricalCandle.timestamp.asc(),
                    HistoricalCandle.symbol_id.asc(),
                    HistoricalCandle.timeframe.asc(),
                )
            )

            if config.start is not None:
                statement = statement.where(HistoricalCandle.timestamp >= config.start)

            if config.end is not None:
                statement = statement.where(HistoricalCandle.timestamp < config.end)

            result = await session.execute(statement)

            rows = result.scalars().unique().all()

            candles: list[BacktestCandle] = []

            requested_symbols = set(symbols)

            for row in rows:
                symbol = self._extract_symbol(row)

                if symbol not in requested_symbols:
                    continue

                candles.append(self._to_backtest_candle(row))

            return candles

    @staticmethod
    def _extract_symbol(row: HistoricalCandle) -> str:
        """
        Resolve the canonical symbol name from the HistoricalCandle relation.
        """
        symbol = row.symbol

        if symbol is None:
            raise HistoricalMarketDataLoadError(
                "Historical candle has no associated Symbol: "
                f"candle_id={getattr(row, 'id', None)} "
                f"symbol_id={row.symbol_id}"
            )

        symbol_name = getattr(symbol, "symbol", None)

        if symbol_name is None:
            symbol_name = getattr(symbol, "name", None)

        if symbol_name is None:
            raise HistoricalMarketDataLoadError(
                "Unable to resolve symbol name from HistoricalCandle "
                f"symbol relationship: symbol_id={row.symbol_id}"
            )

        normalized = str(symbol_name).strip().upper()

        if not normalized:
            raise HistoricalMarketDataLoadError(
                f"Historical candle has an empty symbol name: "
                f"symbol_id={row.symbol_id}"
            )

        return normalized

    @classmethod
    def _to_backtest_candle(
        cls,
        row: HistoricalCandle,
    ) -> BacktestCandle:
        """
        Convert the SQLAlchemy HistoricalCandle into the backtesting model.
        """
        return BacktestCandle(
            symbol=cls._extract_symbol(row),
            timeframe=str(row.timeframe).strip().upper(),
            timestamp=cls._ensure_datetime(row.timestamp),
            open=cls._decimal(row.open),
            high=cls._decimal(row.high),
            low=cls._decimal(row.low),
            close=cls._decimal(row.close),
            volume=cls._decimal(row.volume),
            spread=cls._decimal(row.spread),
        )

    @staticmethod
    def _ensure_datetime(value: datetime) -> datetime:
        """
        Normalize database timestamps to timezone-aware UTC datetimes.
        """
        if not isinstance(value, datetime):
            raise HistoricalMarketDataLoadError(
                "Historical candle timestamp must be a datetime."
            )

        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)

        return value.astimezone(timezone.utc)

    @staticmethod
    def _decimal(value: Any) -> Decimal:
        """
        Convert SQLAlchemy Numeric values into Decimal safely.
        """
        if value is None:
            return Decimal("0")

        if isinstance(value, Decimal):
            return value

        try:
            return Decimal(str(value))
        except Exception as exc:
            raise HistoricalMarketDataLoadError(
                f"Unable to convert historical candle value to Decimal: " f"{value!r}"
            ) from exc
