from __future__ import annotations

import logging
from dataclasses import dataclass
from uuid import UUID

from app.broker.broker_manager import BrokerManager
from app.broker.factory import get_broker_adapter
from app.database.session import SessionLocal
from app.events.bus import event_bus
from .live_context_factory import LiveContextFactory
from .engine import ExecutionEngine
from .live_pipeline import LivePipeline
from .live_context_provider import LiveRiskContextProvider
from .runtime_account import (
    RuntimeAccount,
    RuntimeAccountResolver,
)
from .signal_pipeline import SignalRiskExecutionPipeline
from app.market_data.consumer import MarketDataConsumer
from app.market_data.service import MarketDataService
from app.market_data.subscription_manager import (
    MarketDataSubscriptionManager,
)
from risk.engine import RiskEngine
from app.services.mt5_bridge_service import MT5BridgeService
from app.services.trading_account_service import TradingAccountService
from app.repositories.trading_account_repository import (
    TradingAccountRepository,
)
from app.market_data.historical_synchronizer import (
    HistoricalDataSynchronizer,
)
from app.market_data.live import LiveTickHub
from strategies.runtime.manager import StrategyManager

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class ExecutionRuntime:
    """
    Complete runtime composition for one AQE trading account.

    This object contains the account-specific infrastructure required
    to run the live/paper trading pipeline.

    Construction does not connect to MT5 and does not start any
    background services.

    Lifecycle is controlled by AQEEngine.
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

    The factory is deliberately responsible only for composition.

    It does NOT:

    - connect to MT5
    - start Redis consumers
    - start strategies
    - evaluate risk
    - execute orders
    - publish runtime events

    Those operations belong to the runtime lifecycle managed by
    AQEEngine.

    Account credentials are resolved only during ``create()`` and
    are passed to the broker connection layer by the caller.
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

        Parameters
        ----------
        account_id:
            Trading account that will own this runtime.

        Returns
        -------
        ExecutionRuntime
            Fully composed runtime which has not yet been started.
        """

        logger.info(
            "Building AQE execution runtime for account %s.",
            account_id,
        )

        # --------------------------------------------------------------
        # 1. Resolve the runtime account.
        #
        # This retrieves the TradingAccount and decrypts its broker
        # password. The credentials are kept inside RuntimeAccount
        # only for the runtime composition/connection operation.
        # --------------------------------------------------------------

        runtime_account = await self._resolve_account(
            account_id=account_id,
        )

        # --------------------------------------------------------------
        # 2. Create the AQE-side bridge client.
        #
        # MT5BridgeService itself does NOT contain credentials.
        # Credentials are supplied later through broker_manager.connect().
        # --------------------------------------------------------------

        bridge_service = MT5BridgeService(
            bridge_url=runtime_account.bridge_url,
        )

        # --------------------------------------------------------------
        # 3. Create the account-specific broker adapter.
        #
        # MT5Adapter needs the account identity because the bridge
        # connection belongs to the selected trading account.
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
        #
        # IMPORTANT:
        # Do not use the global market_data_service singleton.
        #
        # The runtime gets its own bridge client so the composition
        # remains explicit and testable.
        # --------------------------------------------------------------

        market_data_service = MarketDataService(
            bridge=bridge_service,
        )

        # --------------------------------------------------------------
        # 5. Redis market-data consumer.
        #
        # This consumes bridge-produced Redis market-data events and
        # publishes normalized MarketTickEvents to the AQE EventBus.
        # --------------------------------------------------------------

        market_data_consumer = MarketDataConsumer()

        # --------------------------------------------------------------
        # 6. Subscription manager.
        #
        # Database remains the source of truth for enabled symbols.
        #
        # We inject the same bridge client instead of using its global
        # singleton.
        # --------------------------------------------------------------

        market_data_subscription_manager = MarketDataSubscriptionManager(
            session_factory=self.session_factory,
            bridge_service=bridge_service,
        )

        # --------------------------------------------------------------
        # 7. Historical synchronization.
        #
        # HistoricalDataSynchronizer currently owns its bridge client
        # internally. Its synchronization is intentionally independent
        # from the live market-data consumer.
        #
        # It runs against the already-connected bridge once AQEEngine
        # starts the runtime.
        # --------------------------------------------------------------

        historical_data_synchronizer = HistoricalDataSynchronizer()

        # --------------------------------------------------------------
        # 8. Live tick hub.
        #
        # The hub listens to normalized MarketTickEvents and fans
        # ticks out to WebSocket consumers.
        # --------------------------------------------------------------

        live_tick_hub = LiveTickHub()

        # --------------------------------------------------------------
        # 9. Strategy runtime.
        #
        # StrategyManager remains broker/order/risk agnostic.
        # Strategies receive market data through the EventBus and
        # eventually emit StrategySignalEvents.
        # --------------------------------------------------------------

        strategy_manager = StrategyManager()

        # --------------------------------------------------------------
        # 10. Risk engine.
        #
        # RiskEngine has no external side effects and can safely be
        # constructed before the broker connection exists.
        # --------------------------------------------------------------

        risk_engine = RiskEngine()

        # --------------------------------------------------------------
        # 11. Live risk-context provider.
        #
        # LiveContextFactory creates the provider responsible for
        # resolving:
        #
        #   account state
        #   open positions
        #   broker symbol
        #   current market
        #   risk configuration
        #
        # It uses the same account-specific BrokerManager that execution
        # will use.
        # --------------------------------------------------------------

        live_context_factory = LiveContextFactory(
            session_factory=self.session_factory,
            broker_manager=broker_manager,
            account_id_resolver=lambda: runtime_account.account_id,
        )

        risk_context_provider = live_context_factory.create()

        # --------------------------------------------------------------
        # 12. Execution engine.
        #
        # This is the actual component that takes an approved
        # RiskDecision and turns it into a broker execution.
        #
        # RiskEngine itself never places orders.
        # --------------------------------------------------------------

        execution_engine = ExecutionEngine(
            session_factory=self.session_factory,
            broker_manager=broker_manager,
            bus=event_bus,
        )

        # --------------------------------------------------------------
        # 13. Signal -> Risk -> Execution pipeline.
        #
        # StrategySignalEvent
        #        ↓
        # RiskContextProvider
        #        ↓
        # RiskEngine
        #        ↓
        # approved RiskDecision
        #        ↓
        # ExecutionEngine
        #        ↓
        # BrokerManager
        #        ↓
        # MT5Adapter
        # --------------------------------------------------------------

        signal_pipeline = SignalRiskExecutionPipeline(
            bus=event_bus,
            risk_engine=risk_engine,
            context_provider=risk_context_provider,
            execution_engine=execution_engine,
        )
        # --------------------------------------------------------------
        # 14. Live pipeline wrapper.
        # --------------------------------------------------------------

        live_pipeline = LivePipeline(
            broker_manager=broker_manager,
            risk_engine=risk_engine,
            context_provider=risk_context_provider,
            execution_engine=execution_engine,
            signal_pipeline=signal_pipeline,
        )

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
            "AQE execution runtime composed successfully: "
            "account_id=%s broker=%s login=%s server=%s",
            runtime_account.account_id,
            runtime_account.broker,
            runtime_account.login,
            runtime_account.server,
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
        Resolve a trading account and decrypt its runtime credentials.

        A fresh database session is used because this operation occurs
        at runtime composition time and must not retain a request-scoped
        session.
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
