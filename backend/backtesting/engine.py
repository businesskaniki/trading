"""Core simulation engine and configuration for AQE backtesting."""
from __future__ import annotations

import asyncio
import calendar
import inspect
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4
from app.schemas.execution import (
    ExecutionOrder,
    ExecutionResult,
    OrderSide,
    OrderType,
)
from .execution import (
    BacktestExecution,
    BacktestExecutionContext,
)
from .fill import (
    BacktestFillConfig,
    BacktestFillEngine,
)
from .market import (
    BacktestMarket,
    BacktestMarketData,
    BacktestMarketEvent,
)
from .orders import (
    BacktestPendingOrderBook,
    PendingBacktestOrder,
)
from .portfolio import BacktestPortfolio
from .position import BacktestPositionSide
# ======================================================================
# EXCEPTIONS
# ======================================================================
class BacktestEngineError(Exception):
    """Base exception for backtest engine failures."""
class BacktestConfigurationError(BacktestEngineError):
    """Raised when backtest configuration is invalid."""
# ======================================================================
# STATUS
# ======================================================================
class BacktestStatus(StrEnum):
    """Lifecycle states for a backtest run."""
    CREATED = "CREATED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    STOPPED = "STOPPED"
    FAILED = "FAILED"
# ======================================================================
# PERIOD
# ======================================================================
class BacktestPeriodUnit(StrEnum):
    """Supported relative backtest period units."""
    MINUTES = "minutes"
    HOURS = "hours"
    DAYS = "days"
    WEEKS = "weeks"
    MONTHS = "months"
    YEARS = "years"
@dataclass(frozen=True, slots=True)
class BacktestPeriod:
    """Relative historical period requested for a backtest."""
    value: int
    unit: BacktestPeriodUnit
    def __post_init__(self) -> None:
        if isinstance(self.unit, str):
            try:
                object.__setattr__(
                    self,
                    "unit",
                    BacktestPeriodUnit(
                        self.unit.strip().lower(),
                    ),
                )
            except ValueError as exc:
                raise BacktestConfigurationError(
                    f"Invalid backtest period unit: {self.unit!r}.",
                ) from exc
        if isinstance(
            self.value,
            bool,
        ) or not isinstance(
            self.value,
            int,
        ):
            raise BacktestConfigurationError(
                "Backtest period value must be an integer.",
            )
        if self.value <= 0:
            raise BacktestConfigurationError(
                "Backtest period value must be greater than zero.",
            )
        if not isinstance(
            self.unit,
            BacktestPeriodUnit,
        ):
            raise BacktestConfigurationError(
                "Backtest period unit is invalid.",
            )
    @classmethod
    def from_value(
        cls,
        value: BacktestPeriod | dict[str, Any],
    ) -> BacktestPeriod:
        """
        Build a BacktestPeriod from the native object or a mapping.
        """
        if isinstance(
            value,
            cls,
        ):
            return value
        if isinstance(
            value,
            dict,
        ):
            try:
                raw_value = value["value"]
                raw_unit = value["unit"]
                if isinstance(
                    raw_value,
                    bool,
                ):
                    raise TypeError(
                        "Boolean is not a valid period value.",
                    )
                return cls(
                    value=int(raw_value),
                    unit=BacktestPeriodUnit(
                        str(raw_unit).strip().lower(),
                    ),
                )
            except (
                KeyError,
                TypeError,
                ValueError,
            ) as exc:
                raise BacktestConfigurationError(
                    "Invalid backtest period. Expected "
                    "{'value': positive integer, "
                    "'unit': valid period unit}.",
                ) from exc
        raise BacktestConfigurationError(
            "Backtest period must be a BacktestPeriod or mapping.",
        )
    def resolve(
        self,
        *,
        end: datetime,
    ) -> datetime:
        """
        Resolve this relative period into a UTC start datetime.
        """
        end = self._normalize_datetime(
            end,
        )
        if self.unit == BacktestPeriodUnit.MINUTES:
            return end - timedelta(
                minutes=self.value,
            )
        if self.unit == BacktestPeriodUnit.HOURS:
            return end - timedelta(
                hours=self.value,
            )
        if self.unit == BacktestPeriodUnit.DAYS:
            return end - timedelta(
                days=self.value,
            )
        if self.unit == BacktestPeriodUnit.WEEKS:
            return end - timedelta(
                weeks=self.value,
            )
        if self.unit == BacktestPeriodUnit.MONTHS:
            return self._subtract_months(
                end,
                self.value,
            )
        if self.unit == BacktestPeriodUnit.YEARS:
            return self._subtract_months(
                end,
                self.value * 12,
            )
        raise BacktestConfigurationError(
            f"Unsupported backtest period unit: {self.unit!r}",
        )
    @staticmethod
    def _subtract_months(
        value: datetime,
        months: int,
    ) -> datetime:
        """
        Subtract calendar months while clamping invalid month days.
        """
        absolute_month = value.year * 12 + (value.month - 1) - months
        target_year = absolute_month // 12
        target_month = absolute_month % 12 + 1
        last_day = calendar.monthrange(
            target_year,
            target_month,
        )[1]
        target_day = min(
            value.day,
            last_day,
        )
        return value.replace(
            year=target_year,
            month=target_month,
            day=target_day,
        )
    @staticmethod
    def _normalize_datetime(
        value: datetime,
    ) -> datetime:
        if value.tzinfo is None:
            return value.replace(
                tzinfo=timezone.utc,
            )
        return value.astimezone(
            timezone.utc,
        )
