from __future__ import annotations

import logging

from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

from app.broker.broker_manager import BrokerManager
from app.broker.factory import get_broker_adapter
from app.database.session import SessionLocal
from app.events.bus import event_bus
from app.market_data.candle_builder import LiveCandleBuilder
from app.market_data.consumer import MarketDataConsumer
from app.market_data.historical_synchronizer import (
    HistoricalDataSynchronizer,
)
from app.market_data.live import LiveTickHub
from app.market_data.service import MarketDataService
from app.market_data.strategy_view import StrategyMarketDataView
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
from .order_reconciliation_service import (
    OrderReconciliationService,
)
from .position_reconciliation_service import (
    PositionReconciliationService,
)
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

    Construction performs dependency composition only.

    It does NOT:

        - connect to MT5;
        - start Redis consumers;
        - start live candle processing;
        - start strategies;
        - start the signal pipeline;
        - evaluate risk;
        - execute orders;
        - start market-data polling;
        - start order reconciliation;
        - start position reconciliation.

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
    live_candle_builder: LiveCandleBuilder
    strategy_market_data: StrategyMarketDataView

    strategy_manager: StrategyManager

    risk_engine: RiskEngine
    risk_context_provider: LiveRiskContextProvider

    execution_engine: ExecutionEngine
    order_reconciliation_service: OrderReconciliationService
    position_reconciliation_service: PositionReconciliationService

    signal_pipeline: SignalRiskExecutionPipeline
    live_pipeline: LivePipeline


