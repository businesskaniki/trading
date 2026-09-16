from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import SessionLocal, get_db
from app.schemas.historical_data import (
    HistoricalCandleListResponse,
    HistoricalDataSyncRequest,
    HistoricalDataSyncResponse,
)
from app.services.historical_data_service import HistoricalDataService
from app.services.mt5_bridge_service import MT5BridgeService

router = APIRouter(
    prefix="/historical-data",
    tags=["Historical Data"],
)


def get_historical_data_service() -> HistoricalDataService:
    """
    Provide the historical-data service.

    SessionLocal is the application's existing async session factory.
    MT5BridgeService communicates with the configured MT5 bridge.
    """

    return HistoricalDataService(
        session_factory=SessionLocal,
        bridge_service=MT5BridgeService(),
    )


# ==========================================================
# SYNCHRONIZATION
# ==========================================================


@router.post(
    "/sync/{account_id}",
    response_model=HistoricalDataSyncResponse,
    status_code=status.HTTP_200_OK,
)
async def sync_historical_data(
    account_id: UUID,
    request: HistoricalDataSyncRequest,
    service: HistoricalDataService = Depends(get_historical_data_service),
):
    """
    Synchronize historical candles for all enabled symbols
    belonging to the specified trading account.

    Only AccountSymbol.enabled=True symbols are synchronized.
    """

    try:
        result = await service.sync_selected_symbols(
            account_id=account_id,
            timeframe=request.timeframe,
            count=request.count,
        )

        return result

    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Historical data synchronization failed: {exc}",
        ) from exc


# ==========================================================
# LATEST HISTORICAL CANDLES
# ==========================================================


@router.get(
    "/{symbol_id}/latest",
    response_model=HistoricalCandleListResponse,
    status_code=status.HTTP_200_OK,
)
async def get_latest_historical_candles(
    symbol_id: UUID,
    timeframe: str = Query(
        default="M15",
        min_length=1,
        max_length=10,
    ),
    limit: int = Query(
        default=200,
        ge=1,
        le=10000,
    ),
    service: HistoricalDataService = Depends(get_historical_data_service),
):
    """
    Retrieve the latest persisted historical candles for a symbol.

    Results are returned in ascending timestamp order.
    """

    try:
        candles = await service.get_latest_candles(
            symbol_id=symbol_id,
            timeframe=timeframe,
            limit=limit,
        )

    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve latest historical candles: {exc}",
        ) from exc

    return HistoricalCandleListResponse(
        symbol_id=symbol_id,
        timeframe=timeframe,
        count=len(candles),
        candles=candles,
    )


# ==========================================================
# HISTORICAL CANDLES BY RANGE
# ==========================================================


@router.get(
    "/{symbol_id}",
    response_model=HistoricalCandleListResponse,
    status_code=status.HTTP_200_OK,
)
async def get_historical_candles(
    symbol_id: UUID,
    timeframe: str = Query(
        default="M15",
        min_length=1,
        max_length=10,
    ),
    start: datetime | None = Query(
        default=None,
    ),
    end: datetime | None = Query(
        default=None,
    ),
    limit: int | None = Query(
        default=None,
        ge=1,
        le=10000,
    ),
    service: HistoricalDataService = Depends(get_historical_data_service),
):
    """
    Retrieve persisted historical candles for a symbol.

    Optional start/end parameters restrict the timestamp range.

    Results are returned in ascending timestamp order.
    """

    if start is not None and end is not None and start > end:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="start must be earlier than or equal to end",
        )

    try:
        candles = await service.get_candles(
            symbol_id=symbol_id,
            timeframe=timeframe,
            start=start,
            end=end,
            limit=limit,
        )

    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve historical candles: {exc}",
        ) from exc

    return HistoricalCandleListResponse(
        symbol_id=symbol_id,
        timeframe=timeframe,
        count=len(candles),
        candles=candles,
    )