# ======================================================================
# SYMBOL SPECIFICATION
# ======================================================================
@dataclass(frozen=True, slots=True)
class BacktestSymbolSpecification:
    """
    Account/broker-specific trading specification for one backtest symbol.
    ``symbol`` is the canonical AQE symbol.
    ``broker_symbol`` is the broker/server representation used when
    historical data was acquired.
    The remaining fields mirror the relevant AccountSymbol trading
    metadata needed by the simulation and risk engine.
    ``tick_value`` is intentionally derived because AccountSymbol does
    not currently persist an explicit tick-value field.
    When both tick_size and contract_size are available:
        tick_value = tick_size * contract_size
    This is a simulation convention and should not be interpreted as a
    broker-reported MT5 tick value.
    """
    symbol: str
    broker_symbol: str | None = None
    digits: int | None = None
    point: Decimal | None = None
    tick_size: Decimal | None = None
    contract_size: Decimal | None = None
    min_volume: Decimal | None = None
    max_volume: Decimal | None = None
    volume_step: Decimal | None = None
    def __post_init__(self) -> None:
        # ==============================================================
        # SYMBOL
        # ==============================================================
        if not isinstance(
            self.symbol,
            str,
        ):
            raise BacktestConfigurationError(
                "Backtest symbol specification symbol must be a string.",
            )
        symbol = self.symbol.strip().upper()
        if not symbol:
            raise BacktestConfigurationError(
                "Backtest symbol specification symbol cannot be empty.",
            )
        object.__setattr__(
            self,
            "symbol",
            symbol,
        )
        # ==============================================================
        # BROKER SYMBOL
        # ==============================================================
        broker_symbol = self.broker_symbol
        if broker_symbol is not None:
            if not isinstance(
                broker_symbol,
                str,
            ):
                raise BacktestConfigurationError(
                    f"Broker symbol for '{symbol}' must be a string.",
                )
            broker_symbol = broker_symbol.strip()
            if not broker_symbol:
                broker_symbol = None
        object.__setattr__(
            self,
            "broker_symbol",
            broker_symbol,
        )
        # ==============================================================
        # DIGITS
        # ==============================================================
        if self.digits is not None:
            if isinstance(
                self.digits,
                bool,
            ) or not isinstance(
                self.digits,
                int,
            ):
                raise BacktestConfigurationError(
                    f"Digits for '{symbol}' must be an integer.",
                )
            if self.digits < 0:
                raise BacktestConfigurationError(
                    f"Digits for '{symbol}' cannot be negative.",
                )
        # ==============================================================
        # DECIMAL METADATA
        # ==============================================================
        normalized_point = self._normalize_positive_decimal(
            self.point,
            field_name="point",
            symbol=symbol,
        )
        normalized_tick_size = self._normalize_positive_decimal(
            self.tick_size,
            field_name="tick_size",
            symbol=symbol,
        )
        normalized_contract_size = self._normalize_positive_decimal(
            self.contract_size,
            field_name="contract_size",
            symbol=symbol,
        )
        normalized_min_volume = self._normalize_positive_decimal(
            self.min_volume,
            field_name="min_volume",
            symbol=symbol,
        )
        normalized_max_volume = self._normalize_positive_decimal(
            self.max_volume,
            field_name="max_volume",
            symbol=symbol,
        )
        normalized_volume_step = self._normalize_positive_decimal(
            self.volume_step,
            field_name="volume_step",
            symbol=symbol,
        )
        if (
            normalized_min_volume is not None
            and normalized_max_volume is not None
            and normalized_max_volume < normalized_min_volume
        ):
            raise BacktestConfigurationError(
                f"max_volume cannot be smaller than min_volume " f"for '{symbol}'.",
            )
        object.__setattr__(
            self,
            "point",
            normalized_point,
        )
        object.__setattr__(
            self,
            "tick_size",
            normalized_tick_size,
        )
        object.__setattr__(
            self,
            "contract_size",
            normalized_contract_size,
        )
        object.__setattr__(
            self,
            "min_volume",
            normalized_min_volume,
        )
        object.__setattr__(
            self,
            "max_volume",
            normalized_max_volume,
        )
        object.__setattr__(
            self,
            "volume_step",
            normalized_volume_step,
        )
    @staticmethod
    def _normalize_positive_decimal(
        value: Decimal | None,
        *,
        field_name: str,
        symbol: str,
    ) -> Decimal | None:
        if value is None:
            return None
        try:
            normalized = Decimal(
                str(value),
            )
        except Exception as exc:
            raise BacktestConfigurationError(
                f"{field_name} for '{symbol}' must be a valid decimal.",
            ) from exc
        if not normalized.is_finite():
            raise BacktestConfigurationError(
                f"{field_name} for '{symbol}' must be finite.",
            )
        if normalized <= Decimal("0"):
            raise BacktestConfigurationError(
                f"{field_name} for '{symbol}' must be greater than zero.",
            )
        return normalized
    @property
    def tick_value(self) -> Decimal | None:
        """
        Derive the simulation tick value when sufficient metadata exists.
        """
        if self.tick_size is None:
            return None
        if self.contract_size is None:
            return None
        return self.tick_size * self.contract_size