class ExecutionRuntimeFactory:
    """
    Compose all AQE runtime services for a selected trading account.

    The factory is responsible for dependency composition only.

    AQEEngine owns runtime startup and shutdown.

    Account credentials are resolved during create() and retained
    only within the resulting RuntimeAccount and broker connection
    layer.
    """

    def __init__(
        self,
        *,
        session_factory=SessionLocal,
        paper_margin_rate: Decimal = Decimal("1"),
    ) -> None:
        self.session_factory = session_factory
        self.paper_margin_rate = Decimal(str(paper_margin_rate))
        if not self.paper_margin_rate.is_finite() or self.paper_margin_rate <= Decimal(
            "0"
        ):
            raise ValueError("paper_margin_rate must be finite and greater than zero.")

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
        # Broker credentials are resolved through the account runtime,
        # not hard-coded into the bridge service.
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

        # --------------------------------------------------------------
        # 3a. Resolve broker margin provider.
        #
        # MT5 accounts must be able to calculate margin before an
        # order is approved. Refuse to compose a live MT5 runtime
        # whose adapter cannot expose calculate_margin(), rather
        # than silently approving trades without a margin check.
        #
        # Non-MT5 (PAPER/backtest) brokers fall back to the
        # conservative configured paper_margin_rate supplied to the
        # LiveContextFactory below.
        # --------------------------------------------------------------

        margin_provider = getattr(broker_adapter, "calculate_margin", None)
        broker_name = (
            str(getattr(runtime_account.broker, "value", runtime_account.broker))
            .strip()
            .lower()
        )

        if broker_name == "mt5" and not callable(margin_provider):
            raise RuntimeError(
                "MT5 broker adapter does not expose calculate_margin(); "
                "refusing to compose a live runtime without broker margin checks."
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
        # The active account ID allows the consumer to translate
        # broker-facing symbols into canonical AQE symbols using
        # enabled AccountSymbol mappings.
        #
        # Construction does not start Redis consumption.
        # --------------------------------------------------------------

        market_data_consumer = MarketDataConsumer(
            account_id=runtime_account.account_id,
            session_factory=self.session_factory,
        )

        # --------------------------------------------------------------
        # 6. Account-symbol subscription manager.
        #
        # PostgreSQL AccountSymbol.enabled remains the source of truth
        # for bridge subscription reconciliation.
        # --------------------------------------------------------------

        market_data_subscription_manager = MarketDataSubscriptionManager(
            session_factory=self.session_factory,
            bridge_service=bridge_service,
        )

        # --------------------------------------------------------------
        # 7. Historical-data synchronization.
        #
        # Construction does not start synchronization.
        # --------------------------------------------------------------

        historical_data_synchronizer = HistoricalDataSynchronizer(
            account_id=runtime_account.account_id,
            bridge_service=bridge_service,
        )

        # --------------------------------------------------------------
        # 8. Live tick hub.
        #
        # The hub distributes incoming tick events to its local
        # subscribers. It does not generate candle events.
        # --------------------------------------------------------------

        live_tick_hub = LiveTickHub()

        # --------------------------------------------------------------
        # 9. Live candle builder.
        #
        # Converts MarketTickEvent instances into completed
        # MarketCandleEvent instances.
        #
        # Construction does not start candle processing.
        # --------------------------------------------------------------

        live_candle_builder = LiveCandleBuilder(
            bus=event_bus,
        )

        # --------------------------------------------------------------
        # 10. Strategy market-data view.
        #
        # Gives strategies read-only access to:
        #
        #   - the latest cached live ticks;
        #   - persisted historical candles;
        #   - candles queried by symbol and timeframe.
        #
        # Its event subscription is established by start(), which
        # AQEEngine must call before starting the market-data consumer.
        # --------------------------------------------------------------

        strategy_market_data = StrategyMarketDataView(
            session_factory=self.session_factory,
            bus=event_bus,
        )

        # --------------------------------------------------------------
        # 11. Strategy runtime.
        #
        # Strategies analyse market data and emit TradingSignal objects.
        # They do not access broker execution directly.
        #
        # Injecting the shared market-data view enables strategies such
        # as EMATrendStrategy to warm up from historical candles and
        # query live market state through StrategyContext.
        # --------------------------------------------------------------

        strategy_manager = StrategyManager(
            market_data=strategy_market_data,
        )

        # --------------------------------------------------------------
        # 12. Risk engine.
        # --------------------------------------------------------------

        risk_engine = RiskEngine()

        # --------------------------------------------------------------
        # 13. Position reconciliation service.
        #
        # Construct this before LiveContextFactory.
        #
        # This is the single account-scoped position reconciliation
        # service instance shared by:
        #
        #   - AQEEngine, which owns its lifecycle;
        #   - LiveContextFactory, which consumes its validated,
        #     persisted position state;
        #   - PositionWebSocketManager, which reads its latest
        #     synchronization status.
        #
        # Construction does not start reconciliation.
        # --------------------------------------------------------------

        position_reconciliation_service = PositionReconciliationService(
            broker=broker_manager,
            account_id=runtime_account.account_id,
            user_id=runtime_account.user_id,
            session_factory=self.session_factory,
        )

        # --------------------------------------------------------------
        # 14. Live risk-context provider.
        #
        # StrategySignalEvent intentionally remains account-agnostic.
        # StrategyManager.account_router owns strategy-to-account
        # resolution.
        #
        # This runtime is account-scoped, so a signal assigned to a
        # different account must be rejected before risk evaluation.
        #
        # PositionReconciliationService is injected so the risk-context
        # factory uses validated, persisted AQE positions rather than
        # independently retrieving positions from MT5.
        #
        # margin_rate is supplied only when the broker adapter does
        # not expose calculate_margin(). For MT5, margin_rate=None
        # signals that margin must be resolved at trade time via the
        # broker, not from a fixed formula rate.
        # --------------------------------------------------------------

        async def resolve_account_id(
            signal: TradingSignal,
        ) -> UUID:
            """Resolve and validate the account assigned to a signal."""

            resolved_account_id = strategy_manager.account_router.resolve(
                signal,
            )

            if resolved_account_id != runtime_account.account_id:
                raise RuntimeError(
                    "Strategy signal is routed to a different "
                    "trading account. "
                    f"strategy_id={signal.strategy_id!r}, "
                    f"resolved_account_id={resolved_account_id}, "
                    f"runtime_account_id={runtime_account.account_id}"
                )

            return resolved_account_id

        live_context_factory = LiveContextFactory(
            session_factory=self.session_factory,
            broker_manager=broker_manager,
            account_id_resolver=resolve_account_id,
            position_reconciliation_service=position_reconciliation_service,
            margin_rate=(None if callable(margin_provider) else self.paper_margin_rate),
        )

        risk_context_provider = live_context_factory.create()

        # --------------------------------------------------------------
        # 15. Execution engine.
        #
        # Approved RiskDecision objects enter the execution engine:
        #
        #     RiskDecision
        #          |
        #          v
        #     ExecutionOrder
        #          |
        #          v
        #     Account-symbol resolution
        #          |
        #          v
        #     Persistent Order
        #          |
        #          v
        #     BrokerManager
        # --------------------------------------------------------------

        execution_engine = ExecutionEngine(
            session_factory=self.session_factory,
            broker_manager=broker_manager,
            bus=event_bus,
        )

        # --------------------------------------------------------------
        # 16. Order reconciliation service.
        #
        # Recovers orders whose final broker execution outcome may
        # be unknown. AQEEngine owns its lifecycle.
        # --------------------------------------------------------------

        order_reconciliation_service = OrderReconciliationService(
            broker=broker_manager,
            session_factory=self.session_factory,
        )

        # --------------------------------------------------------------
        # 17. Strategy signal -> Risk -> Execution pipeline.
        #
        # StrategySignalEvent
        #        |
        #        v
        # RiskContextProvider
        #        |
        #        v
        # RiskEngine
        #        |
        #        v
        # RiskDecision
        #        |
        #        v
        # ExecutionEngine
        #        |
        #        v
        # BrokerManager
        #
        # This is the single live/paper signal execution path.
        #
        # margin_provider is forwarded to the pipeline only when the
        # broker adapter exposes calculate_margin(). For MT5, the
        # pipeline uses the broker margin endpoint before approving
        # a trade. For PAPER/backtest, margin_provider=None keeps
        # the fixed paper_margin_rate simulation path.
        # --------------------------------------------------------------

        signal_pipeline = SignalRiskExecutionPipeline(
            bus=event_bus,
            risk_engine=risk_engine,
            context_provider=risk_context_provider,
            execution_engine=execution_engine,
            margin_provider=(margin_provider if callable(margin_provider) else None),
        )

        # --------------------------------------------------------------
        # 18. Live pipeline lifecycle wrapper.
        #
        # LivePipeline owns the signal pipeline lifecycle.
        # --------------------------------------------------------------

        live_pipeline = LivePipeline(
            signal_pipeline=signal_pipeline,
        )

        # --------------------------------------------------------------
        # 19. Compose the complete runtime.
        #
        # Components are constructed but remain stopped until
        # AQEEngine explicitly starts them.
        # --------------------------------------------------------------

        runtime = ExecutionRuntime(
            account=runtime_account,
            broker_manager=broker_manager,
            bridge_service=bridge_service,
            market_data_service=market_data_service,
            market_data_consumer=market_data_consumer,
            market_data_subscription_manager=(market_data_subscription_manager),
            historical_data_synchronizer=historical_data_synchronizer,
            live_tick_hub=live_tick_hub,
            live_candle_builder=live_candle_builder,
            strategy_market_data=strategy_market_data,
            strategy_manager=strategy_manager,
            risk_engine=risk_engine,
            risk_context_provider=risk_context_provider,
            execution_engine=execution_engine,
            order_reconciliation_service=order_reconciliation_service,
            position_reconciliation_service=(position_reconciliation_service),
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
            repository = TradingAccountRepository(session)

            trading_account_service = TradingAccountService(
                repository,
            )

            resolver = RuntimeAccountResolver(
                trading_account_service,
            )

            return await resolver.resolve(account_id)


async def build_execution_runtime(
    account_id: UUID,
    *,
    session_factory=SessionLocal,
    paper_margin_rate: Decimal = Decimal("1"),
) -> ExecutionRuntime:
    """
    Compose an AQE execution runtime without starting its components.

    The default paper_margin_rate of 1.0 is a conservative
    100%-notional PAPER assumption, not a claimed MT5 leverage figure.
    Supply a smaller positive rate explicitly when the PAPER simulation
    should model leverage.
    """

    factory = ExecutionRuntimeFactory(
        session_factory=session_factory,
        paper_margin_rate=paper_margin_rate,
    )

    return await factory.create(account_id)
