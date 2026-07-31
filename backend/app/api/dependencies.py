from fastapi import Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.dependencies import get_db
from app.core.security import oauth2_scheme, verify_token
from app.repositories.order_repository import OrderRepository
from app.repositories.performance_repository import PerformanceRepository
from app.repositories.position_repository import PositionRepository
from app.repositories.strategy_run_repository import StrategyRunRepository
from app.repositories.symbol_repository import SymbolRepository
from app.repositories.trade_repository import TradeRepository
from app.repositories.trading_account_repository import TradingAccountRepository
from app.repositories.snapshot_repository import RiskSnapshotRepository
from app.repositories.user_repository import UserRepository
from app.services.order_service import OrderService
from app.services.performance_service import PerformanceService
from app.services.position_service import PositionService
from app.services.strategy_run_service import StrategyRunService
from app.services.symbol_service import SymbolService
from app.services.trade_service import TradeService
from app.services.trading_account_service import TradingAccountService
from app.services.risk_snapshot_service import RiskSnapshotService
from app.services.user_service import UserService


def get_db_session(db: AsyncSession = Depends(get_db)) -> AsyncSession:
    return db


async def get_current_user(token: str = Depends(oauth2_scheme), db: AsyncSession = Depends(get_db)):
    try:
        payload = verify_token(token, expected_type="access")
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = await UserRepository(db).get_by_id(payload["sub"])
    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid user",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


def get_symbol_service(db: AsyncSession = Depends(get_db)):
    return SymbolService(SymbolRepository(db))


def get_trading_account_service(db: AsyncSession = Depends(get_db)):
    return TradingAccountService(TradingAccountRepository(db))


def get_order_service(db: AsyncSession = Depends(get_db)):
    return OrderService(OrderRepository(db))


def get_position_service(db: AsyncSession = Depends(get_db)):
    return PositionService(PositionRepository(db))


def get_trade_service(db: AsyncSession = Depends(get_db)):
    return TradeService(TradeRepository(db))


def get_strategy_run_service(db: AsyncSession = Depends(get_db)):
    return StrategyRunService(StrategyRunRepository(db))


def get_performance_service(db: AsyncSession = Depends(get_db)):
    return PerformanceService(PerformanceRepository(db))


def get_risk_snapshot_service(db: AsyncSession = Depends(get_db)):
    return RiskSnapshotService(RiskSnapshotRepository(db))


def get_user_service(db: AsyncSession = Depends(get_db)):
    return UserService(UserRepository(db))
