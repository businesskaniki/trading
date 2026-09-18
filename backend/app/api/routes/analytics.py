from datetime import datetime
from decimal import Decimal
from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    status,
)

from app.api.dependencies import (
    get_analytics_service,
    get_current_user,
    get_owned_account,
)
from app.schemas.analytics import (
    AccountPerformanceSummary,
    DailyPnLPoint,
    DailyPnLRequest,
    DirectionComparison,
    DirectionPerformance,
    DrawdownPoint,
    DrawdownRequest,
    EquityCurveRequest,
    EquityPoint,
    MonthlyPnLPoint,
    MonthlyPnLRequest,
    ProfitDistributionResponse,
    StrategyComparison,
    StrategyPerformance,
    SymbolComparison,
    SymbolPerformance,
    TradeStatistics,
    TradeStatisticsRequest,
)
from app.services.analytics_service import (
    AnalyticsService,
)


router = APIRouter(
    prefix="/analytics",
    tags=["analytics"],
    dependencies=[
        Depends(get_current_user),
        Depends(get_owned_account),
    ],
)


# ==========================================================
# ACCOUNT SUMMARY
# ==========================================================

@router.get(
    "/accounts/{account_id}/summary",
    response_model=AccountPerformanceSummary,
)
async def get_account_summary(
    account_id: UUID,
    service: AnalyticsService = Depends(
        get_analytics_service
    ),
):

    return await service.get_account_summary(
        account_id
    )


# ==========================================================
# EQUITY CURVE
# ==========================================================

@router.post(
    "/accounts/{account_id}/equity",
    response_model=list[EquityPoint],
)
async def get_account_equity_curve(
    account_id: UUID,
    payload: EquityCurveRequest,
    service: AnalyticsService = Depends(
        get_analytics_service
    ),
):

    if payload.account_id != account_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "account_id in request body must match "
                "account_id in URL"
            ),
        )

    if payload.end <= payload.start:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="end must be later than start",
        )

    return await service.get_account_equity_curve(
        account_id=account_id,
        start=payload.start,
        end=payload.end,
        starting_balance=payload.starting_balance,
    )


# ==========================================================
# DAILY P&L
# ==========================================================

@router.post(
    "/accounts/{account_id}/pnl/daily",
    response_model=list[DailyPnLPoint],
)
async def get_daily_pnl(
    account_id: UUID,
    payload: DailyPnLRequest,
    service: AnalyticsService = Depends(
        get_analytics_service
    ),
):

    if payload.account_id != account_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "account_id in request body must match "
                "account_id in URL"
            ),
        )

    if payload.end <= payload.start:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="end must be later than start",
        )

    return await service.get_daily_pnl(
        account_id=account_id,
        start=payload.start,
        end=payload.end,
    )


# ==========================================================
# MONTHLY P&L
# ==========================================================

@router.post(
    "/accounts/{account_id}/pnl/monthly",
    response_model=list[MonthlyPnLPoint],
)
async def get_monthly_pnl(
    account_id: UUID,
    payload: MonthlyPnLRequest,
    service: AnalyticsService = Depends(
        get_analytics_service
    ),
):

    if payload.account_id != account_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "account_id in request body must match "
                "account_id in URL"
            ),
        )

    if payload.end <= payload.start:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="end must be later than start",
        )

    return await service.get_monthly_pnl(
        account_id=account_id,
        start=payload.start,
        end=payload.end,
    )


# ==========================================================
# DRAWDOWN
# ==========================================================

@router.post(
    "/accounts/{account_id}/drawdown",
    response_model=list[DrawdownPoint],
)
async def get_drawdown(
    account_id: UUID,
    payload: DrawdownRequest,
    service: AnalyticsService = Depends(
        get_analytics_service
    ),
):

    if payload.account_id != account_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "account_id in request body must match "
                "account_id in URL"
            ),
        )

    if payload.end <= payload.start:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="end must be later than start",
        )

    return await service.get_drawdown(
        account_id=account_id,
        start=payload.start,
        end=payload.end,
        starting_balance=payload.starting_balance,
    )


