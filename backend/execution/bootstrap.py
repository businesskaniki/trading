from __future__ import annotations

import logging
from dataclasses import dataclass
from uuid import UUID

from app.broker.broker_manager import BrokerManager
from app.broker.factory import get_broker_adapter
from app.database.session import SessionLocal
from app.events.bus import event_bus
from app.market_data.consumer import MarketDataConsumer
from app.market_data.historical_synchronizer import (
    HistoricalDataSynchronizer,
)
from app.market_data.live import LiveTickHub
from app.market_data.service import MarketDataService
from app.market_data.subscription_manager import (
    MarketDataSubscriptionManager,
)
from app.repositories.trading_account_repository import (
    TradingAccountRepository,
)
from app.services.mt5_bridge_service import MT5BridgeService
from app.services.trading_account_service import (
    TradingAccountService,
)
from risk.engine import RiskEngine
from strategies.core.signal import TradingSignal
from strategies.runtime.manager import StrategyManager

from .engine import ExecutionEngine
from .live_context_factory import LiveContextFactory
from .live_context_provider import LiveRiskContextProvider
from .live_pipeline import LivePipeline
from .runtime_account import (
    RuntimeAccount,
    RuntimeAccountResolver,
)
from .signal_pipeline import SignalRiskExecutionPipeline

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class ExecutionRuntime:
    """
    Complete runtime composition for one AQE trading account.

    This object contains the account-specific infrastructure required
    to run the live/paper trading pipeline.

    Construction performs dependency composition only.

    It does NOT:

        - connect to MT5;
        - start Redis consumers;
        - start strategies;
        - start the signal pipeline;
        - evaluate risk;
        - execute orders;
        - start market-data polling.

    Runtime lifecycle is controlled by AQEEngine.
    """

    account: RuntimeAccount

    broker_manager: BrokerManager

    bridge_service: MT5BridgeService

    market_data_service: MarketDataService
    market_data_consumer: MarketDataConsumer
    market_data_subscription_manager: MarketDataSubscriptionManager
    historical_data_synchronizer: HistoricalDataSynchronizer
    live_tick_hub: LiveTickHub

    strategy_manager: StrategyManager

    risk_engine: RiskEngine
    risk_context_provider: LiveRiskContextProvider

    execution_engine: ExecutionEngine
    signal_pipeline: SignalRiskExecutionPipeline
    live_pipeline: LivePipeline


