from fastapi import Depends
from fastapi import HTTPException
from fastapi import status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_db

from app.core.config import settings
from app.core.security import (
    oauth2_scheme,
    verify_token,
)

# ==========================================================
# REPOSITORIES
# ==========================================================

from app.repositories.account_symbol_repository import (
    AccountSymbolRepository,
)
from app.repositories.analytics_repository import (
    AnalyticsRepository,
)
from app.repositories.email_verification_repository import (
    EmailVerificationRepository,
)
from app.repositories.order_repository import (
    OrderRepository,
)
from app.repositories.password_reset_repository import (
    PasswordResetRepository,
)
from app.repositories.performance_repository import (
    PerformanceRepository,
)
from app.repositories.position_repository import (
    PositionRepository,
)
from app.repositories.snapshot_repository import (
    RiskSnapshotRepository,
)
from app.repositories.strategy_run_repository import (
    StrategyRunRepository,
)
from app.repositories.symbol_repository import (
    SymbolRepository,
)
from app.repositories.trade_repository import (
    TradeRepository,
)
from app.repositories.trading_account_repository import (
    TradingAccountRepository,
)
from app.repositories.user_repository import (
    UserRepository,
)

# ==========================================================
# SERVICES
# ==========================================================

from app.services.account_symbol_service import (
    AccountSymbolService,
)
from app.services.analytics_service import (
    AnalyticsService,
)
from app.services.bot_service import (
    BotService,
)
from app.services.email_service import (
    EmailService,
)
from app.services.execution_service import (
    ExecutionService,
)
from app.services.mt5_bridge_service import (
    MT5BridgeService,
)
from app.services.order_execution_service import (
    OrderExecutionService,
)
from app.services.order_service import (
    OrderService,
)
from app.services.performance_service import (
    PerformanceService,
)
from app.services.position_service import (
    PositionService,
)
from app.services.position_sync_service import (
    PositionSyncService,
)
from app.services.risk_snapshot_service import (
    RiskSnapshotService,
)
from app.services.strategy_run_service import (
    StrategyRunService,
)
from app.services.symbol_service import (
    SymbolService,
)
from app.services.symbol_sync_service import (
    SymbolSyncService,
)
from app.services.trade_service import (
    TradeService,
)
from app.services.trading_account_service import (
    TradingAccountService,
)
from app.services.user_service import (
    UserService,
)

# ==========================================================
# BROKER
# ==========================================================

from app.broker.broker_manager import (
    BrokerManager,
)
from app.broker.factory import (
    get_broker_adapter,
)


# ==========================================================
# DATABASE
# ==========================================================


def get_db_session(
    db: AsyncSession = Depends(get_db),
) -> AsyncSession:
    """
    Return the current database session.
    """
    return db


# ==========================================================
# AUTHENTICATION
# ==========================================================


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
):
    """
    Validate the access token and return the current user.
    """

    try:
        payload = verify_token(
            token,
            expected_type="access",
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
            headers={
                "WWW-Authenticate": "Bearer",
            },
        ) from exc

    user = await UserRepository(db).get_by_id(
        payload["sub"],
    )

    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid user",
            headers={
                "WWW-Authenticate": "Bearer",
            },
        )

    return user


# ==========================================================
# USER SERVICE
# ==========================================================


def get_user_service(
    db: AsyncSession = Depends(get_db),
) -> UserService:

    return UserService(
        repository=UserRepository(db),
        email_verification_repository=EmailVerificationRepository(
            db,
        ),
        password_reset_repository=PasswordResetRepository(
            db,
        ),
        email_service=EmailService(),
    )


# ==========================================================
# SYMBOL REPOSITORY
# ==========================================================


def get_symbol_repository(
    db: AsyncSession = Depends(get_db),
) -> SymbolRepository:

    return SymbolRepository(db)


# ==========================================================
# SYMBOL SERVICE
# ==========================================================


def get_symbol_service(
    symbol_repository: SymbolRepository = Depends(
        get_symbol_repository,
    ),
) -> SymbolService:

    return SymbolService(
        symbol_repository,
    )


# ==========================================================
# TRADING ACCOUNT REPOSITORY
# ==========================================================


def get_trading_account_repository(
    db: AsyncSession = Depends(get_db),
) -> TradingAccountRepository:

    return TradingAccountRepository(db)


# ==========================================================
# TRADING ACCOUNT SERVICE
# ==========================================================


def get_trading_account_service(
    repository: TradingAccountRepository = Depends(
        get_trading_account_repository,
    ),
) -> TradingAccountService:

    return TradingAccountService(
        repository,
    )


# ==========================================================
# ACCOUNT SYMBOL REPOSITORY
# ==========================================================


def get_account_symbol_repository(
    db: AsyncSession = Depends(get_db),
) -> AccountSymbolRepository:

    return AccountSymbolRepository(db)


# ==========================================================
# ACCOUNT SYMBOL SERVICE
# ==========================================================


def get_account_symbol_service(
    account_symbol_repository: AccountSymbolRepository = Depends(
        get_account_symbol_repository,
    ),
    trading_account_repository: TradingAccountRepository = Depends(
        get_trading_account_repository,
    ),
) -> AccountSymbolService:

    return AccountSymbolService(
        account_symbol_repository=account_symbol_repository,
        trading_account_repository=trading_account_repository,
    )