# ======================================================================
# CONFIGURATION
# ======================================================================
@dataclass(frozen=True, slots=True)
class BacktestConfig:
    """
    Immutable configuration for one account-level backtest.
    Public/client-level configuration is account-centric:
        account_id
        initial_balance
        period OR explicit start/end
        close_positions_at_end
    Internal authenticated context:
        user_id
    Composition resolves:
        symbols
        timeframes
        contract_sizes
        symbol_specifications
        leverage
    ``leverage`` is resolved internally from the authenticated trading
    account. It is not intended to be supplied by the public backtest
    request.
    There is intentionally no strategy identity here.
    """
    account_id: UUID
    initial_balance: Decimal
    symbols: tuple[str, ...] = ()
    timeframes: tuple[str, ...] = ()
    period: BacktestPeriod | None = None
    start: datetime | None = None
    end: datetime | None = None
    fill: BacktestFillConfig = field(
        default_factory=BacktestFillConfig,
    )
    # Backward-compatible contract-size overrides.
    contract_sizes: dict[str, Decimal] = field(
        default_factory=dict,
    )
    # AccountSymbol-derived trading metadata.
    symbol_specifications: dict[
        str,
        BacktestSymbolSpecification,
    ] = field(
        default_factory=dict,
    )
    # Trading-account leverage resolved by application composition.
    #
    # This must come from TradingAccount.leverage rather than from the
    # public backtest request and is later converted by the risk layer
    # into:
    #
    #     margin_rate = 1 / leverage
    #
    leverage: Decimal | None = None
    close_positions_at_end: bool = True
    # Internal authenticated-request context.
    #
    # This is not intended to be accepted from the public JSON request.
    # The API layer should inject it from the authenticated principal.
    user_id: UUID | None = field(
        default=None,
        repr=False,
    )
    def __post_init__(self) -> None:
        # ==============================================================
        # ACCOUNT
        # ==============================================================
        if not isinstance(
            self.account_id,
            UUID,
        ):
            raise BacktestConfigurationError(
                "account_id must be a UUID.",
            )
        if self.user_id is not None and not isinstance(
            self.user_id,
            UUID,
        ):
            raise BacktestConfigurationError(
                "user_id must be a UUID when supplied.",
            )
        try:
            initial_balance = Decimal(
                str(self.initial_balance),
            )
        except Exception as exc:
            raise BacktestConfigurationError(
                "initial_balance must be a valid decimal value.",
            ) from exc
        if not initial_balance.is_finite():
            raise BacktestConfigurationError(
                "Initial balance must be finite.",
            )
        if initial_balance < Decimal("0"):
            raise BacktestConfigurationError(
                "Initial balance cannot be negative.",
            )
        object.__setattr__(
            self,
            "initial_balance",
            initial_balance,
        )
        # ==============================================================
        # LEVERAGE
        # ==============================================================
        if self.leverage is not None:
            try:
                leverage = Decimal(
                    str(self.leverage),
                )
            except Exception as exc:
                raise BacktestConfigurationError(
                    "leverage must be a valid decimal value.",
                ) from exc
            if not leverage.is_finite():
                raise BacktestConfigurationError(
                    "Backtest leverage must be finite.",
                )
            if leverage <= Decimal("0"):
                raise BacktestConfigurationError(
                    "Backtest leverage must be greater than zero.",
                )
            object.__setattr__(
                self,
                "leverage",
                leverage,
            )
        # ==============================================================
        # SYMBOLS
        # ==============================================================
        normalized_symbols: list[str] = []
        for symbol in self.symbols:
            if not isinstance(
                symbol,
                str,
            ):
                raise BacktestConfigurationError(
                    "Backtest symbols must be strings.",
                )
            normalized = symbol.strip().upper()
            if normalized and normalized not in normalized_symbols:
                normalized_symbols.append(
                    normalized,
                )
        object.__setattr__(
            self,
            "symbols",
            tuple(normalized_symbols),
        )
        # ==============================================================
        # TIMEFRAMES
        # ==============================================================
        normalized_timeframes: list[str] = []
        for timeframe in self.timeframes:
            if not isinstance(
                timeframe,
                str,
            ):
                raise BacktestConfigurationError(
                    "Backtest timeframes must be strings.",
                )
            normalized = timeframe.strip().upper()
            if normalized and normalized not in normalized_timeframes:
                normalized_timeframes.append(
                    normalized,
                )
        object.__setattr__(
            self,
            "timeframes",
            tuple(normalized_timeframes),
        )
        # ==============================================================
        # PERIOD
        # ==============================================================
        period = self.period
        if period is not None:
            period = BacktestPeriod.from_value(
                period,
            )
        object.__setattr__(
            self,
            "period",
            period,
        )
        # ==============================================================
        # EXPLICIT DATES
        # ==============================================================
        start = self._normalize_datetime(
            self.start,
        )
        end = self._normalize_datetime(
            self.end,
        )
        if period is not None:
            if start is not None or end is not None:
                raise BacktestConfigurationError(
                    "Specify either period or explicit start/end, " "not both.",
                )
            resolved_end = datetime.now(
                timezone.utc,
            )
            resolved_start = period.resolve(
                end=resolved_end,
            )
            start = resolved_start
            end = resolved_end
        elif start is None or end is None:
            raise BacktestConfigurationError(
                "Backtest requires either a period or explicit "
                "start and end datetimes.",
            )
        elif start >= end:
            raise BacktestConfigurationError(
                "Backtest start must be before backtest end.",
            )
        object.__setattr__(
            self,
            "start",
            start,
        )
        object.__setattr__(
            self,
            "end",
            end,
        )
        # ==============================================================
        # CONTRACT SIZES
        # ==============================================================
        normalized_contract_sizes: dict[str, Decimal] = {}
        for symbol, value in self.contract_sizes.items():
            if not isinstance(
                symbol,
                str,
            ):
                raise BacktestConfigurationError(
                    "Contract-size symbols must be strings.",
                )
            normalized_symbol = symbol.strip().upper()
            if not normalized_symbol:
                raise BacktestConfigurationError(
                    "Contract-size symbol cannot be empty.",
                )
            try:
                contract_size = Decimal(
                    str(value),
                )
            except Exception as exc:
                raise BacktestConfigurationError(
                    f"Invalid contract size for " f"'{normalized_symbol}'.",
                ) from exc
            if not contract_size.is_finite():
                raise BacktestConfigurationError(
                    f"Contract size for '{normalized_symbol}' " f"must be finite.",
                )
            if contract_size <= Decimal("0"):
                raise BacktestConfigurationError(
                    f"Contract size for '{normalized_symbol}' "
                    "must be greater than zero.",
                )
            normalized_contract_sizes[normalized_symbol] = contract_size
        object.__setattr__(
            self,
            "contract_sizes",
            normalized_contract_sizes,
        )
        # ==============================================================
        # SYMBOL SPECIFICATIONS
        # ==============================================================
        normalized_specifications: dict[
            str,
            BacktestSymbolSpecification,
        ] = {}
        for symbol, specification in self.symbol_specifications.items():
            if isinstance(
                specification,
                BacktestSymbolSpecification,
            ):
                normalized_specification = specification
            elif isinstance(
                specification,
                dict,
            ):
                try:
                    normalized_specification = BacktestSymbolSpecification(
                        symbol=specification.get(
                            "symbol",
                            symbol,
                        ),
                        broker_symbol=specification.get(
                            "broker_symbol",
                        ),
                        digits=specification.get(
                            "digits",
                        ),
                        point=specification.get(
                            "point",
                        ),
                        tick_size=specification.get(
                            "tick_size",
                        ),
                        contract_size=specification.get(
                            "contract_size",
                        ),
                        min_volume=specification.get(
                            "min_volume",
                        ),
                        max_volume=specification.get(
                            "max_volume",
                        ),
                        volume_step=specification.get(
                            "volume_step",
                        ),
                    )
                except (
                    BacktestConfigurationError,
                    TypeError,
                    ValueError,
                ) as exc:
                    raise BacktestConfigurationError(
                        f"Invalid symbol specification for " f"'{symbol}'.",
                    ) from exc
            else:
                raise BacktestConfigurationError(
                    f"Symbol specification for '{symbol}' must be "
                    "a BacktestSymbolSpecification or mapping.",
                )
            normalized_symbol = normalized_specification.symbol
            if normalized_symbol != symbol.strip().upper():
                raise BacktestConfigurationError(
                    f"Symbol specification key '{symbol}' does not "
                    f"match specification symbol "
                    f"'{normalized_symbol}'.",
                )
            normalized_specifications[normalized_symbol] = normalized_specification
        object.__setattr__(
            self,
            "symbol_specifications",
            normalized_specifications,
        )
        # ==============================================================
        # CLOSE POSITIONS
        # ==============================================================
        object.__setattr__(
            self,
            "close_positions_at_end",
            bool(
                self.close_positions_at_end,
            ),
        )
    @staticmethod
    def _normalize_datetime(
        value: datetime | None,
    ) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(
                tzinfo=timezone.utc,
            )
        return value.astimezone(
            timezone.utc,
        )
    @property
    def has_resolved_market_universe(self) -> bool:
        """Return whether symbols and timeframes are resolved."""
        return bool(
            self.symbols and self.timeframes,
        )
    @property
    def historical_range(
        self,
    ) -> tuple[datetime, datetime]:
        """Return the resolved historical range."""
        if self.start is None or self.end is None:
            raise BacktestConfigurationError(
                "Backtest historical range has not been resolved.",
            )
        return self.start, self.end
    def symbol_specification(
        self,
        symbol: str,
    ) -> BacktestSymbolSpecification | None:
        """Return the specification for one canonical symbol."""
        normalized_symbol = symbol.strip().upper()
        return self.symbol_specifications.get(
            normalized_symbol,
        )
