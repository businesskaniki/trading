from fastapi import APIRouter

from app.api.routes import (
    auth,
    orders,
    performance,
    positions,
    risk_snapshots,
    strategy_runs,
    symbols,
    trading_accounts,
    trades,
    broker,
    execution,
    analytics,
    risk,
    bot,
    stream,
)

api_router = APIRouter()

api_router.include_router(auth.router)
api_router.include_router(symbols.router)
api_router.include_router(trading_accounts.router)
api_router.include_router(orders.router)
api_router.include_router(positions.router)
api_router.include_router(trades.router)
api_router.include_router(strategy_runs.router)
api_router.include_router(performance.router)
api_router.include_router(risk_snapshots.router)
api_router.include_router(broker.router)
api_router.include_router(execution.router)
api_router.include_router(analytics.router)
api_router.include_router(risk.router)
api_router.include_router(bot.router)
api_router.include_router(stream.router)

