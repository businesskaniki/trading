"""
Base strategy interface for the AQE strategy engine.

All trading strategies must inherit from BaseStrategy.

The base class defines the contract between the strategy engine and
individual strategies.

Strategies:
    - consume StrategyContext
    - analyze market conditions
    - optionally generate a Signal

Strategies must NOT:
    - connect directly to MT5
    - place orders
    - modify positions
    - perform risk approval
    - access the database directly
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import ClassVar

from .context import StrategyContext
from .enums import StrategyCategory, Timeframe
from .signal import Signal


class BaseStrategy(ABC):
    """
    Abstract base class for all AQE trading strategies.

    Concrete strategies implement `generate_signal()`.
    """

    # ------------------------------------------------------------------
    # Strategy identity
    # ------------------------------------------------------------------

    strategy_id: ClassVar[str]

    name: ClassVar[str]

    category: ClassVar[StrategyCategory]

    description: ClassVar[str] = ""

    # ------------------------------------------------------------------
    # Strategy configuration
    # ------------------------------------------------------------------

    timeframe: ClassVar[Timeframe]

    minimum_candles: ClassVar[int] = 1

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def __init__(self) -> None:
        """
        Initialize the strategy.

        Strategy instances should remain lightweight.

        Configuration should normally be supplied through
        StrategyConfig/strategy parameters rather than hard-coded
        instance state.
        """

        self._initialized = False

    @property
    def initialized(self) -> bool:
        """Return whether the strategy has been initialized."""

        return self._initialized

    def initialize(self) -> None:
        """
        Initialize the strategy.

        Override this method only when a strategy requires explicit
        initialization.

        Avoid performing network or broker operations here.
        """

        self._initialized = True

    def shutdown(self) -> None:
        """
        Shut down the strategy.

        Override when a strategy needs cleanup.

        Strategies should not own external resources such as MT5
        connections.
        """

        self._initialized = False

    # ------------------------------------------------------------------
    # Main strategy interface
    # ------------------------------------------------------------------

    @abstractmethod
    def generate_signal(
        self,
        context: StrategyContext,
    ) -> Signal | None:
        """
        Analyze the current market context and generate a signal.

        Args:
            context:
                Normalized market and runtime information supplied by
                the strategy engine.

        Returns:
            Signal:
                When the strategy identifies a valid trading setup.

            None:
                When no valid setup exists.

        Important:
            Returning a Signal does NOT mean a trade will be executed.
            The signal must pass through the risk engine first.
        """

        raise NotImplementedError

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def validate_context(
        self,
        context: StrategyContext,
    ) -> None:
        """
        Validate that the supplied context is suitable for this strategy.

        Raises:
            ValueError:
                If the context does not match the strategy requirements.
        """

        if context.strategy.strategy_id != self.strategy_id:
            raise ValueError(
                f"Context strategy '{context.strategy.strategy_id}' "
                f"does not match strategy '{self.strategy_id}'"
            )

        if context.timeframe != self.timeframe:
            raise ValueError(
                f"Strategy '{self.strategy_id}' requires timeframe "
                f"{self.timeframe.value}, "
                f"got {context.timeframe.value}"
            )

        context.require_candles(self.minimum_candles)

    # ------------------------------------------------------------------
    # Public execution wrapper
    # ------------------------------------------------------------------

    def evaluate(
        self,
        context: StrategyContext,
    ) -> Signal | None:
        """
        Evaluate the strategy against a runtime context.

        This method provides a consistent entry point for the strategy
        engine.

        It validates the context before calling the strategy's actual
        signal-generation logic.
        """

        self.validate_context(context)

        if not context.strategy.enabled:
            return None

        if not self.initialized:
            self.initialize()

        signal = self.generate_signal(context)

        return self.validate_signal(signal)

    # ------------------------------------------------------------------
    # Signal validation
    # ------------------------------------------------------------------

    def validate_signal(
        self,
        signal: Signal | None,
    ) -> Signal | None:
        """
        Validate a signal returned by the strategy.

        This performs structural validation only.

        Risk approval belongs to the Risk Engine.
        """

        if signal is None:
            return None

        if signal.strategy_id != self.strategy_id:
            raise ValueError(
                f"Signal strategy '{signal.strategy_id}' does not match "
                f"strategy '{self.strategy_id}'"
            )

        if signal.symbol == "":
            raise ValueError("Signal symbol cannot be empty")

        if signal.timeframe != self.timeframe:
            raise ValueError(
                f"Signal timeframe {signal.timeframe.value} does not "
                f"match strategy timeframe {self.timeframe.value}"
            )

        return signal

    # ------------------------------------------------------------------
    # Strategy metadata
    # ------------------------------------------------------------------

    @classmethod
    def metadata(cls) -> dict[str, object]:
        """
        Return static metadata describing the strategy.

        Useful for:
            - strategy registry
            - API responses
            - dashboard
            - logging
            - strategy discovery
        """

        return {
            "strategy_id": cls.strategy_id,
            "name": cls.name,
            "category": cls.category.value,
            "description": cls.description,
            "timeframe": cls.timeframe.value,
            "minimum_candles": cls.minimum_candles,
        }

    def __repr__(self) -> str:
        """Return a useful strategy representation."""

        return (
            f"{self.__class__.__name__}("
            f"strategy_id='{self.strategy_id}', "
            f"timeframe='{self.timeframe.value}', "
            f"category='{self.category.value}'"
            f")"
        )