# ======================================================================
# EXECUTION RECORD
# ======================================================================
@dataclass(frozen=True, slots=True)
class BacktestExecutionRecord:
    """Immutable execution record produced during a backtest."""
    timestamp: datetime
    order: ExecutionOrder
    result: ExecutionResult
    strategy_id: str | None = None
    strategy_name: str | None = None
    def __post_init__(self) -> None:
        timestamp = self.timestamp
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(
                tzinfo=timezone.utc,
            )
        else:
            timestamp = timestamp.astimezone(
                timezone.utc,
            )
        object.__setattr__(
            self,
            "timestamp",
            timestamp,
        )
# ======================================================================
# RUN STATE
# ======================================================================
@dataclass(slots=True)
class BacktestRun:
    """Runtime state and results for one backtest."""
    run_id: UUID
    config: BacktestConfig
    status: BacktestStatus = BacktestStatus.CREATED
    started_at: datetime | None = None
    completed_at: datetime | None = None
    current_time: datetime | None = None
    processed_events: int = 0
    processed_candles: int = 0
    executions: list[BacktestExecutionRecord] = field(
        default_factory=list,
    )
    pending_orders: list[UUID] = field(
        default_factory=list,
    )
    errors: list[str] = field(
        default_factory=list,
    )
    @property
    def duration_seconds(self) -> float | None:
        """Return wall-clock runtime duration."""
        if self.started_at is None or self.completed_at is None:
            return None
        return (self.completed_at - self.started_at).total_seconds()
