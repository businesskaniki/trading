from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from risk.config import RiskConfig
from risk.engine import RiskEngine
from strategies.core import StrategyConfig
from strategies.core.enums import StrategyMode
from strategies.runtime.manager import StrategyManager

from .engine import BacktestConfig, BacktestEngine
from .factory import BacktestFactory
from .market import BacktestMarketData
from .market_data_view import BacktestMarketDataView
from .orchestration import (
    BacktestOrchestrator,
    BacktestRiskConfiguration,
)

BacktestMarketDataLoader = Callable[
    [BacktestConfig],
    BacktestMarketData | Awaitable[BacktestMarketData],
]

RiskConfigFactory = Callable[
    [BacktestConfig],
    RiskConfig | Awaitable[RiskConfig],
]

StrategyConfigFactory = Callable[
    [BacktestConfig],
    StrategyConfig | Awaitable[StrategyConfig],
]


@dataclass(slots=True)
class BacktestComposition:
    """
    Composition root for a complete backtest.

    This class wires together:

        historical market data
            ↓
        BacktestMarketDataView
            ↓
        StrategyManager
            ↓
        Strategy
            ↓
        RiskEngine
            ↓
        BacktestOrchestrator
            ↓
        BacktestEngine

    The composition layer owns construction only. Runtime execution
    remains inside the orchestrator and backtest engine.
    """

    market_data_loader: BacktestMarketDataLoader
    risk_config_factory: RiskConfigFactory
    strategy_config_factory: StrategyConfigFactory

    async def build(
        self,
        config: BacktestConfig,
    ) -> BacktestOrchestrator:
        """
        Build a fully wired BacktestOrchestrator.
        """
        if not isinstance(config, BacktestConfig):
            raise TypeError("config must be an instance of BacktestConfig.")

        # --------------------------------------------------------------
        # 1. Load historical market data
        # --------------------------------------------------------------
        market_data = await self._resolve(
            self.market_data_loader,
            config,
        )

        if not isinstance(market_data, BacktestMarketData):
            raise TypeError("market_data_loader must return BacktestMarketData.")

        market_data.finalize()

        # --------------------------------------------------------------
        # 2. Build the strategy manager
        # --------------------------------------------------------------
        strategy_manager = StrategyManager()

        strategy_config = await self._resolve(
            self.strategy_config_factory,
            config,
        )

        if not isinstance(strategy_config, StrategyConfig):
            raise TypeError("strategy_config_factory must return StrategyConfig.")

        # The strategy used by the composition must correspond to the
        # strategy requested by the backtest configuration.
        if strategy_config.strategy_id != config.strategy_id:
            raise ValueError(
                "Strategy configuration mismatch: "
                f"expected strategy_id={config.strategy_id!r}, "
                f"got {strategy_config.strategy_id!r}."
            )

        if strategy_config.strategy_name != config.strategy_name:
            raise ValueError(
                "Strategy configuration mismatch: "
                f"expected strategy_name={config.strategy_name!r}, "
                f"got {strategy_config.strategy_name!r}."
            )

        # --------------------------------------------------------------
        # 3. Create the historical market-data view
        # --------------------------------------------------------------
        #
        # The strategy must only see data available at the current
        # simulation timestamp. This prevents look-ahead bias.
        #
        # If an explicit backtest start exists, use it.
        # Otherwise begin at the first available candle.
        #
        initial_time = config.start

        if initial_time is None:
            initial_time = market_data.start_time

        market_data_view = BacktestMarketDataView(
            market_data,
            current_time=initial_time,
        )

        # --------------------------------------------------------------
        # 4. Create the strategy instance
        # --------------------------------------------------------------
        await strategy_manager.create(
            strategy_config,
            market_data=market_data_view,
            auto_start=False,
        )

        # --------------------------------------------------------------
        # 5. Create the Risk Engine
        # --------------------------------------------------------------
        risk_engine = RiskEngine()

        risk_config = await self._resolve(
            self.risk_config_factory,
            config,
        )

        if not isinstance(risk_config, RiskConfig):
            raise TypeError("risk_config_factory must return RiskConfig.")

        risk_configuration = BacktestRiskConfiguration(
            config=risk_config,
        )

        # --------------------------------------------------------------
        # 6. Create the Backtest Engine
        # --------------------------------------------------------------
        engine = BacktestEngine(
            market_data=market_data,
            config=config,
        )

        # --------------------------------------------------------------
        # 7. Create the orchestrator
        # --------------------------------------------------------------
        orchestrator = BacktestOrchestrator(
            engine=engine,
            strategy_manager=strategy_manager,
            risk_engine=risk_engine,
            risk_configuration=risk_configuration,
        )

        # The orchestrator advances the market-data view before each
        # strategy dispatch.
        orchestrator.set_market_data_view(
            market_data_view,
        )

        return orchestrator

    @staticmethod
    async def _resolve(
        factory: Callable[[BacktestConfig], object],
        config: BacktestConfig,
    ) -> object:
        """
        Resolve either a synchronous or asynchronous factory.
        """
        value = factory(config)

        if inspect.isawaitable(value):
            return await value

        return value

    def create_factory(self) -> BacktestFactory:
        """
        Create the BacktestFactory expected by BacktestService.

        BacktestFactory expects the callable under the
        `orchestrator_builder` argument.
        """

        async def build(
            config: BacktestConfig,
        ) -> BacktestOrchestrator:
            return await self.build(config)

        return BacktestFactory(
            orchestrator_builder=build,
        )
