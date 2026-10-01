"""Historical market-data loading for AQE backtesting."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import (
    Select,
    and_,
    func,
    or_,
    select,
)
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.database.models.historical_candle import HistoricalCandle

from .engine import BacktestConfig
from .market import BacktestCandle, BacktestMarketData

logger = logging.getLogger(__name__)


# ======================================================================
# ERRORS
# ======================================================================


class HistoricalMarketDataLoadError(RuntimeError):
    """Raised when historical market data cannot be loaded."""


# ======================================================================
# TYPES
# ======================================================================


SessionFactory = Callable[[], AsyncSession]


# ======================================================================
# COVERAGE
# ======================================================================


@dataclass(frozen=True, slots=True)
class HistoricalCoverage:
    """
    Coverage information for one symbol/timeframe dataset.

    ``first_timestamp`` and ``last_timestamp`` represent the earliest
    and latest persisted timestamps available for that dataset.

    ``range_first_timestamp`` and ``range_last_timestamp`` represent
    the first and last candles actually loaded inside the requested
    backtest range.
    """

    symbol: str
    timeframe: str

    candles: int

    first_timestamp: datetime | None
    last_timestamp: datetime | None

    range_first_timestamp: datetime | None
    range_last_timestamp: datetime | None

    requested_start: datetime
    requested_end: datetime

    @property
    def has_data(self) -> bool:
        """Return whether data exists inside the requested range."""

        return self.candles > 0

    @property
    def spans_requested_range(self) -> bool:
        """
        Return whether the persisted dataset spans the complete
        requested historical range.

        Because the requested end is exclusive, the important question
        is whether persisted data exists at or beyond that boundary.

        This intentionally does not require a candle exactly at
        ``requested_end`` because the requested end may fall between
        candle boundaries or during a market closure.
        """

        if self.first_timestamp is None or self.last_timestamp is None:
            return False

        return (
            self.first_timestamp <= self.requested_start
            and self.last_timestamp >= self.requested_end
        )

    @property
    def range_has_boundary_data(self) -> bool:
        """
        Return whether at least one persisted candle exists inside the
        requested range.

        This is weaker than ``spans_requested_range`` and is useful in
        diagnostics.
        """

        return (
            self.range_first_timestamp is not None
            and self.range_last_timestamp is not None
        )


# ======================================================================
# LOADER
# ======================================================================


class HistoricalMarketDataLoader:
    """
    Load persisted historical candles into the AQE backtesting store.

    Responsibilities:
        - validate the resolved backtest universe
        - load PostgreSQL historical candles
        - normalize database values
        - detect missing symbol/timeframe datasets
        - verify that persisted data spans the requested range
        - remove duplicate candles from the simulation feed
        - convert SQLAlchemy rows into BacktestCandle objects

    This class does NOT:
        - generate synthetic candles
        - fabricate missing market data
        - communicate with MT5
        - communicate with Redis
        - execute orders
        - calculate risk
        - generate strategy signals

    Broker historical backfill must populate HistoricalCandle before
    this loader is invoked.
    """

    def __init__(
        self,
        *,
        session_factory: SessionFactory,
        require_full_range: bool = True,
    ) -> None:
        if not callable(session_factory):
            raise TypeError("session_factory must be callable.")

        self._session_factory = session_factory

        self._require_full_range = bool(
            require_full_range,
        )

    # ==================================================================
    # PUBLIC LOAD
    # ==================================================================

    async def load(
        self,
        config: BacktestConfig,
    ) -> BacktestMarketData:
        """
        Load the complete historical dataset required by a backtest.

        The resolved BacktestConfig supplies:

            symbols
            timeframes
            start
            end

        The loader returns only candles belonging to that universe and
        requested time range.

        When ``require_full_range`` is enabled, every requested
        symbol/timeframe pair must have persisted history spanning the
        complete requested period.
        """

        self._validate_config(
            config,
        )

        try:
            candles, coverage = await self._load_candles(
                config,
            )

            if not candles:
                raise HistoricalMarketDataLoadError(
                    self._format_no_data_error(
                        config,
                    )
                )

            self._validate_coverage(
                config=config,
                coverage=coverage,
            )

            market_data = BacktestMarketData()

            market_data.add_many(
                candles,
            )

            market_data.finalize()

            logger.info(
                "Loaded historical market data for backtest: "
                "account_id=%s symbols=%s timeframes=%s "
                "candles=%d start=%s end=%s",
                config.account_id,
                config.symbols,
                config.timeframes,
                len(candles),
                config.start,
                config.end,
            )

            for item in coverage:
                logger.debug(
                    "Historical coverage: "
                    "account_id=%s symbol=%s timeframe=%s "
                    "range_candles=%d first=%s last=%s "
                    "range_first=%s range_last=%s",
                    config.account_id,
                    item.symbol,
                    item.timeframe,
                    item.candles,
                    item.first_timestamp,
                    item.last_timestamp,
                    item.range_first_timestamp,
                    item.range_last_timestamp,
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

    # ==================================================================
    # DATABASE LOAD
    # ==================================================================

    async def _load_candles(
        self,
        config: BacktestConfig,
    ) -> tuple[
        list[BacktestCandle],
        list[HistoricalCoverage],
    ]:
        """
        Load requested-range candles and calculate full dataset
        coverage for every symbol/timeframe pair.
        """

        symbols = self._normalize_values(
            config.symbols,
        )

        timeframes = self._normalize_values(
            config.timeframes,
        )

        start, end = config.historical_range

        requested_pairs = {
            (
                symbol,
                timeframe,
            )
            for symbol in symbols
            for timeframe in timeframes
        }

        # --------------------------------------------------------------
        # First query:
        #
        # Load only candles actually needed by the simulation.
        # --------------------------------------------------------------

        async with self._session_factory() as session:
            statement: Select[Any] = (
                select(HistoricalCandle)
                .options(
                    joinedload(
                        HistoricalCandle.symbol,
                    )
                )
                .where(
                    HistoricalCandle.timeframe.in_(
                        timeframes,
                    )
                )
                .where(
                    HistoricalCandle.timestamp >= start,
                )
                .where(
                    HistoricalCandle.timestamp < end,
                )
                .order_by(
                    HistoricalCandle.timestamp.asc(),
                    HistoricalCandle.symbol_id.asc(),
                    HistoricalCandle.timeframe.asc(),
                )
            )

            result = await session.execute(
                statement,
            )

            rows = result.scalars().unique().all()

        candles: list[BacktestCandle] = []

        # --------------------------------------------------------------
        # Range coverage state.
        # --------------------------------------------------------------

        coverage_state: dict[
            tuple[str, str],
            dict[str, Any],
        ] = {
            pair: {
                "candles": 0,
                "range_first": None,
                "range_last": None,
                "symbol_id": None,
            }
            for pair in requested_pairs
        }

        # --------------------------------------------------------------
        # Deduplication.
        # --------------------------------------------------------------

        seen_candles: set[tuple[str, str, datetime]] = set()

        requested_symbols = set(
            symbols,
        )

        requested_timeframes = set(
            timeframes,
        )

        for row in rows:
            symbol = self._extract_symbol(
                row,
            )

            if symbol not in requested_symbols:
                continue

            timeframe = (
                str(
                    row.timeframe,
                )
                .strip()
                .upper()
            )

            if timeframe not in requested_timeframes:
                continue

            timestamp = self._ensure_datetime(
                row.timestamp,
            )

            pair = (
                symbol,
                timeframe,
            )

            state = coverage_state.get(
                pair,
            )

            if state is None:
                continue

            state["candles"] += 1

            state["symbol_id"] = row.symbol_id

            if state["range_first"] is None or timestamp < state["range_first"]:
                state["range_first"] = timestamp

            if state["range_last"] is None or timestamp > state["range_last"]:
                state["range_last"] = timestamp

            dedupe_key = (
                symbol,
                timeframe,
                timestamp,
            )

            if dedupe_key in seen_candles:
                logger.warning(
                    "Duplicate historical candle ignored: "
                    "symbol=%s timeframe=%s timestamp=%s",
                    symbol,
                    timeframe,
                    timestamp,
                )

                continue

            seen_candles.add(
                dedupe_key,
            )

            candles.append(
                self._to_backtest_candle(
                    row,
                    symbol=symbol,
                    timeframe=timeframe,
                    timestamp=timestamp,
                )
            )

        # --------------------------------------------------------------
        # Second query:
        #
        # For every pair that actually has data in the requested range,
        # inspect the whole persisted history for that exact
        # symbol_id/timeframe pair.
        #
        # This lets us correctly determine:
        #
        #     earliest available timestamp
        #     latest available timestamp
        #
        # without loading all historical candles into memory.
        # --------------------------------------------------------------

        boundary_lookup: dict[
            tuple[UUID, str],
            tuple[
                datetime | None,
                datetime | None,
            ],
        ] = {}

        pair_to_symbol_id: dict[
            tuple[str, str],
            UUID,
        ] = {}

        for pair, state in coverage_state.items():
            symbol_id = state["symbol_id"]

            if symbol_id is None:
                continue

            pair_to_symbol_id[pair] = symbol_id

        if pair_to_symbol_id:
            boundary_conditions = [
                and_(
                    HistoricalCandle.symbol_id == symbol_id,
                    HistoricalCandle.timeframe == timeframe,
                )
                for (
                    _symbol,
                    timeframe,
                ), symbol_id in pair_to_symbol_id.items()
            ]

            async with self._session_factory() as session:
                boundary_statement = (
                    select(
                        HistoricalCandle.symbol_id,
                        HistoricalCandle.timeframe,
                        func.min(
                            HistoricalCandle.timestamp,
                        ).label(
                            "first_timestamp",
                        ),
                        func.max(
                            HistoricalCandle.timestamp,
                        ).label(
                            "last_timestamp",
                        ),
                    )
                    .where(
                        or_(
                            *boundary_conditions,
                        )
                    )
                    .group_by(
                        HistoricalCandle.symbol_id,
                        HistoricalCandle.timeframe,
                    )
                )

                boundary_result = await session.execute(
                    boundary_statement,
                )

                boundary_rows = boundary_result.all()

            for row in boundary_rows:
                boundary_lookup[
                    (
                        row.symbol_id,
                        str(
                            row.timeframe,
                        )
                        .strip()
                        .upper(),
                    )
                ] = (
                    (
                        self._ensure_datetime(
                            row.first_timestamp,
                        )
                        if row.first_timestamp is not None
                        else None
                    ),
                    (
                        self._ensure_datetime(
                            row.last_timestamp,
                        )
                        if row.last_timestamp is not None
                        else None
                    ),
                )

        # --------------------------------------------------------------
        # Build final coverage records.
        # --------------------------------------------------------------

        coverage: list[HistoricalCoverage] = []

        for (
            symbol,
            timeframe,
        ), state in sorted(
            coverage_state.items(),
        ):
            symbol_id = state["symbol_id"]

            first_timestamp: datetime | None = None
            last_timestamp: datetime | None = None

            if symbol_id is not None:
                (
                    first_timestamp,
                    last_timestamp,
                ) = boundary_lookup.get(
                    (
                        symbol_id,
                        timeframe,
                    ),
                    (
                        None,
                        None,
                    ),
                )

            coverage.append(
                HistoricalCoverage(
                    symbol=symbol,
                    timeframe=timeframe,
                    candles=int(
                        state["candles"],
                    ),
                    first_timestamp=first_timestamp,
                    last_timestamp=last_timestamp,
                    range_first_timestamp=state["range_first"],
                    range_last_timestamp=state["range_last"],
                    requested_start=start,
                    requested_end=end,
                )
            )

        # --------------------------------------------------------------
        # Chronological order.
        # --------------------------------------------------------------

        candles.sort(
            key=lambda candle: (
                candle.timestamp,
                candle.symbol,
                candle.timeframe,
            )
        )

        return candles, coverage

    # ==================================================================
    # CONFIG VALIDATION
    # ==================================================================

    @staticmethod
    def _validate_config(
        config: BacktestConfig,
    ) -> None:
        """
        Validate that the loader receives a resolved account-level
        BacktestConfig.
        """

        if not isinstance(
            config,
            BacktestConfig,
        ):
            raise TypeError("config must be an instance of BacktestConfig.")

        symbols = HistoricalMarketDataLoader._normalize_values(
            config.symbols,
        )

        timeframes = HistoricalMarketDataLoader._normalize_values(
            config.timeframes,
        )

        if not symbols:
            raise HistoricalMarketDataLoadError(
                "Backtest requires at least one resolved symbol."
            )

        if not timeframes:
            raise HistoricalMarketDataLoadError(
                "Backtest requires at least one resolved timeframe."
            )

        if config.start is None or config.end is None:
            raise HistoricalMarketDataLoadError(
                "Backtest requires a resolved historical start/end range."
            )

        if config.start >= config.end:
            raise HistoricalMarketDataLoadError(
                "Backtest start must be before backtest end."
            )

    # ==================================================================
    # COVERAGE VALIDATION
    # ==================================================================

    def _validate_coverage(
        self,
        *,
        config: BacktestConfig,
        coverage: list[HistoricalCoverage],
    ) -> None:
        """
        Validate that every requested symbol/timeframe pair has
        persisted historical data spanning the requested period.
        """

        if not coverage:
            raise HistoricalMarketDataLoadError(
                self._format_no_data_error(
                    config,
                )
            )

        missing_pairs: list[str] = []
        incomplete_pairs: list[str] = []

        for item in coverage:
            pair = f"{item.symbol}/{item.timeframe}"

            # ----------------------------------------------------------
            # No candle inside the requested simulation range.
            # ----------------------------------------------------------

            if not item.has_data:
                missing_pairs.append(
                    pair,
                )

                continue

            # ----------------------------------------------------------
            # Candle exists in the requested range, but historical
            # storage does not span the complete requested period.
            # ----------------------------------------------------------

            if self._require_full_range and not item.spans_requested_range:
                first = (
                    item.first_timestamp.isoformat()
                    if item.first_timestamp is not None
                    else "none"
                )

                last = (
                    item.last_timestamp.isoformat()
                    if item.last_timestamp is not None
                    else "none"
                )

                range_first = (
                    item.range_first_timestamp.isoformat()
                    if item.range_first_timestamp is not None
                    else "none"
                )

                range_last = (
                    item.range_last_timestamp.isoformat()
                    if item.range_last_timestamp is not None
                    else "none"
                )

                incomplete_pairs.append(
                    f"{pair} "
                    f"(available={first}..{last}, "
                    f"loaded={range_first}..{range_last})"
                )

        if missing_pairs:
            message = (
                "Historical data is missing for requested "
                "symbol/timeframe pairs: "
                + ", ".join(
                    missing_pairs,
                )
            )

            if incomplete_pairs:
                message += ". Incomplete historical coverage: " + ", ".join(
                    incomplete_pairs,
                )

            raise HistoricalMarketDataLoadError(
                message + ". Run historical backfill before starting " "the backtest."
            )

        if incomplete_pairs:
            raise HistoricalMarketDataLoadError(
                "Historical data does not span the requested "
                "backtest period for: "
                + ", ".join(
                    incomplete_pairs,
                )
                + ". "
                "Run historical backfill for the missing range "
                "before starting the backtest."
            )

    # ==================================================================
    # SYMBOL RESOLUTION
    # ==================================================================

    @staticmethod
    def _extract_symbol(
        row: HistoricalCandle,
    ) -> str:
        """
        Resolve the canonical symbol name from the HistoricalCandle
        relationship.
        """

        symbol = row.symbol

        if symbol is None:
            raise HistoricalMarketDataLoadError(
                "Historical candle has no associated Symbol: "
                f"candle_id={getattr(row, 'id', None)} "
                f"symbol_id={row.symbol_id}"
            )

        symbol_name = getattr(
            symbol,
            "symbol",
            None,
        )

        if symbol_name is None:
            symbol_name = getattr(
                symbol,
                "name",
                None,
            )

        if symbol_name is None:
            raise HistoricalMarketDataLoadError(
                "Unable to resolve symbol name from HistoricalCandle "
                "symbol relationship: "
                f"symbol_id={row.symbol_id}"
            )

        normalized = (
            str(
                symbol_name,
            )
            .strip()
            .upper()
        )

        if not normalized:
            raise HistoricalMarketDataLoadError(
                "Historical candle has an empty symbol name: "
                f"symbol_id={row.symbol_id}"
            )

        return normalized

    # ==================================================================
    # CANDLE CONVERSION
    # ==================================================================

    @classmethod
    def _to_backtest_candle(
        cls,
        row: HistoricalCandle,
        *,
        symbol: str | None = None,
        timeframe: str | None = None,
        timestamp: datetime | None = None,
    ) -> BacktestCandle:
        """
        Convert a SQLAlchemy HistoricalCandle into BacktestCandle.
        """

        normalized_symbol = (
            symbol
            if symbol is not None
            else cls._extract_symbol(
                row,
            )
        )

        normalized_timeframe = (
            timeframe
            if timeframe is not None
            else (
                str(
                    row.timeframe,
                )
                .strip()
                .upper()
            )
        )

        normalized_timestamp = (
            timestamp
            if timestamp is not None
            else cls._ensure_datetime(
                row.timestamp,
            )
        )

        return BacktestCandle(
            symbol=normalized_symbol,
            timeframe=normalized_timeframe,
            timestamp=normalized_timestamp,
            open=cls._decimal(
                row.open,
            ),
            high=cls._decimal(
                row.high,
            ),
            low=cls._decimal(
                row.low,
            ),
            close=cls._decimal(
                row.close,
            ),
            volume=cls._decimal(
                row.volume,
            ),
            spread=cls._decimal_or_none(
                getattr(
                    row,
                    "spread",
                    None,
                )
            ),
        )

    # ==================================================================
    # NORMALIZATION
    # ==================================================================

    @staticmethod
    def _normalize_values(
        values: Any,
    ) -> tuple[str, ...]:
        """
        Normalize values to uppercase strings, remove blanks, and
        deduplicate while preserving order.
        """

        if values is None:
            return ()

        normalized: list[str] = []
        seen: set[str] = set()

        for value in values:
            if value is None:
                continue

            item = (
                str(
                    value,
                )
                .strip()
                .upper()
            )

            if not item or item in seen:
                continue

            seen.add(
                item,
            )

            normalized.append(
                item,
            )

        return tuple(
            normalized,
        )

    # ==================================================================
    # DATETIME
    # ==================================================================

    @staticmethod
    def _ensure_datetime(
        value: datetime,
    ) -> datetime:
        """
        Normalize database timestamps to timezone-aware UTC datetimes.
        """

        if not isinstance(
            value,
            datetime,
        ):
            raise HistoricalMarketDataLoadError(
                "Historical candle timestamp must be a datetime."
            )

        if value.tzinfo is None:
            return value.replace(
                tzinfo=timezone.utc,
            )

        return value.astimezone(
            timezone.utc,
        )

    # ==================================================================
    # DECIMAL
    # ==================================================================

    @staticmethod
    def _decimal(
        value: Any,
    ) -> Decimal:
        """
        Convert SQLAlchemy numeric values into Decimal safely.
        """

        if value is None:
            return Decimal("0")

        if isinstance(
            value,
            Decimal,
        ):
            return value

        try:
            return Decimal(
                str(value),
            )

        except Exception as exc:
            raise HistoricalMarketDataLoadError(
                "Unable to convert historical candle value to Decimal: " f"{value!r}"
            ) from exc

    @classmethod
    def _decimal_or_none(
        cls,
        value: Any,
    ) -> Decimal | None:
        """
        Convert an optional numeric database value to Decimal.
        """

        if value is None:
            return None

        return cls._decimal(
            value,
        )

    # ==================================================================
    # ERROR FORMATTING
    # ==================================================================

    @staticmethod
    def _format_no_data_error(
        config: BacktestConfig,
    ) -> str:
        """
        Build a useful no-data diagnostic.
        """

        return (
            "No historical market data found for backtest: "
            f"symbols={config.symbols}, "
            f"timeframes={config.timeframes}, "
            f"start={config.start}, "
            f"end={config.end}. "
            "Historical backfill is required before this period "
            "can be backtested."
        )