# ======================================================================
# ENGINE
# ======================================================================
@dataclass(slots=True)
class BacktestEngine:
    """
    Chronological account-level backtest simulation engine.
    Multiple strategies submit into one shared portfolio.
    Responsibilities:
        - historical event sequencing
        - simulation clock
        - latest market state
        - pending-order processing
        - approved-order execution
        - SL/TP handling
        - portfolio marking
        - orchestration callback
    Strategy logic and risk evaluation remain outside this class.
    """

    EVENT_LOOP_YIELD_INTERVAL = 100

    market_data: BacktestMarketData
    config: BacktestConfig
    portfolio: BacktestPortfolio = field(
        init=False,
    )
    fill_engine: BacktestFillEngine = field(
        init=False,
    )
    execution: BacktestExecution = field(
        init=False,
    )
    pending_orders: BacktestPendingOrderBook = field(
        init=False,
    )
    run: BacktestRun = field(
        init=False,
    )
    _markets: dict[str, BacktestMarket] = field(
        init=False,
        default_factory=dict,
    )
    _latest_prices: dict[str, Decimal] = field(
        init=False,
        default_factory=dict,
    )
    strategy_handler: (
        Callable[
            ["BacktestEngine", BacktestMarketEvent],
            Awaitable[Any] | Any,
        ]
        | None
    ) = None
    risk_handler: (
        Callable[
            ["BacktestEngine", Any],
            Awaitable[Any] | Any,
        ]
        | None
    ) = None
    def __post_init__(self) -> None:
        if not isinstance(
            self.market_data,
            BacktestMarketData,
        ):
            raise BacktestConfigurationError(
                "market_data must be a BacktestMarketData instance.",
            )
        if not isinstance(
            self.config,
            BacktestConfig,
        ):
            raise BacktestConfigurationError(
                "config must be a BacktestConfig instance.",
            )
        self.portfolio = BacktestPortfolio(
            account_id=self.config.account_id,
            initial_balance=self.config.initial_balance,
        )
        self.fill_engine = BacktestFillEngine(
            self.config.fill,
        )
        if self.config.leverage is None:
            raise BacktestConfigurationError(
                "Backtest account leverage has not been resolved.",
            )
        margin_rate = Decimal("1") / self.config.leverage
        if not margin_rate.is_finite():
            raise BacktestConfigurationError(
                "Resolved backtest margin rate must be finite.",
            )
        if margin_rate <= Decimal("0"):
            raise BacktestConfigurationError(
                "Resolved backtest margin rate must be greater than zero.",
            )
        self.execution = BacktestExecution(
            portfolio=self.portfolio,
            fill_engine=self.fill_engine,
            margin_rate=margin_rate,
        )
        self.pending_orders = BacktestPendingOrderBook(
            fill_engine=self.fill_engine,
        )
        self.run = BacktestRun(
            run_id=uuid4(),
            config=self.config,
        )
    # ==================================================================
    # LIFECYCLE
    # ==================================================================
    async def run_backtest(
        self,
    ) -> BacktestRun:
        """
        Run the simulation through the configured historical range.
        """
        if self.run.status != BacktestStatus.CREATED:
            raise BacktestEngineError(
                "Backtest can only be started from CREATED state.",
            )
        self._validate_runtime_configuration()
        self.market_data.finalize()
        self.run.status = BacktestStatus.RUNNING
        self.run.started_at = datetime.now(
            timezone.utc,
        )
        try:
            events = self.market_data.events(
                symbols=set(
                    self.config.symbols,
                ),
                timeframes=set(
                    self.config.timeframes,
                ),
                start=self.config.start,
                end=self.config.end,
            )
            processed_any_event = False
            for event in events:
                if not self.is_running:
                    break
                processed_any_event = True
                await self._process_event(
                    event,
                )
                # Backtests are CPU-heavy and run inside an asyncio task.
                # Yield periodically so FastAPI can continue servicing
                # status, stop, health, and other API requests while the
                # simulation is running.
                if (
                    self.run.processed_events
                    % self.EVENT_LOOP_YIELD_INTERVAL
                    == 0
                ):
                    await asyncio.sleep(0)
            if self.is_running and not processed_any_event:
                raise BacktestEngineError(
                    "No historical market data was available for "
                    f"the requested range "
                    f"{self.config.start.isoformat()} -> "
                    f"{self.config.end.isoformat()} "
                    f"for symbols={self.config.symbols} "
                    f"timeframes={self.config.timeframes}.",
                )
            if self.is_running:
                if self.config.close_positions_at_end:
                    await self._close_open_positions()
                self._mark_portfolio_to_market()
                self.run.status = BacktestStatus.COMPLETED
        except Exception as exc:
            self.run.status = BacktestStatus.FAILED
            self.run.errors.append(
                f"{type(exc).__name__}: {exc}",
            )
            raise
        finally:
            self.run.completed_at = datetime.now(
                timezone.utc,
            )
        return self.run
    def stop(self) -> None:
        """
        Request cooperative termination after the current event.
        """
        if self.is_running:
            self.run.status = BacktestStatus.STOPPED
    def _validate_runtime_configuration(
        self,
    ) -> None:
        """Validate the resolved account-level simulation config."""
        if not isinstance(
            self.config.account_id,
            UUID,
        ):
            raise BacktestConfigurationError(
                "Backtest account_id is required.",
            )
        if not self.config.symbols:
            raise BacktestConfigurationError(
                "Backtest has no resolved symbols.",
            )
        if not self.config.timeframes:
            raise BacktestConfigurationError(
                "Backtest has no resolved timeframes.",
            )
        if self.config.start is None or self.config.end is None:
            raise BacktestConfigurationError(
                "Backtest historical range is not resolved.",
            )
        if self.config.start >= self.config.end:
            raise BacktestConfigurationError(
                "Backtest start must be before backtest end.",
            )
        if self.config.leverage is None:
            raise BacktestConfigurationError(
                "Backtest account leverage has not been resolved.",
            )
        if self.config.leverage <= Decimal("0"):
            raise BacktestConfigurationError(
                "Backtest account leverage must be greater than zero.",
            )
    # ==================================================================
    # EVENT PROCESSING
    # ==================================================================
    async def _process_event(
        self,
        event: BacktestMarketEvent,
    ) -> None:
        """
        Process one chronological market event.
        Order:
            1. advance clock
            2. update latest market state
            3. process pending orders
            4. process SL/TP exits
            5. dispatch strategy/risk orchestration
            6. mark portfolio to market
        """
        if not isinstance(
            event,
            BacktestMarketEvent,
        ):
            raise BacktestEngineError(
                "Backtest event must be a BacktestMarketEvent.",
            )
        if event.event_type.value != "CANDLE":
            raise BacktestEngineError(
                f"Unsupported market event type: {event.event_type!r}",
            )
        event_timestamp = self._normalize_datetime(
            event.timestamp,
        )
        if (
            self.run.current_time is not None
            and event_timestamp < self.run.current_time
        ):
            raise BacktestEngineError(
                "Backtest event time moved backwards. "
                f"Current={self.run.current_time.isoformat()}, "
                f"event={event_timestamp.isoformat()}.",
            )
        self.run.current_time = event_timestamp
        self.run.processed_events += 1
        self.run.processed_candles += 1
        market = self._market_from_event(
            event,
        )
        self._update_market(
            market,
        )
        # ==============================================================
        # Pending LIMIT / STOP orders
        # ==============================================================
        triggered_orders = self.pending_orders.process_market(
            market,
        )
        for pending_order in triggered_orders:
            self._apply_pending_fill(
                pending_order,
            )
        self._sync_pending_order_ids()
        # ==============================================================
        # Existing position SL / TP
        # ==============================================================
        exit_results = self.execution.check_position_exits(
            market=market,
            contract_sizes=self._resolved_contract_sizes(),
        )
        self._record_exit_results(
            results=exit_results,
            timestamp=event_timestamp,
        )
        # ==============================================================
        # Strategy -> Risk -> Execution orchestration
        # ==============================================================
        if self.strategy_handler is not None:
            await self._invoke_callback(
                self.strategy_handler,
                self,
                event,
            )
        # ==============================================================
        # Account valuation
        # ==============================================================
        self._mark_portfolio_to_market()
    # ==================================================================
    # MARKET STATE
    # ==================================================================
    @staticmethod
    def _market_from_event(
        event: BacktestMarketEvent,
    ) -> BacktestMarket:
        """
        Convert a historical candle event into a simulation market.
        Explicit bid/ask values are intentionally absent unless the
        market-data source supplies them.
        """
        return BacktestMarket(
            candle=event.candle,
        )
    def _update_market(
        self,
        market: BacktestMarket,
    ) -> None:
        """Update the latest executable market for a symbol."""
        symbol = self._normalize_symbol(
            market.symbol,
        )
        self._markets[symbol] = market
        self._latest_prices[symbol] = self._decimal(
            market.mid,
        )
    def _store_market(
        self,
        market: BacktestMarket,
    ) -> None:
        """Compatibility alias for older callers."""
        self._update_market(
            market,
        )
    def _current_market_for(
        self,
        symbol: str,
    ) -> BacktestMarket:
        """Return the latest known market snapshot for a symbol."""
        normalized_symbol = self._normalize_symbol(
            symbol,
        )
        try:
            return self._markets[normalized_symbol]
        except KeyError as exc:
            raise BacktestEngineError(
                f"No market data is available for " f"'{normalized_symbol}'.",
            ) from exc
    @property
    def current_markets(
        self,
    ) -> dict[str, BacktestMarket]:
        """Return a defensive copy of current market state."""
        return dict(
            self._markets,
        )
    @property
    def latest_prices(
        self,
    ) -> dict[str, Decimal]:
        """Return latest mark prices keyed by symbol."""
        return dict(
            self._latest_prices,
        )
    # ==================================================================
    # ORDER SUBMISSION
    # ==================================================================
    async def submit_order(
        self,
        order: ExecutionOrder,
        *,
        strategy_id: str | None = None,
        strategy_name: str | None = None,
        expiration: datetime | None = None,
    ) -> ExecutionResult | PendingBacktestOrder:
        """
        Submit an approved execution order into the simulation.
        MARKET:
            execute immediately against the current market.
        LIMIT / STOP:
            register with the pending-order book.
        Every order must belong to the simulated account.
        """
        if not self.is_running:
            raise BacktestEngineError(
                "Orders can only be submitted while the " "backtest is running.",
            )
        if not isinstance(
            order,
            ExecutionOrder,
        ):
            raise BacktestEngineError(
                "submit_order() requires an ExecutionOrder.",
            )
        if order.account_id is None:
            raise BacktestEngineError(
                "ExecutionOrder account_id is required for backtesting.",
            )
        if order.account_id != self.config.account_id:
            raise BacktestEngineError(
                "ExecutionOrder account does not match the " "backtest account.",
            )
        normalized_symbol = self._normalize_symbol(
            order.symbol,
        )
        if normalized_symbol not in self.config.symbols:
            raise BacktestEngineError(
                f"Order symbol '{normalized_symbol}' is not part "
                "of the backtest symbol universe.",
            )
        market = self._current_market_for(
            normalized_symbol,
        )
        resolved_strategy_id = (
            strategy_id.strip()
            if isinstance(
                strategy_id,
                str,
            )
            and strategy_id.strip()
            else None
        )
        resolved_strategy_name = (
            strategy_name.strip()
            if isinstance(
                strategy_name,
                str,
            )
            and strategy_name.strip()
            else None
        )
        context = BacktestExecutionContext(
            strategy_id=resolved_strategy_id,
            strategy_name=resolved_strategy_name,
            magic_number=order.magic_number,
        )
        contract_size = self._contract_size(
            normalized_symbol,
        )
        # ==============================================================
        # MARKET
        # ==============================================================
        if order.order_type == OrderType.MARKET:
            result = self.execution.execute(
                order=order,
                market=market,
                context=context,
                contract_size=contract_size,
            )
            self._record_execution(
                order=order,
                result=result,
                timestamp=market.timestamp,
                strategy_id=resolved_strategy_id,
                strategy_name=resolved_strategy_name,
            )
            self._mark_portfolio_to_market()
            return result
        # ==============================================================
        # LIMIT / STOP
        # ==============================================================
        if order.order_type in {
            OrderType.LIMIT,
            OrderType.STOP,
        }:
            pending = self.pending_orders.add(
                order=order,
                created_at=market.timestamp,
                expiration=expiration,
                strategy_id=resolved_strategy_id,
                strategy_name=resolved_strategy_name,
            )
            self._sync_pending_order_ids()
            return pending
        raise BacktestEngineError(
            f"Unsupported execution order type: {order.order_type!r}",
        )
    # ==================================================================
    # PENDING ORDERS
    # ==================================================================
    def _apply_pending_fill(
        self,
        pending: PendingBacktestOrder,
    ) -> None:
        """
        Apply a pending order after the pending-order book has generated
        its fill.
        """
        if not isinstance(
            pending,
            PendingBacktestOrder,
        ):
            raise BacktestEngineError(
                "pending must be a PendingBacktestOrder.",
            )
        fill = pending.fill
        if fill is None or not fill.filled:
            return
        try:
            normalized_symbol = self._normalize_symbol(
                pending.order.symbol,
            )
            contract_size = self._contract_size(
                normalized_symbol,
            )
            result = self.execution.apply_pending_fill(
                order=pending.order,
                fill=fill,
                context=BacktestExecutionContext(
                    strategy_id=pending.strategy_id,
                    strategy_name=pending.strategy_name,
                    magic_number=pending.order.magic_number,
                ),
                contract_size=contract_size,
            )
        except Exception as exc:
            raise BacktestEngineError(
                "Failed to apply a pending-order fill: " f"{type(exc).__name__}: {exc}",
            ) from exc
        self._record_execution(
            order=pending.order,
            result=result,
            timestamp=fill.timestamp,
            strategy_id=pending.strategy_id,
            strategy_name=pending.strategy_name,
        )
        self._mark_portfolio_to_market()
    # ==================================================================
    # EXECUTION RECORDING
    # ==================================================================
    def _record_execution(
        self,
        *,
        order: ExecutionOrder,
        result: ExecutionResult,
        timestamp: datetime,
        strategy_id: str | None,
        strategy_name: str | None,
    ) -> None:
        """Append one immutable execution record to the current run."""
        self.run.executions.append(
            BacktestExecutionRecord(
                timestamp=timestamp,
                order=order,
                result=result,
                strategy_id=strategy_id,
                strategy_name=strategy_name,
            ),
        )
    def _record_exit_results(
        self,
        *,
        results: list[ExecutionResult],
        timestamp: datetime,
    ) -> None:
        """Record internally generated SL/TP execution results."""
        for result in results:
            broker_position_id = result.broker_position_id
            if broker_position_id is None:
                continue
            position = self._find_position_by_broker_id(
                broker_position_id,
            )
            if position is None:
                continue
            order_side = (
                OrderSide.SELL
                if position.side == BacktestPositionSide.LONG
                else OrderSide.BUY
            )
            order = ExecutionOrder(
                symbol=position.symbol,
                account_id=position.account_id,
                side=order_side,
                order_type=OrderType.MARKET,
                volume=position.volume,
            )
            self._record_execution(
                order=order,
                result=result,
                timestamp=timestamp,
                strategy_id=position.strategy_id,
                strategy_name=position.strategy_name,
            )
    def _find_position_by_broker_id(
        self,
        broker_position_id: int,
    ):
        """Find a portfolio position by its broker-compatible ID."""
        for position in self.portfolio.positions.values():
            if (
                self._uuid_as_int(
                    position.position_id,
                )
                == broker_position_id
            ):
                return position
        return None
    # ==================================================================
    # PORTFOLIO
    # ==================================================================
    def _mark_portfolio_to_market(
        self,
    ) -> Decimal:
        """
        Mark the shared account using the latest known price for each
        available symbol.
        """
        if not self._latest_prices:
            return self._decimal(
                self.portfolio.balance,
            )
        return self.portfolio.mark_to_market(
            prices=self._latest_prices,
            contract_sizes=self._resolved_contract_sizes(),
            timestamp=self.run.current_time,
        )
    def _resolved_contract_sizes(
        self,
    ) -> dict[str, Decimal]:
        """
        Resolve a complete contract-size map for the backtest universe.
        Resolution order:
            1. explicit BacktestConfig.contract_sizes
            2. AccountSymbol-derived specification
            3. XAUUSD legacy default of 100
            4. generic legacy default of 1
        Explicit contract-size configuration therefore remains
        backward-compatible and has highest precedence.
        """
        resolved: dict[str, Decimal] = {}
        for symbol in self.config.symbols:
            normalized_symbol = self._normalize_symbol(
                symbol,
            )
            resolved[normalized_symbol] = self._contract_size(
                normalized_symbol,
            )
        for symbol, value in self.config.contract_sizes.items():
            normalized_symbol = self._normalize_symbol(
                symbol,
            )
            resolved[normalized_symbol] = self._decimal(
                value,
            )
        return resolved
    def _contract_size(
        self,
        symbol: str,
    ) -> Decimal:
        """
        Return the resolved contract size for one symbol.
        Explicit configuration takes precedence over AccountSymbol
        metadata, preserving the previous BacktestConfig behavior.
        """
        normalized_symbol = self._normalize_symbol(
            symbol,
        )
        configured = self.config.contract_sizes.get(
            normalized_symbol,
        )
        if configured is not None:
            return self._decimal(
                configured,
            )
        specification = self.config.symbol_specification(
            normalized_symbol,
        )
        if specification is not None:
            if specification.contract_size is not None:
                return self._decimal(
                    specification.contract_size,
                )
        # Preserve the existing XAUUSD behavior until the account
        # provides an actual contract specification.
        if normalized_symbol in {
            "XAUUSD",
            "XAUUSD.S",
        }:
            return Decimal("100")
        # Preserve the existing generic fallback.
        return Decimal("1")
    # ==================================================================
    # END OF BACKTEST
    # ==================================================================
    async def _close_open_positions(
        self,
    ) -> None:
        """
        Close every remaining open position using the latest known
        market for its symbol.
        """
        open_positions = list(
            self.portfolio.open_positions,
        )
        for position in open_positions:
            if not position.is_open:
                continue
            market = self._current_market_for(
                position.symbol,
            )
            contract_size = self._contract_size(
                position.symbol,
            )
            result = self.execution.close_position(
                position_id=position.position_id,
                market=market,
                exit_reason="BACKTEST_END",
                contract_size=contract_size,
            )
            order_side = (
                OrderSide.SELL
                if position.side == BacktestPositionSide.LONG
                else OrderSide.BUY
            )
            order = ExecutionOrder(
                symbol=position.symbol,
                account_id=position.account_id,
                side=order_side,
                order_type=OrderType.MARKET,
                volume=position.volume,
            )
            self._record_execution(
                order=order,
                result=result,
                timestamp=market.timestamp,
                strategy_id=position.strategy_id,
                strategy_name=position.strategy_name,
            )
        self._mark_portfolio_to_market()
    # ==================================================================
    # CALLBACKS
    # ==================================================================
    @staticmethod
    async def _invoke_callback(
        callback: Callable[..., Awaitable[Any] | Any],
        *args: Any,
    ) -> Any:
        """
        Invoke a synchronous or asynchronous callback.
        """
        result = callback(
            *args,
        )
        if inspect.isawaitable(
            result,
        ):
            return await result
        return result
    # ==================================================================
    # STATE / METRICS
    # ==================================================================
    @property
    def is_running(
        self,
    ) -> bool:
        """Return whether the backtest is currently running."""
        return self.run.status == BacktestStatus.RUNNING
    @property
    def is_completed(
        self,
    ) -> bool:
        """Return whether the backtest completed successfully."""
        return self.run.status == BacktestStatus.COMPLETED
    @property
    def equity(
        self,
    ) -> Decimal:
        """Return current marked account equity."""
        return self._mark_portfolio_to_market()
    @property
    def balance(
        self,
    ) -> Decimal:
        """Return current account balance."""
        return self.portfolio.balance
    @property
    def realized_pnl(
        self,
    ) -> Decimal:
        """Return realized portfolio P&L."""
        return self.portfolio.realized_pnl
    @property
    def unrealized_pnl(
        self,
    ) -> Decimal:
        """Return floating P&L across currently open positions."""
        if not self.portfolio.open_positions:
            return Decimal("0")
        if not self._latest_prices:
            return Decimal("0")
        return self.portfolio.total_unrealized_pnl(
            prices=self._latest_prices,
            contract_sizes=self._resolved_contract_sizes(),
        )
    # ==================================================================
    # PENDING ORDER STATE
    # ==================================================================
    def _sync_pending_order_ids(
        self,
    ) -> None:
        """Synchronize run-level pending IDs with the pending-order book."""
        self.run.pending_orders = [
            pending.order_id for pending in self.pending_orders.pending()
        ]
    # ==================================================================
    # COMPATIBILITY
    # ==================================================================
    def _process_market_storage(
        self,
        market: BacktestMarket,
    ) -> None:
        """Compatibility alias for older callers."""
        self._store_market(
            market,
        )
    # ==================================================================
    # HELPERS
    # ==================================================================
    @staticmethod
    def _normalize_symbol(
        symbol: str,
    ) -> str:
        if not isinstance(
            symbol,
            str,
        ):
            raise BacktestEngineError(
                "Symbol must be a string.",
            )
        normalized = symbol.strip().upper()
        if not normalized:
            raise BacktestEngineError(
                "Symbol cannot be empty.",
            )
        return normalized
    @staticmethod
    def _normalize_datetime(
        value: datetime,
    ) -> datetime:
        if not isinstance(
            value,
            datetime,
        ):
            raise BacktestEngineError(
                "Backtest timestamps must be datetime values.",
            )
        if value.tzinfo is None:
            return value.replace(
                tzinfo=timezone.utc,
            )
        return value.astimezone(
            timezone.utc,
        )
    @staticmethod
    def _decimal(
        value: Any,
    ) -> Decimal:
        """
        Convert a numeric value to a finite Decimal.
        """
        if isinstance(
            value,
            Decimal,
        ):
            result = value
        else:
            if value is None:
                raise BacktestEngineError(
                    "None cannot be converted to Decimal.",
                )
            try:
                result = Decimal(
                    str(value),
                )
            except Exception as exc:
                raise BacktestEngineError(
                    f"Invalid decimal value: {value!r}",
                ) from exc
        if not result.is_finite():
            raise BacktestEngineError(
                f"Decimal value must be finite: {value!r}",
            )
        return result
    @staticmethod
    def _uuid_as_int(
        value: UUID,
    ) -> int:
        """
        Produce a deterministic positive broker-compatible identifier.
        UUID remains the authoritative position identity.
        """
        if not isinstance(
            value,
            UUID,
        ):
            raise BacktestEngineError(
                "Broker identifier source must be a UUID.",
            )
        return value.int % (2**63 - 1) or 1
