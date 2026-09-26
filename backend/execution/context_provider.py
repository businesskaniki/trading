"""
Risk context provider contracts for the AQE execution pipeline.

The Risk Engine must receive a complete RiskContext, but it must not know
where that context came from.

Different execution environments can therefore provide their own context:

    LIVE/PAPER
        -> LiveRiskContextProvider

    BACKTEST
        -> BacktestRiskContextProvider

    REPLAY
        -> ReplayRiskContextProvider
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from risk.models import RiskContext
from strategies.core.signal import TradingSignal


class RiskContextProvider(ABC):
    """
    Abstract provider for Risk Engine runtime context.

    Implementations are responsible for assembling every piece of state
    required by RiskEngine.evaluate().
    """

    @abstractmethod
    async def build(
        self,
        signal: TradingSignal,
    ) -> RiskContext:
        """
        Build a complete RiskContext for a trading signal.

        Args:
            signal:
                Strategy-generated trading intent.

        Returns:
            A fully populated RiskContext.

        Raises:
            Exception:
                Implementations should raise a meaningful exception when
                the required account, market, position, or symbol state
                cannot be obtained.
        """

        raise NotImplementedError
