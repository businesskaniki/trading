"""Strategy-related events for the AQE event system."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from strategies.core.signal import TradingSignal

from .base import Event


@dataclass(frozen=True, slots=True)
class StrategySignalEvent(Event):
    """
    Event emitted when a strategy generates a trading signal.

    The signal represents trading intent only. Downstream consumers,
    primarily the Risk Engine, are responsible for validating risk,
    determining position sizing, and deciding whether execution is
    permitted.

    Strategy implementations must not place broker orders directly.
    """

    signal: TradingSignal

    @property
    def strategy_id(self) -> str:
        """Return the strategy instance that generated the signal."""
        return self.signal.strategy_id

    @property
    def strategy_name(self) -> str:
        """Return the registered strategy name."""
        return self.signal.strategy_name

    @property
    def symbol(self) -> str:
        """Return the signal symbol."""
        return self.signal.symbol

    @property
    def timeframe(self) -> str:
        """Return the signal timeframe."""
        return self.signal.timeframe.value

    @property
    def mode(self) -> str:
        """Return the strategy execution mode."""
        return self.signal.metadata.get(
            "strategy_mode",
            "unknown",
        )

    @property
    def direction(self) -> str:
        """Return the signal direction."""
        return self.signal.direction.value

    @property
    def signal_type(self) -> str:
        """Return the requested signal action."""
        return self.signal.signal_type.value

    @property
    def order_type(self) -> str:
        """Return the requested order type."""
        return self.signal.order_type.value

    def as_dict(self) -> dict[str, Any]:
        """
        Return a serializable representation of the strategy signal.

        This is intended for logging, monitoring, diagnostics, and
        event forwarding. The TradingSignal remains the canonical
        signal contract.
        """
        return {
            "event_id": str(self.event_id),
            "occurred_at": self.occurred_at.isoformat(),
            "signal": self.signal.model_dump(mode="json"),
        }
