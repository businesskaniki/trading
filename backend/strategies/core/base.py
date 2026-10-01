"""Base strategy abstractions and runtime configuration for the AQE Strategy Engine."""

from __future__ import annotations

import logging
from abc import ABC
from dataclasses import dataclass, field
from typing import Any, ClassVar
from uuid import UUID

from app.events.market import MarketCandleEvent, MarketTickEvent
from app.market_data.models import MarketCandle, MarketTick

from .context import StrategyContext
from .enums import StrategyMode, StrategyStatus
from .exceptions import (
    StrategyConfigurationError,
    StrategyExecutionError,
    StrategyStateError,
)
from .signal import TradingSignal

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class StrategyConfig:
    """
    Runtime configuration for one strategy instance.

    StrategyConfig describes how one strategy implementation is deployed
    at runtime.

    One StrategyConfig represents one strategy instance operating across
    its complete configured symbol universe:

        EMA Trend
            ├── XAUUSD.s
            ├── AUDCAD.s
            └── EURUSD

    The configuration is intentionally separate from StrategyDefinition.

    StrategyDefinition describes the implementation itself:

        name
        version
        description
        author
        tags

    StrategyConfig describes one runtime deployment:

        strategy_id
        strategy_name
        mode
        account_id
        symbols
        timeframes
        parameters
        metadata
        enabled
    """

    strategy_id: str
    strategy_name: str
    mode: StrategyMode

    enabled: bool = True
    account_id: UUID | None = None

    symbols: list[str] = field(default_factory=list)
    timeframes: list[str] = field(default_factory=list)

    parameters: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Validate and normalize runtime configuration."""

        # --------------------------------------------------------------
        # Identity
        # --------------------------------------------------------------

        self.strategy_id = str(self.strategy_id).strip()
        self.strategy_name = str(self.strategy_name).strip().lower()

        if not self.strategy_id:
            raise StrategyConfigurationError(
                "Strategy configuration requires a non-empty strategy_id."
            )

        if not self.strategy_name:
            raise StrategyConfigurationError(
                "Strategy configuration requires a non-empty strategy_name."
            )

        # --------------------------------------------------------------
        # Mode
        # --------------------------------------------------------------

        if not isinstance(self.mode, StrategyMode):
            try:
                self.mode = StrategyMode(str(self.mode).strip().lower())
            except (TypeError, ValueError) as exc:
                raise StrategyConfigurationError(
                    f"Unsupported strategy mode: {self.mode!r}."
                ) from exc

        # --------------------------------------------------------------
        # Account
        # --------------------------------------------------------------

        if self.account_id is not None:
            if not isinstance(self.account_id, UUID):
                try:
                    self.account_id = UUID(str(self.account_id))
                except (TypeError, ValueError) as exc:
                    raise StrategyConfigurationError(
                        "account_id must be a valid UUID or None."
                    ) from exc

        # --------------------------------------------------------------
        # Symbols
        # --------------------------------------------------------------

        if self.symbols is None:
            self.symbols = []

        try:
            normalized_symbols = [
                str(symbol).strip() for symbol in self.symbols if str(symbol).strip()
            ]
        except TypeError as exc:
            raise StrategyConfigurationError(
                "symbols must be an iterable of symbol identifiers."
            ) from exc

        if not normalized_symbols:
            raise StrategyConfigurationError(
                f"Strategy '{self.strategy_id}' must define at least one symbol."
            )

        self.symbols = normalized_symbols

        # --------------------------------------------------------------
        # Timeframes
        # --------------------------------------------------------------

        if self.timeframes is None:
            self.timeframes = []

        try:
            normalized_timeframes = [
                str(timeframe).strip().upper()
                for timeframe in self.timeframes
                if str(timeframe).strip()
            ]
        except TypeError as exc:
            raise StrategyConfigurationError(
                "timeframes must be an iterable of timeframe identifiers."
            ) from exc

        if not normalized_timeframes:
            raise StrategyConfigurationError(
                f"Strategy '{self.strategy_id}' must define at least one timeframe."
            )

        self.timeframes = normalized_timeframes

        # --------------------------------------------------------------
        # Parameters
        # --------------------------------------------------------------

        if self.parameters is None:
            self.parameters = {}

        if not isinstance(self.parameters, dict):
            raise StrategyConfigurationError(
                "strategy parameters must be a dictionary."
            )

        self.parameters = dict(self.parameters)

        # --------------------------------------------------------------
        # Metadata
        # --------------------------------------------------------------

        if self.metadata is None:
            self.metadata = {}

        if not isinstance(self.metadata, dict):
            raise StrategyConfigurationError("strategy metadata must be a dictionary.")

        self.metadata = dict(self.metadata)

        # --------------------------------------------------------------
        # Enabled
        # --------------------------------------------------------------

        self.enabled = bool(self.enabled)

    def snapshot(self) -> dict[str, Any]:
        """Return a serializable runtime configuration snapshot."""

        return {
            "strategy_id": self.strategy_id,
            "strategy_name": self.strategy_name,
            "mode": self.mode.value,
            "enabled": self.enabled,
            "account_id": (
                str(self.account_id) if self.account_id is not None else None
            ),
            "symbols": list(self.symbols),
            "timeframes": list(self.timeframes),
            "parameters": dict(self.parameters),
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True, slots=True)
class StrategyDefinition:
    """
    Static metadata describing a strategy implementation.

    A StrategyDefinition belongs to the strategy class, not to an
    individual runtime instance.
    """

    name: str
    version: str = "1.0.0"
    description: str = ""
    author: str = "AQE"
    tags: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        """Validate and normalize strategy definition metadata."""

        normalized_name = self.name.strip().lower()
        normalized_version = self.version.strip()
        normalized_description = self.description.strip()
        normalized_author = self.author.strip()

        if not normalized_name:
            raise ValueError("Strategy definition name cannot be empty.")

        if not normalized_version:
            raise ValueError("Strategy definition version cannot be empty.")

        if not normalized_author:
            raise ValueError("Strategy definition author cannot be empty.")

        normalized_tags = tuple(
            tag.strip().lower() for tag in self.tags if tag and tag.strip()
        )

        object.__setattr__(
            self,
            "name",
            normalized_name,
        )
        object.__setattr__(
            self,
            "version",
            normalized_version,
        )
        object.__setattr__(
            self,
            "description",
            normalized_description,
        )
        object.__setattr__(
            self,
            "author",
            normalized_author,
        )
        object.__setattr__(
            self,
            "tags",
            normalized_tags,
        )

    def snapshot(self) -> dict[str, Any]:
        """Return a serializable representation of the definition."""

        return {
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "author": self.author,
            "tags": list(self.tags),
        }


class BaseStrategy(ABC):
    """
    Abstract base class for all AQE trading strategies.

    A strategy is responsible only for:

        - analysing market data
        - maintaining strategy-specific state
        - generating TradingSignal objects

    A strategy must never:

        - place broker orders
        - communicate directly with MT5
        - communicate directly with Redis
        - perform risk checks
        - perform position sizing
        - bypass the AQE execution pipeline

    The strategy receives normalized domain market data through the
    runtime boundary and returns TradingSignal objects to the runtime
    layer.

    Event envelopes such as MarketCandleEvent and MarketTickEvent remain
    infrastructure/runtime concerns. Concrete strategies receive the
    underlying MarketCandle or MarketTick objects.

    ------------------------------------------------------------------
    STRATEGY DEFINITION
    ------------------------------------------------------------------

    Every concrete strategy must provide a class-level
    ``StrategyDefinition``:

        class MyStrategy(BaseStrategy):
            definition = StrategyDefinition(
                name="my_strategy",
                ...
            )

    ------------------------------------------------------------------
    RUNTIME CONFIGURATION
    ------------------------------------------------------------------

    Each strategy instance receives its own StrategyConfig and context.

    The instance can therefore represent one strategy operating across
    multiple selected symbols.

    ------------------------------------------------------------------
    ACTIVATION
    ------------------------------------------------------------------

    Registration and activation are separate concerns.

    Lifecycle:

        CREATED -> READY -> RUNNING -> PAUSED -> STOPPED

    Activation:

        enabled / disabled

    A disabled strategy remains present in the runtime but does not
    process market-data events.
    """

    definition: ClassVar[StrategyDefinition]

    def __init__(
        self,
        *,
        config: StrategyConfig,
        context: StrategyContext,
    ) -> None:
        """
        Initialize a strategy instance.

        Args:
            config:
                Runtime strategy configuration.

            context:
                Runtime context containing market data, positions,
                state, clock, parameters, symbols, and metadata.
        """

        if not isinstance(config, StrategyConfig):
            raise StrategyConfigurationError(
                "Strategy config must be a StrategyConfig instance."
            )

        if not isinstance(context, StrategyContext):
            raise StrategyConfigurationError(
                "Strategy context must be a StrategyContext instance."
            )

        self._config = config
        self._context = context

        self._status = StrategyStatus.CREATED

        # Activation is runtime state.
        #
        # The initial value comes from configuration, while subsequent
        # activate()/deactivate() calls are controlled by the runtime
        # manager.
        self._enabled = bool(config.enabled)

        self._validate_definition()
        self._validate_configuration()

        logger.debug(
            "Strategy created: id=%s name=%s definition=%s "
            "mode=%s enabled=%s symbols=%s timeframes=%s",
            self.strategy_id,
            self.strategy_name,
            self.definition.name,
            self.mode.value,
            self.is_enabled,
            self.symbols,
            self.timeframes,
        )

    # ==================================================================
    # CLASS-LEVEL DEFINITION
    # ==================================================================

    @classmethod
    def get_definition(cls) -> StrategyDefinition:
        """
        Return the static definition of the strategy implementation.

        This method is safe to call on the class without constructing
        a strategy instance.
        """

        definition = getattr(
            cls,
            "definition",
            None,
        )

        if not isinstance(
            definition,
            StrategyDefinition,
        ):
            raise StrategyConfigurationError(
                f"Strategy class '{cls.__name__}' must define a "
                "StrategyDefinition in the 'definition' class attribute."
            )

        return definition

    # ==================================================================
    # CORE PROPERTIES
    # ==================================================================

    @property
    def config(self) -> StrategyConfig:
        """Return the strategy runtime configuration."""

        return self._config

    @property
    def context(self) -> StrategyContext:
        """Return the strategy runtime context."""

        return self._context

    @property
    def strategy_id(self) -> str:
        """Return the unique runtime strategy instance identifier."""

        return self.config.strategy_id

    @property
    def strategy_name(self) -> str:
        """
        Return the runtime strategy name.

        The runtime configuration normally contains the registered
        strategy name. The implementation definition remains available
        separately through ``definition``.
        """

        return self.config.strategy_name

    @property
    def mode(self) -> StrategyMode:
        """Return the strategy execution mode."""

        return self.config.mode

    @property
    def status(self) -> StrategyStatus:
        """Return the current strategy lifecycle state."""

        return self._status

    @property
    def symbols(self) -> tuple[str, ...]:
        """
        Return all symbols monitored by this strategy instance.
        """

        return tuple(self.config.symbols)

    @property
    def timeframes(self) -> tuple[str, ...]:
        """Return all timeframes monitored by this strategy."""

        return tuple(self.config.timeframes)

    @property
    def parameters(self) -> dict[str, Any]:
        """Return strategy-specific parameters."""

        return dict(self.config.parameters)

    @property
    def metadata(self) -> dict[str, Any]:
        """Return strategy metadata."""

        return dict(self.config.metadata)

    @property
    def is_enabled(self) -> bool:
        """
        Return whether this strategy instance is administratively enabled.
        """

        return self._enabled

    @property
    def is_running(self) -> bool:
        """Return whether the strategy lifecycle is RUNNING."""

        return self.status is StrategyStatus.RUNNING

    @property
    def is_active(self) -> bool:
        """
        Return whether the strategy is currently allowed to process
        market data.

        A strategy must be:

            1. enabled
            2. READY or RUNNING

        PAUSED strategies are inactive even when enabled.
        """

        return self.is_enabled and self.status in {
            StrategyStatus.READY,
            StrategyStatus.RUNNING,
        }

    # ==================================================================
    # ACTIVATION
    # ==================================================================

    def activate(self) -> None:
        """
        Activate the strategy for market-data processing.

        Activation does not start the lifecycle.
        """

        if self.status is StrategyStatus.STOPPED:
            raise StrategyStateError(
                f"Strategy '{self.strategy_id}' cannot be activated "
                "because it is STOPPED."
            )

        if self.status is StrategyStatus.ERROR:
            raise StrategyStateError(
                f"Strategy '{self.strategy_id}' cannot be activated "
                "because it is in ERROR state."
            )

        if self._enabled:
            return

        self._enabled = True

        logger.info(
            "Strategy activated: id=%s name=%s status=%s",
            self.strategy_id,
            self.strategy_name,
            self.status.value,
        )

    def deactivate(self) -> None:
        """
        Deactivate the strategy.

        Deactivation does not stop the lifecycle or destroy strategy
        state. It simply prevents market-data processing.
        """

        if self.status is StrategyStatus.STOPPED:
            return

        if not self._enabled:
            return

        self._enabled = False

        logger.info(
            "Strategy deactivated: id=%s name=%s status=%s",
            self.strategy_id,
            self.strategy_name,
            self.status.value,
        )

    # ==================================================================
    # LIFECYCLE
    # ==================================================================

    async def initialize(self) -> None:
        """
        Initialize the strategy.

        Initialization is performed once before the strategy is started.
        """

        if self.status is not StrategyStatus.CREATED:
            raise StrategyStateError(
                f"Strategy '{self.strategy_id}' cannot be initialized "
                f"from state '{self.status.value}'."
            )

        try:
            await self.on_initialize()

        except StrategyConfigurationError:
            self._status = StrategyStatus.ERROR
            raise

        except Exception as exc:
            self._status = StrategyStatus.ERROR

            raise StrategyExecutionError(
                f"Strategy '{self.strategy_id}' failed during initialization."
            ) from exc

        self._status = StrategyStatus.READY

        logger.info(
            "Strategy initialized: id=%s name=%s enabled=%s active=%s",
            self.strategy_id,
            self.strategy_name,
            self.is_enabled,
            self.is_active,
        )

    async def start(self) -> None:
        """
        Start the strategy lifecycle.

        Starting does not automatically activate a disabled strategy.
        """

        if self.status is StrategyStatus.CREATED:
            raise StrategyStateError(
                f"Strategy '{self.strategy_id}' must be initialized "
                "before it can be started."
            )

        if self.status is StrategyStatus.RUNNING:
            return

        if self.status is StrategyStatus.PAUSED:
            raise StrategyStateError(
                f"Strategy '{self.strategy_id}' is paused. "
                "Use resume() instead of start()."
            )

        if self.status is StrategyStatus.STOPPED:
            raise StrategyStateError(
                f"Strategy '{self.strategy_id}' cannot be restarted "
                "from STOPPED state. Recreate the strategy instance."
            )

        if self.status is StrategyStatus.ERROR:
            raise StrategyStateError(
                f"Strategy '{self.strategy_id}' is in ERROR state "
                "and cannot be started."
            )

        try:
            await self.on_start()

        except Exception as exc:
            self._status = StrategyStatus.ERROR

            raise StrategyExecutionError(
                f"Strategy '{self.strategy_id}' failed during start."
            ) from exc

        self._status = StrategyStatus.RUNNING

        logger.info(
            "Strategy started: id=%s name=%s enabled=%s active=%s",
            self.strategy_id,
            self.strategy_name,
            self.is_enabled,
            self.is_active,
        )

    async def pause(self) -> None:
        """
        Pause strategy processing.

        Market-data infrastructure remains active, but this strategy
        becomes inactive and no longer processes market events.
        """

        if self.status is not StrategyStatus.RUNNING:
            raise StrategyStateError(
                f"Strategy '{self.strategy_id}' can only be paused "
                f"from RUNNING state. Current state={self.status.value}."
            )

        try:
            await self.on_pause()

        except Exception as exc:
            self._status = StrategyStatus.ERROR

            raise StrategyExecutionError(
                f"Strategy '{self.strategy_id}' failed during pause."
            ) from exc

        self._status = StrategyStatus.PAUSED

        logger.info(
            "Strategy paused: id=%s name=%s",
            self.strategy_id,
            self.strategy_name,
        )

    async def resume(self) -> None:
        """
        Resume strategy processing after a pause.

        The strategy becomes active only when it is also enabled.
        """

        if self.status is not StrategyStatus.PAUSED:
            raise StrategyStateError(
                f"Strategy '{self.strategy_id}' can only be resumed "
                f"from PAUSED state. Current state={self.status.value}."
            )

        try:
            await self.on_resume()

        except Exception as exc:
            self._status = StrategyStatus.ERROR

            raise StrategyExecutionError(
                f"Strategy '{self.strategy_id}' failed during resume."
            ) from exc

        self._status = StrategyStatus.RUNNING

        logger.info(
            "Strategy resumed: id=%s name=%s enabled=%s active=%s",
            self.strategy_id,
            self.strategy_name,
            self.is_enabled,
            self.is_active,
        )

    async def stop(self) -> None:
        """
        Stop the strategy.

        STOPPED is a terminal runtime state for the current instance.
        """

        if self.status is StrategyStatus.STOPPED:
            return

        try:
            await self.on_stop()

        except Exception as exc:
            self._status = StrategyStatus.ERROR

            raise StrategyExecutionError(
                f"Strategy '{self.strategy_id}' failed during stop."
            ) from exc

        self._status = StrategyStatus.STOPPED

        logger.info(
            "Strategy stopped: id=%s name=%s",
            self.strategy_id,
            self.strategy_name,
        )

    # ==================================================================
    # MARKET-DATA CAPABILITY
    # ==================================================================

    def supports_tick(
        self,
        symbol: str,
    ) -> bool:
        """
        Return whether this strategy should receive tick events for
        the supplied symbol.
        """

        if not self.is_active:
            return False

        return symbol in self.symbols

    def supports_candle(
        self,
        *,
        symbol: str,
        timeframe: str,
    ) -> bool:
        """
        Return whether this strategy should receive candle events for
        the supplied symbol and timeframe.
        """

        if not self.is_active:
            return False

        return symbol in self.symbols and timeframe.strip().upper() in self.timeframes

    # ==================================================================
    # MARKET-DATA HANDLERS
    # ==================================================================

    async def handle_tick(
        self,
        event: MarketTickEvent,
    ) -> TradingSignal | list[TradingSignal] | tuple[TradingSignal, ...] | None:
        """
        Process a market tick event.

        The runtime receives a MarketTickEvent, but concrete strategies
        receive the normalized MarketTick domain object.
        """

        if not self.is_active:
            return None

        if not self.supports_tick(event.symbol):
            return None

        try:
            return await self.on_tick(event.tick)

        except StrategyExecutionError:
            raise

        except Exception as exc:
            raise StrategyExecutionError(
                f"Strategy '{self.strategy_id}' failed while processing tick."
            ) from exc

    async def handle_candle(
        self,
        event: MarketCandleEvent,
    ) -> TradingSignal | list[TradingSignal] | tuple[TradingSignal, ...] | None:
        """
        Process a market candle event.

        The runtime receives a MarketCandleEvent envelope. The concrete
        strategy receives the underlying MarketCandle domain object.

        This boundary is intentional:

            MarketCandleEvent
                └── candle: MarketCandle
                              │
                              ├── open
                              ├── high
                              ├── low
                              ├── close
                              └── ...

        This prevents concrete strategies from depending on event
        infrastructure and ensures their candle contract matches the
        actual OHLC data they analyse.
        """

        if not self.is_active:
            return None

        if not self.supports_candle(
            symbol=event.symbol,
            timeframe=event.timeframe,
        ):
            return None

        try:
            return await self.on_candle(event.candle)

        except StrategyExecutionError:
            raise

        except Exception as exc:
            raise StrategyExecutionError(
                f"Strategy '{self.strategy_id}' failed while processing candle."
            ) from exc

    # ==================================================================
    # STRATEGY HOOKS
    # ==================================================================

    async def on_initialize(self) -> None:
        """
        Strategy-specific initialization hook.

        Concrete strategies may override this method.
        """

    async def on_start(self) -> None:
        """
        Strategy-specific start hook.

        Concrete strategies may override this method.
        """

    async def on_pause(self) -> None:
        """
        Strategy-specific pause hook.

        Concrete strategies may override this method.
        """

    async def on_resume(self) -> None:
        """
        Strategy-specific resume hook.

        Concrete strategies may override this method.
        """

    async def on_stop(self) -> None:
        """
        Strategy-specific stop hook.

        Concrete strategies may override this method.
        """

    async def on_tick(
        self,
        tick: MarketTick,
    ) -> TradingSignal | list[TradingSignal] | tuple[TradingSignal, ...] | None:
        """
        Optional market-tick analysis hook.

        Concrete strategies receive the normalized MarketTick object,
        not the MarketTickEvent envelope.
        """

        return None

    async def on_candle(
        self,
        candle: MarketCandle,
    ) -> TradingSignal | list[TradingSignal] | tuple[TradingSignal, ...] | None:
        """
        Optional market-candle analysis hook.

        Concrete strategies receive the normalized MarketCandle object,
        not the MarketCandleEvent envelope.

        Candle-based implementations can therefore safely access:

            candle.open
            candle.high
            candle.low
            candle.close
            candle.volume
            candle.symbol
            candle.timeframe
        """

        return None

    # ==================================================================
    # VALIDATION
    # ==================================================================

    def _validate_definition(self) -> None:
        """Validate the concrete strategy definition."""

        definition = getattr(
            type(self),
            "definition",
            None,
        )

        if not isinstance(
            definition,
            StrategyDefinition,
        ):
            raise StrategyConfigurationError(
                f"Strategy class '{type(self).__name__}' must define "
                "a class-level StrategyDefinition."
            )

    def _validate_configuration(self) -> None:
        """
        Validate strategy runtime configuration.

        StrategyConfig performs structural validation. This layer
        validates requirements specific to the strategy runtime.
        """

        if not self.strategy_id:
            raise StrategyConfigurationError(
                "Strategy instance requires a strategy_id."
            )

        if not self.strategy_name:
            raise StrategyConfigurationError(
                "Strategy instance requires a strategy_name."
            )

        if not self.symbols:
            raise StrategyConfigurationError(
                f"Strategy '{self.strategy_id}' must define at least one symbol."
            )

        if not self.timeframes:
            raise StrategyConfigurationError(
                f"Strategy '{self.strategy_id}' must define at least one timeframe."
            )

        if self.mode not in {
            StrategyMode.LIVE,
            StrategyMode.PAPER,
            StrategyMode.BACKTEST,
            StrategyMode.REPLAY,
        }:
            raise StrategyConfigurationError(
                f"Strategy '{self.strategy_id}' has unsupported "
                f"execution mode: {self.mode!r}."
            )

        if (
            self.mode
            in {
                StrategyMode.LIVE,
                StrategyMode.PAPER,
            }
            and self.config.account_id is None
        ):
            raise StrategyConfigurationError(
                f"Strategy '{self.strategy_id}' running in "
                f"{self.mode.value} mode requires an account_id."
            )

    # ==================================================================
    # SNAPSHOT
    # ==================================================================

    def snapshot(self) -> dict[str, Any]:
        """
        Return a lightweight runtime snapshot.

        This snapshot is intended for management APIs, monitoring,
        frontend state, and diagnostics.
        """

        return {
            "strategy_id": self.strategy_id,
            "strategy_name": self.strategy_name,
            "definition": self.definition.snapshot(),
            "config": self.config.snapshot(),
            "mode": self.mode.value,
            "status": self.status.value,
            "enabled": self.is_enabled,
            "active": self.is_active,
            "symbols": list(self.symbols),
            "timeframes": list(self.timeframes),
            "parameters": dict(self.parameters),
            "metadata": dict(self.metadata),
        }

    def __repr__(self) -> str:
        """Return a useful representation for logs and debugging."""

        return (
            "BaseStrategy("
            f"strategy_id={self.strategy_id!r}, "
            f"strategy_name={self.strategy_name!r}, "
            f"definition={self.definition.name!r}, "
            f"mode={self.mode.value!r}, "
            f"status={self.status.value!r}, "
            f"enabled={self.is_enabled!r}, "
            f"active={self.is_active!r}"
            ")"
        )


__all__ = [
    "BaseStrategy",
    "StrategyConfig",
    "StrategyDefinition",
]