# ==========================================================
# STRATEGY PERFORMANCE
# ==========================================================

@router.get(
    "/accounts/{account_id}/strategies",
    response_model=list[StrategyPerformance],
)
async def get_strategy_performance(
    account_id: UUID,
    service: AnalyticsService = Depends(
        get_analytics_service
    ),
):

    return await service.get_strategy_performance(
        account_id
    )


# ==========================================================
# STRATEGY COMPARISON
# ==========================================================

@router.get(
    "/accounts/{account_id}/strategies/comparison",
    response_model=list[StrategyComparison],
)
async def get_strategy_comparison(
    account_id: UUID,
    service: AnalyticsService = Depends(
        get_analytics_service
    ),
):

    return await service.get_strategy_comparison(
        account_id
    )


# ==========================================================
# SYMBOL PERFORMANCE
# ==========================================================

@router.get(
    "/accounts/{account_id}/symbols",
    response_model=list[SymbolPerformance],
)
async def get_symbol_performance(
    account_id: UUID,
    service: AnalyticsService = Depends(
        get_analytics_service
    ),
):

    return await service.get_symbol_performance(
        account_id
    )


# ==========================================================
# SYMBOL COMPARISON
# ==========================================================

@router.get(
    "/accounts/{account_id}/symbols/comparison",
    response_model=list[SymbolComparison],
)
async def get_symbol_comparison(
    account_id: UUID,
    service: AnalyticsService = Depends(
        get_analytics_service
    ),
):

    return await service.get_symbol_comparison(
        account_id
    )


# ==========================================================
# DIRECTION PERFORMANCE
# ==========================================================

@router.get(
    "/accounts/{account_id}/directions",
    response_model=list[DirectionPerformance],
)
async def get_direction_performance(
    account_id: UUID,
    service: AnalyticsService = Depends(
        get_analytics_service
    ),
):

    return await service.get_direction_performance(
        account_id
    )


# ==========================================================
# DIRECTION COMPARISON
# ==========================================================

@router.get(
    "/accounts/{account_id}/directions/comparison",
    response_model=list[DirectionComparison],
)
async def get_direction_comparison(
    account_id: UUID,
    service: AnalyticsService = Depends(
        get_analytics_service
    ),
):

    return await service.get_direction_comparison(
        account_id
    )


# ==========================================================
# TRADE STATISTICS
# ==========================================================

@router.post(
    "/accounts/{account_id}/trade-statistics",
    response_model=TradeStatistics,
)
async def get_trade_statistics(
    account_id: UUID,
    payload: TradeStatisticsRequest,
    service: AnalyticsService = Depends(
        get_analytics_service
    ),
):

    if payload.account_id != account_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "account_id in request body must match "
                "account_id in URL"
            ),
        )

    if payload.end <= payload.start:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="end must be later than start",
        )

    return await service.get_trade_statistics(
        account_id=account_id,
        start=payload.start,
        end=payload.end,
    )


# ==========================================================
# PROFIT DISTRIBUTION
# ==========================================================

@router.post(
    "/accounts/{account_id}/profit-distribution",
    response_model=ProfitDistributionResponse,
)
async def get_profit_distribution(
    account_id: UUID,
    payload: TradeStatisticsRequest,
    bucket_size: Decimal = Query(
        Decimal("10.00"),
        gt=0,
    ),
    service: AnalyticsService = Depends(
        get_analytics_service
    ),
):

    if payload.account_id != account_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "account_id in request body must match "
                "account_id in URL"
            ),
        )

    if payload.end <= payload.start:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="end must be later than start",
        )

    return await service.get_profit_distribution(
        account_id=account_id,
        start=payload.start,
        end=payload.end,
        bucket_size=bucket_size,
    )