from __future__ import annotations

from backtesting.composition import (
    BacktestComposition,
    RiskConfigFactory,
    StrategyConfigFactory,
)
from backtesting.engine import BacktestConfig
from backtesting.factory import BacktestFactory
from backtesting.market_data_loader import HistoricalMarketDataLoader
from backtesting.service import BacktestService
from risk.config import RiskConfig
from strategies.core.base import StrategyConfig
from strategies.core.enums import StrategyMode

from app.database.session import SessionLocal


def create_historical_market_data_loader() -> HistoricalMarketDataLoader:
    """
    Create the historical market-data loader used by backtests.

    Backtests read historical candles from AQE's existing market-data
    persistence layer. They do not create a second market-data system.
    """

    return HistoricalMarketDataLoader(
        session_factory=SessionLocal,
    )


def create_strategy_config(config: BacktestConfig) -> StrategyConfig:
    """
    Convert a BacktestConfig into the runtime StrategyConfig expected
    by StrategyManager.

    The actual strategy implementation is resolved by StrategyManager
    using strategy_id / strategy_name. This function only describes
    the runtime configuration of that strategy instance.
    """

    if not config.strategy_id:
        raise ValueError(
            "BacktestConfig.strategy_id is required to run a strategy " "backtest."
        )

    if not config.strategy_name:
        raise ValueError(
            "BacktestConfig.strategy_name is required to run a strategy " "backtest."
        )

    return StrategyConfig(
        strategy_id=config.strategy_id,
        strategy_name=config.strategy_name,
        mode=StrategyMode.BACKTEST,
        enabled=True,
        account_id=config.account_id,
        symbols=list(config.symbols),
        timeframes=list(config.timeframes),
    )


def create_risk_config(
    config: BacktestConfig,
) -> RiskConfig:
    """
    Create the risk configuration for a backtest.

    The initial backtest API uses the same production RiskConfig model
    and its validated defaults. Backtest-specific risk parameters can
    be exposed later without changing the RiskEngine itself.
    """

    return RiskConfig()


def create_backtest_composition() -> BacktestComposition:
    """
    Create the complete backtest dependency composition.

    This composition deliberately remains separate from the live AQE
    engine composition. A backtest must never accidentally reuse the
    live broker/session lifecycle.
    """

    market_data_loader = create_historical_market_data_loader()

    return BacktestComposition(
        market_data_loader=market_data_loader.load,
        strategy_config_factory=create_strategy_config,
        risk_config_factory=create_risk_config,
    )


def create_backtest_factory() -> BacktestFactory:
    """
    Create the factory responsible for constructing independent
    BacktestOrchestrator instances.
    """

    composition = create_backtest_composition()

    return composition.create_factory()


def create_backtest_service() -> BacktestService:
    """
    Create the application-level BacktestService.

    BacktestService owns lifecycle and background task management;
    BacktestComposition owns construction of the actual simulation
    pipeline.
    """

    factory = create_backtest_factory()

    return BacktestService(
        orchestrator_factory=factory.create,
    )


# ----------------------------------------------------------------------
# Application-level service
# ----------------------------------------------------------------------
#
# This service is intentionally created once for the running AQE
# application. Individual BacktestEngine instances remain isolated
# inside their respective ManagedBacktest objects.
#

backtest_service = create_backtest_service()


def get_backtest_service() -> BacktestService:
    """
    Return the application-level BacktestService.
    """

    return backtest_service
