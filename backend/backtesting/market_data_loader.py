"""Historical market-data loading for AQE backtesting."""

from __future__ import annotations


import logging

from collections.abc import Callable

from dataclasses import dataclass

from datetime import datetime, timedelta, timezone

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



    ``internal_gaps`` contains unexplained gaps inside the requested

    range that exceed the configured market-closure tolerance.

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

    internal_gaps: tuple[
        tuple[datetime, datetime],
        ...,
    ] = ()

    @property
    def has_data(self) -> bool:
        """Return whether data exists inside the requested range."""

        return self.candles > 0

    @property
    def expected_first_candle(self) -> datetime:
        """

        Return the first timeframe boundary expected for the requested

        range.



        The requested start may fall between candle boundaries, so the

        first expected candle is the first boundary at or after the

        requested start.

        """

        minutes = self._timeframe_minutes()

        timestamp = self.requested_start.replace(
            second=0,
            microsecond=0,
        )

        elapsed_minutes = timestamp.hour * 60 + timestamp.minute

        remainder = elapsed_minutes % minutes

        if (
            remainder == 0
            and self.requested_start.second == 0
            and self.requested_start.microsecond == 0
        ):

            return timestamp

        return timestamp + timedelta(
            minutes=minutes - remainder,
        )

    @property
    def expected_last_candle(self) -> datetime:
        """

        Return the last timeframe boundary expected before the

        requested end.



        The requested end is exclusive.

        """

        minutes = self._timeframe_minutes()

        timestamp = self.requested_end.replace(
            second=0,
            microsecond=0,
        )

        elapsed_minutes = timestamp.hour * 60 + timestamp.minute

        remainder = elapsed_minutes % minutes

        if (
            remainder == 0
            and self.requested_end.second == 0
            and self.requested_end.microsecond == 0
        ):

            return timestamp - timedelta(
                minutes=minutes,
            )

        return timestamp - timedelta(
            minutes=remainder,
        )

    @property
    def spans_requested_range(self) -> bool:
        """

        Return whether the candles actually loaded for the requested

        backtest range provide complete coverage.



        Validation consists of:



            1. beginning coverage;

            2. terminal coverage;

            3. internal continuity.



        Whole-dataset ``first_timestamp`` / ``last_timestamp`` values

        are deliberately NOT used to determine requested-range

        coverage. Those values may belong to history far outside the

        requested backtest period.

        """

        if self.range_first_timestamp is None or self.range_last_timestamp is None:

            return False

        # The actual first candle loaded for this request must reach

        # the first expected timeframe boundary.

        if self.range_first_timestamp > self.expected_first_candle:

            if not self._beginning_weekend_closure_is_valid():

                return False

        # The actual last candle loaded for this request must reach the

        # final expected timeframe boundary.

        if self.range_last_timestamp >= self.expected_last_candle:

            terminal_coverage = True

        else:

            terminal_coverage = self._terminal_weekend_closure_is_valid()

        if not terminal_coverage:

            return False

        return not self.internal_gaps

    @property
    def range_has_boundary_data(self) -> bool:
        """

        Return whether at least one persisted candle exists inside the

        requested range.

        """

        return (
            self.range_first_timestamp is not None
            and self.range_last_timestamp is not None
        )

    def _timeframe_minutes(self) -> int:
        """

        Resolve the timeframe used by coverage calculations.



        Supported identifiers include:



            M1, M5, M15, M30

            H1, H4

            D1



        Unknown formats conservatively fall back to M15.

        """

        normalized = self.timeframe.strip().upper()

        if normalized.startswith("M"):

            try:

                minutes = int(normalized[1:])

            except ValueError:

                return 15

            return minutes if minutes > 0 else 15

        if normalized.startswith("H"):

            try:

                hours = int(normalized[1:])

            except ValueError:

                return 15

            return hours * 60 if hours > 0 else 15

        if normalized == "D1":

            return 24 * 60

        return 15

    def _beginning_weekend_closure_is_valid(self) -> bool:
        """

        Determine whether missing beginning candles are explained by

        a normal weekend market closure.

        The recognized pattern is:

            - requested range begins on Saturday or Sunday;
            - first actual candle resumes on Monday;
            - Monday resume occurs within six hours of Monday 00:00 UTC.

        """

        first_timestamp = self.range_first_timestamp

        if first_timestamp is None:

            return False

        if first_timestamp.weekday() != 0:

            return False

        if self.requested_start.weekday() not in {5, 6}:

            return False

        gap = first_timestamp - self.requested_start

        if gap < timedelta(0):

            return False

        monday_open = datetime.combine(
            first_timestamp.date(),
            datetime.min.time(),
            tzinfo=first_timestamp.tzinfo,
        )

        if first_timestamp - monday_open > timedelta(hours=6):

            return False

        return True

    def _terminal_weekend_closure_is_valid(self) -> bool:
        """

        Determine whether missing terminal candles are explained by a

        normal Friday/weekend market closure.



        The terminal exception is intentionally limited to the actual

        last candle loaded inside the requested range.



        It is valid only when:



            - the final loaded candle is on Friday;

            - the requested end is Saturday, Sunday, or Monday;

            - the gap is no greater than 72 hours.

        """

        last_timestamp = self.range_last_timestamp

        if last_timestamp is None:

            return False

        if last_timestamp.weekday() != 4:

            return False

        requested_end_weekday = self.requested_end.weekday()

        if requested_end_weekday not in {
            0,
            5,
            6,
        }:

            return False

        gap = self.requested_end - last_timestamp

        if gap < timedelta(0):

            return False

        return gap <= timedelta(hours=72)


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

        - verify beginning and terminal coverage

        - detect large unexplained internal gaps

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

    # Normal weekday continuity is validated strictly.
    #
    # Gaps up to 72 hours are tolerated by the existing generic
    # closure tolerance. Longer gaps require a recognizable
    # weekend-style closure pattern and are subject to a separate
    # upper bound.
    DEFAULT_MAX_INTERNAL_GAP = timedelta(
        hours=72,
    )

    DEFAULT_MAX_WEEKEND_CLOSURE_GAP = timedelta(
        hours=96,
    )

    # Some MT5 symbols reopen shortly after 00:00 UTC on Monday.
    # Permit a small Monday pre-session grace period when recognizing
    # an extended Friday/weekend closure.
    DEFAULT_WEEKEND_REOPEN_GRACE = timedelta(
        hours=6,
    )

    def __init__(
        self,
        *,
        session_factory: SessionFactory,
        require_full_range: bool = True,
        max_internal_gap: timedelta | None = None,
    ) -> None:

        if not callable(session_factory):

            raise TypeError(
                "session_factory must be callable.",
            )

        if max_internal_gap is not None:

            if max_internal_gap <= timedelta(0):

                raise ValueError(
                    "max_internal_gap must be greater than zero.",
                )

        self._session_factory = session_factory

        self._require_full_range = bool(
            require_full_range,
        )

        self._max_internal_gap = (
            max_internal_gap
            if max_internal_gap is not None
            else self.DEFAULT_MAX_INTERNAL_GAP
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

        symbol/timeframe pair must:



            - have beginning coverage;

            - have terminal coverage;

            - contain no unexplained large internal gap.

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
                    "range_first=%s range_last=%s "
                    "expected_first=%s expected_last=%s "
                    "internal_gaps=%d",
                    config.account_id,
                    item.symbol,
                    item.timeframe,
                    item.candles,
                    item.first_timestamp,
                    item.last_timestamp,
                    item.range_first_timestamp,
                    item.range_last_timestamp,
                    item.expected_first_candle,
                    item.expected_last_candle,
                    len(item.internal_gaps),
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

        Load requested-range candles and calculate coverage for every

        requested symbol/timeframe pair.

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

        # Load only candles actually required by the simulation.

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
                "timestamps": [],
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

            state["timestamps"].append(
                timestamp,
            )

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

        # Inspect the complete persisted history for each exact

        # symbol_id/timeframe pair.

        #

        # This provides diagnostic boundaries without loading all

        # historical candles into memory.

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

                normalized_timeframe = (
                    str(
                        row.timeframe,
                    )
                    .strip()
                    .upper()
                )

                boundary_lookup[
                    (
                        row.symbol_id,
                        normalized_timeframe,
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

            timestamps = sorted(
                set(
                    state["timestamps"],
                )
            )

            internal_gaps = self._detect_internal_gaps(
                symbol=symbol,
                timestamps=timestamps,
                requested_start=start,
                requested_end=end,
                timeframe=timeframe,
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
                    internal_gaps=tuple(
                        internal_gaps,
                    ),
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

    # INTERNAL GAP DETECTION

    # ==================================================================

    def _detect_internal_gaps(
        self,
        *,
        symbol: str,
        timestamps: list[datetime],
        requested_start: datetime,
        requested_end: datetime,
        timeframe: str,
    ) -> list[tuple[datetime, datetime]]:
        """
        Detect unexplained internal gaps in the requested range.

        A normal timeframe step is expected between adjacent candles.

        Gaps up to ``self._max_internal_gap`` are tolerated by the
        existing generic closure tolerance.

        Longer gaps are tolerated only when they match a conservative
        extended-weekend pattern:

            Friday closure
                ->
            Saturday/Sunday
                ->
            early Monday reopen

        This covers extended holiday-weekend closures such as the
        Good Friday + weekend gap seen in broker historical data, while
        keeping ordinary weekday gaps strict.

        Beginning and terminal coverage are handled separately by
        HistoricalCoverage.
        """

        if len(timestamps) < 2:
            return []

        timeframe_delta = timedelta(
            minutes=self._timeframe_minutes(
                timeframe,
            ),
        )

        if timeframe_delta <= timedelta(0):
            timeframe_delta = timedelta(
                minutes=15,
            )

        gaps: list[tuple[datetime, datetime]] = []

        previous = timestamps[0]

        for current in timestamps[1:]:
            gap = current - previous

            if gap <= timeframe_delta:
                previous = current
                continue

            gap_start = previous
            gap_end = current

            # The missing portion must overlap the requested simulation
            # range to be relevant to this coverage calculation.
            missing_start = max(
                gap_start + timeframe_delta,
                requested_start,
            )

            missing_end = min(
                gap_end,
                requested_end,
            )

            if missing_start >= missing_end:
                previous = current
                continue

            # Preserve the original generic tolerance first.
            if gap <= self._max_internal_gap:
                previous = current
                continue

            # Extended Friday/weekend closures are handled separately
            # from unexplained data holes.
            if self._is_extended_weekend_closure(
                missing_start=missing_start,
                missing_end=missing_end,
            ):
                logger.info(
                    "Historical market-closure gap tolerated: "
                    "symbol=%s timeframe=%s "
                    "gap_start=%s gap_end=%s "
                    "duration=%s max_weekend_allowed=%s",
                    symbol,
                    timeframe,
                    gap_start,
                    gap_end,
                    gap,
                    self.DEFAULT_MAX_WEEKEND_CLOSURE_GAP,
                )

                previous = current
                continue

            gaps.append(
                (
                    gap_start,
                    gap_end,
                )
            )

            logger.warning(
                "Historical internal gap detected: "
                "symbol=%s timeframe=%s "
                "gap_start=%s gap_end=%s "
                "duration=%s max_allowed=%s",
                symbol,
                timeframe,
                gap_start,
                gap_end,
                gap,
                self._max_internal_gap,
            )

            previous = current

        return gaps

    @classmethod
    def _is_extended_weekend_closure(
        cls,
        *,
        missing_start: datetime,
        missing_end: datetime,
    ) -> bool:
        """
        Return whether a long missing interval matches an extended
        Friday/weekend market closure.

        The recognized pattern is deliberately conservative:

            - the missing interval begins on Friday;
            - it continues through Saturday/Sunday;
            - the next candle resumes on Monday;
            - the Monday resume time is within the configured early
              reopen grace period;
            - the total missing interval does not exceed 96 hours.

        This avoids treating arbitrary Monday-through-Friday gaps as
        market closures.
        """

        if missing_start >= missing_end:
            return False

        gap = missing_end - missing_start

        if gap <= timedelta(hours=72):
            return False

        if gap > cls.DEFAULT_MAX_WEEKEND_CLOSURE_GAP:
            return False

        if missing_start.weekday() != 4:
            return False

        if missing_end.weekday() != 0:
            return False

        monday_open = datetime.combine(
            missing_end.date(),
            datetime.min.time(),
            tzinfo=missing_end.tzinfo,
        )

        if missing_end - monday_open > cls.DEFAULT_WEEKEND_REOPEN_GRACE:
            return False

        return True

    @staticmethod
    def _timeframe_minutes(
        timeframe: str,
    ) -> int:
        """

        Resolve a timeframe identifier into minutes.

        """

        normalized = (
            str(
                timeframe,
            )
            .strip()
            .upper()
        )

        if normalized.startswith("M"):

            try:

                minutes = int(
                    normalized[1:],
                )

            except ValueError:

                return 15

            return minutes if minutes > 0 else 15

        if normalized.startswith("H"):

            try:

                hours = int(
                    normalized[1:],
                )

            except ValueError:

                return 15

            return hours * 60 if hours > 0 else 15

        if normalized == "D1":

            return 24 * 60

        return 15

    # ==================================================================

    # CONFIG VALIDATION

    # ==================================================================

    @staticmethod
    @staticmethod
    def _requested_range_is_weekend_or_monday_preopen(
        start: datetime,
        end: datetime,
    ) -> bool:
        """

        Return whether the requested interval contains only normal

        weekend closure time or Monday pre-open time.

        This is intentionally conservative and does not recognize

        exchange-specific holidays or arbitrary weekday outages.

        """

        if start >= end:

            return False

        current = start.date()

        final = (end - timedelta(microseconds=1)).date()

        while current <= final:

            weekday = current.weekday()

            if weekday < 5:

                if weekday != 0:

                    return False

                monday_open = datetime.combine(
                    current,
                    datetime.min.time(),
                    tzinfo=start.tzinfo,
                )

                monday_grace_end = (
                    monday_open
                    + HistoricalMarketDataLoader.DEFAULT_WEEKEND_REOPEN_GRACE
                )

                segment_start = max(
                    start,
                    monday_open,
                )

                segment_end = min(
                    end,
                    monday_grace_end,
                )

                if segment_start >= segment_end:

                    return False

            current += timedelta(days=1)

        if final.weekday() == 0:

            monday_open = datetime.combine(
                final,
                datetime.min.time(),
                tzinfo=start.tzinfo,
            )

            monday_grace_end = (
                monday_open + HistoricalMarketDataLoader.DEFAULT_WEEKEND_REOPEN_GRACE
            )

            if end > monday_grace_end:

                return False

        return True

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

            raise TypeError(
                "config must be an instance of BacktestConfig.",
            )

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

        Validate that every requested symbol/timeframe pair has:



            - data inside the requested range;

            - beginning coverage;

            - terminal coverage;

            - no unexplained large internal gap.

        """

        if not coverage:

            raise HistoricalMarketDataLoadError(
                self._format_no_data_error(
                    config,
                )
            )

        missing_pairs: list[str] = []

        incomplete_pairs: list[str] = []

        gapped_pairs: list[str] = []

        for item in coverage:

            pair = f"{item.symbol}/{item.timeframe}"

            # ----------------------------------------------------------

            # No candle inside the requested simulation range.

            # ----------------------------------------------------------

            if not item.has_data:

                if self._requested_range_is_weekend_or_monday_preopen(
                    item.requested_start,
                    item.requested_end,
                ):

                    logger.info(
                        "Historical coverage contains no candles because "
                        "the requested interval is a known market-closure "
                        "window | symbol=%s timeframe=%s start=%s end=%s",
                        item.symbol,
                        item.timeframe,
                        item.requested_start,
                        item.requested_end,
                    )

                    continue

                missing_pairs.append(
                    pair,
                )

                continue

            # ----------------------------------------------------------

            # Requested-range coverage.

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

                expected_first = item.expected_first_candle.isoformat()

                expected_last = item.expected_last_candle.isoformat()

                incomplete_pairs.append(
                    f"{pair} "
                    f"(available={first}..{last}, "
                    f"loaded={range_first}..{range_last}, "
                    f"expected={expected_first}..{expected_last})"
                )

            # ----------------------------------------------------------

            # Explicit internal gaps.

            # ----------------------------------------------------------

            if item.internal_gaps:

                gapped_pairs.append(
                    f"{pair} " f"({self._format_gaps(item.internal_gaps)})"
                )

        # --------------------------------------------------------------

        # Missing datasets.

        # --------------------------------------------------------------

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

            if gapped_pairs:

                message += ". Internal historical gaps: " + ", ".join(
                    gapped_pairs,
                )

            raise HistoricalMarketDataLoadError(
                message + ". Run historical backfill before starting " "the backtest."
            )

        # --------------------------------------------------------------

        # Incomplete or gapped datasets.

        # --------------------------------------------------------------

        if incomplete_pairs or gapped_pairs:

            parts: list[str] = []

            if incomplete_pairs:

                parts.append(
                    "Incomplete historical coverage: "
                    + ", ".join(
                        incomplete_pairs,
                    )
                )

            if gapped_pairs:

                parts.append(
                    "Internal historical gaps: "
                    + ", ".join(
                        gapped_pairs,
                    )
                )

            raise HistoricalMarketDataLoadError(
                "Historical market data is incomplete. "
                + ". ".join(parts)
                + ". Run historical backfill before starting "
                "the backtest."
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

    # GAP FORMATTING

    # ==================================================================

    @staticmethod
    def _format_gaps(
        gaps: tuple[
            tuple[datetime, datetime],
            ...,
        ],
    ) -> str:
        """

        Format internal gap diagnostics for error messages.

        """

        formatted: list[str] = []

        for start, end in gaps[:5]:

            duration = end - start

            formatted.append(
                f"{start.isoformat()}.." f"{end.isoformat()} " f"({duration})"
            )

        if len(gaps) > 5:

            formatted.append(
                f"... and {len(gaps) - 5} more",
            )

        return ", ".join(
            formatted,
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