class ExecutionRuntimeFactory:
    """
    Compose all AQE runtime services for a selected trading account.

    The factory is responsible only for dependency composition.

    It does NOT:

        - connect to MT5;
        - start Redis consumers;
        - start strategies;
        - evaluate risk;
        - execute orders;
        - publish runtime events.

    Those operations belong to the runtime lifecycle managed by
    AQEEngine.

    Account credentials are resolved during ``create()`` and retained
    only within the resulting RuntimeAccount used by the runtime
    connection layer.
    """

    def __init__(
        self,
        *,
        session_factory=SessionLocal,
    ) -> None:
        self.session_factory = session_factory

    # ==================================================================
    # PUBLIC API
    # ==================================================================

    async def create(
        self,
        account_id: UUID,
    ) -> ExecutionRuntime:
        """
        Build a complete account-specific AQE runtime.

        The returned runtime is fully composed but not started.
        """

        logger.info(
            "Building AQE execution runtime for account %s.",
            account_id,
        )

        # --------------------------------------------------------------
        # 1. Resolve the runtime account.
        # --------------------------------------------------------------

        runtime_account = await self._resolve_account(
            account_id=account_id,
        )

        # --------------------------------------------------------------
        # 2. Create the AQE-side MT5 bridge client.
        #
        # Credentials are intentionally NOT stored in the bridge
        # service. They are supplied to the broker connection layer
        # when the runtime is started.
        # --------------------------------------------------------------

        bridge_service = MT5BridgeService(
            bridge_url=runtime_account.bridge_url,
        )

        # --------------------------------------------------------------
        # 3. Create the account-specific broker adapter.
        # --------------------------------------------------------------

        broker_adapter = get_broker_adapter(
            runtime_account.broker,
            bridge_url=runtime_account.bridge_url,
            account_id=runtime_account.account_id,
        )

        broker_manager = BrokerManager(
            adapter=broker_adapter,
        )

        # --------------------------------------------------------------
        # 4. Market-data service.
        # --------------------------------------------------------------

        market_data_service = MarketDataService(
            bridge=bridge_service,
        )

        # --------------------------------------------------------------
        # 5. Redis market-data consumer.
        #
        # Construction does not start the consumer.
        # --------------------------------------------------------------

        market_data_consumer = MarketDataConsumer()

        # --------------------------------------------------------------
        # 6. Account-specific market-data subscription manager.
        # --------------------------------------------------------------

        market_data_subscription_manager = MarketDataSubscriptionManager(
            session_factory=self.session_factory,
            bridge_service=bridge_service,
        )

        # --------------------------------------------------------------
        # 7. Historical data synchronization.
        #
        # Construction does not start synchronization.
        # --------------------------------------------------------------

        historical_data_synchronizer = HistoricalDataSynchronizer()

        # --------------------------------------------------------------
        # 8. Live tick hub.
        # --------------------------------------------------------------

        live_tick_hub = LiveTickHub()

        # --------------------------------------------------------------
        # 9. Strategy runtime.
        #
        # Strategies remain independent from broker, risk, and
        # execution implementation details.
        # --------------------------------------------------------------

        strategy_manager = StrategyManager()

        # --------------------------------------------------------------
        # 10. Risk engine.
        # --------------------------------------------------------------

        risk_engine = RiskEngine()

        # --------------------------------------------------------------
        # 11. Live risk-context provider.
        #
        # StrategySignalEvent intentionally does not contain account_id.
        #
        # StrategyManager.account_router is therefore the source of
        # truth for strategy → account ownership.
        #
        # Because this ExecutionRuntime is account-scoped, the resolved
        # account must match this runtime's account.
        # --------------------------------------------------------------

        async def resolve_account_id(
            signal: TradingSignal,
        ) -> UUID:
            """
            Resolve the trading account assigned to a strategy signal.
            """

            resolved_account_id = strategy_manager.account_router.resolve(
                signal,
            )

            if resolved_account_id != runtime_account.account_id:
                raise RuntimeError(
                    "Strategy signal is routed to a different "
                    "trading account. "
                    f"strategy_id={signal.strategy_id!r}, "
                    f"resolved_account_id={resolved_account_id}, "
                    f"runtime_account_id={runtime_account.account_id}",
                )

            return resolved_account_id

        live_context_factory = LiveContextFactory(
            session_factory=self.session_factory,
            broker_manager=broker_manager,
            account_id_resolver=resolve_account_id,
        )

        risk_context_provider = live_context_factory.create()

        # --------------------------------------------------------------
        # 12. Execution engine.
        #
        # Approved RiskDecision objects enter here.
        #
        #     RiskDecision
        #          ↓
        #     ExecutionOrder
        #          ↓
        #     account-symbol resolution
        #          ↓
        #     persistent Order
        #          ↓
        #     BrokerManager
        # --------------------------------------------------------------

        execution_engine = ExecutionEngine(
            session_factory=self.session_factory,
            broker_manager=broker_manager,
            bus=event_bus,
        )

        # --------------------------------------------------------------
        # 13. Strategy signal → Risk → Execution pipeline.
        #
        # StrategySignalEvent
        #        ↓
        # RiskContextProvider
        #        ↓
        # RiskEngine
        #        ↓
        # RiskDecision
        #        ↓
        # ExecutionEngine
        #        ↓
        # BrokerManager
        # --------------------------------------------------------------

        signal_pipeline = SignalRiskExecutionPipeline(
            bus=event_bus,
            risk_engine=risk_engine,
            context_provider=risk_context_provider,
            execution_engine=execution_engine,
        )

        # --------------------------------------------------------------
        # 14. Live pipeline lifecycle wrapper.
        #
        # LivePipeline deliberately contains only the signal pipeline.
        # There must be exactly one StrategySignalEvent →
        # RiskEngine → ExecutionEngine path.
        # --------------------------------------------------------------

        live_pipeline = LivePipeline(
            signal_pipeline=signal_pipeline,
        )

        # --------------------------------------------------------------
        # 15. Compose the final runtime.
        # --------------------------------------------------------------

        runtime = ExecutionRuntime(
            account=runtime_account,
            broker_manager=broker_manager,
            bridge_service=bridge_service,
            market_data_service=market_data_service,
            market_data_consumer=market_data_consumer,
            market_data_subscription_manager=(market_data_subscription_manager),
            historical_data_synchronizer=(historical_data_synchronizer),
            live_tick_hub=live_tick_hub,
            strategy_manager=strategy_manager,
            risk_engine=risk_engine,
            risk_context_provider=risk_context_provider,
            execution_engine=execution_engine,
            signal_pipeline=signal_pipeline,
            live_pipeline=live_pipeline,
        )

        logger.info(
            "AQE execution runtime composed successfully: " "account_id=%s broker=%s",
            runtime_account.account_id,
            runtime_account.broker,
        )

        return runtime

    # ==================================================================
    # ACCOUNT RESOLUTION
    # ==================================================================

    async def _resolve_account(
        self,
        account_id: UUID,
    ) -> RuntimeAccount:
        """
        Resolve a trading account and its runtime credentials.

        A fresh database session is used because runtime composition
        must not retain a request-scoped database session.
        """

        async with self.session_factory() as session:
            repository = TradingAccountRepository(
                session,
            )

            trading_account_service = TradingAccountService(
                repository,
            )

            resolver = RuntimeAccountResolver(
                trading_account_service,
            )

            return await resolver.resolve(
                account_id,
            )


async def build_execution_runtime(
    account_id: UUID,
    *,
    session_factory=SessionLocal,
) -> ExecutionRuntime:
    """
    Convenience function for composing an AQE execution runtime.

    No runtime component is started by this function.
    """

    factory = ExecutionRuntimeFactory(
        session_factory=session_factory,
    )

    return await factory.create(
        account_id,
    )