# ==========================================================
# ORDER REPOSITORY
# ==========================================================


def get_order_repository(
    db: AsyncSession = Depends(get_db),
) -> OrderRepository:

    return OrderRepository(db)


# ==========================================================
# ORDER SERVICE
# ==========================================================


def get_order_service(
    order_repository: OrderRepository = Depends(
        get_order_repository,
    ),
) -> OrderService:

    return OrderService(
        order_repository,
    )


# ==========================================================
# POSITION REPOSITORY
# ==========================================================


def get_position_repository(
    db: AsyncSession = Depends(get_db),
) -> PositionRepository:

    return PositionRepository(db)


# ==========================================================
# POSITION SERVICE
# ==========================================================


def get_position_service(
    position_repository: PositionRepository = Depends(
        get_position_repository,
    ),
) -> PositionService:

    return PositionService(
        position_repository,
    )


# ==========================================================
# TRADE SERVICE
# ==========================================================


def get_trade_service(
    db: AsyncSession = Depends(get_db),
) -> TradeService:

    return TradeService(
        repository=TradeRepository(db),
        position_repository=PositionRepository(db),
    )


# ==========================================================
# STRATEGY RUN SERVICE
# ==========================================================


def get_strategy_run_service(
    db: AsyncSession = Depends(get_db),
) -> StrategyRunService:

    return StrategyRunService(
        StrategyRunRepository(db),
    )


# ==========================================================
# PERFORMANCE SERVICE
# ==========================================================


def get_performance_service(
    db: AsyncSession = Depends(get_db),
) -> PerformanceService:

    return PerformanceService(
        repository=PerformanceRepository(db),
        trade_repository=TradeRepository(db),
    )


# ==========================================================
# RISK SNAPSHOT SERVICE
# ==========================================================


def get_risk_snapshot_service(
    db: AsyncSession = Depends(get_db),
) -> RiskSnapshotService:

    return RiskSnapshotService(
        RiskSnapshotRepository(db),
    )


# ==========================================================
# BROKER MANAGER
# ==========================================================


def get_broker_manager() -> BrokerManager:
    """
    Return the broker manager used by the trading engine.

    The broker implementation is selected from application
    configuration.
    """

    adapter = get_broker_adapter(
        settings.BROKER,
    )

    return BrokerManager(
        adapter,
    )


# ==========================================================
# EXECUTION SERVICE
# ==========================================================


def get_execution_service(
    broker: BrokerManager = Depends(
        get_broker_manager,
    ),
) -> ExecutionService:

    return ExecutionService(
        broker=broker,
    )


# ==========================================================
# ORDER EXECUTION SERVICE
# ==========================================================


def get_order_execution_service(
    order_repository: OrderRepository = Depends(
        get_order_repository,
    ),
    execution_service: ExecutionService = Depends(
        get_execution_service,
    ),
) -> OrderExecutionService:

    return OrderExecutionService(
        order_repository=order_repository,
        execution_service=execution_service,
    )


# ==========================================================
# POSITION SYNC SERVICE
# ==========================================================


def get_position_sync_service(
    position_repository: PositionRepository = Depends(
        get_position_repository,
    ),
    position_service: PositionService = Depends(
        get_position_service,
    ),
    order_repository: OrderRepository = Depends(
        get_order_repository,
    ),
    execution_service: ExecutionService = Depends(
        get_execution_service,
    ),
    trade_service: TradeService = Depends(
        get_trade_service,
    ),
) -> PositionSyncService:

    return PositionSyncService(
        execution_service=execution_service,
        position_repository=position_repository,
        position_service=position_service,
        order_repository=order_repository,
        trade_service=trade_service,
    )


# ==========================================================
# ANALYTICS SERVICE
# ==========================================================


def get_analytics_service(
    db: AsyncSession = Depends(get_db),
) -> AnalyticsService:

    return AnalyticsService(
        repository=AnalyticsRepository(db),
    )


# ==========================================================
# RISK SERVICE
# ==========================================================

# ==================================
# BOT SERVICE
# ==========================================================


def get_bot_service(
    db: AsyncSession = Depends(get_db),
) -> BotService:

    return BotService(
        StrategyRunRepository(db),
    )


# ==========================================================
# MT5 BRIDGE SERVICE
# ==========================================================


def get_mt5_bridge_service() -> MT5BridgeService:
    """
    Provide the AQE service responsible for communicating
    with the MT5 bridge.
    """
    return MT5BridgeService()


# ==========================================================
# SYMBOL SYNC SERVICE
# ==========================================================


def get_symbol_sync_service(
    bridge_service: MT5BridgeService = Depends(
        get_mt5_bridge_service,
    ),
    trading_account_repository: TradingAccountRepository = Depends(
        get_trading_account_repository,
    ),
    symbol_repository: SymbolRepository = Depends(
        get_symbol_repository,
    ),
    account_symbol_repository: AccountSymbolRepository = Depends(
        get_account_symbol_repository,
    ),
) -> SymbolSyncService:

    return SymbolSyncService(
        bridge_service=bridge_service,
        trading_account_repository=trading_account_repository,
        symbol_repository=symbol_repository,
        account_symbol_repository=account_symbol_repository,
    )
