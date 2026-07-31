from fastapi import APIRouter, Depends, HTTPException, status

from app.api.dependencies import get_current_user, get_trade_service
from app.schemas.trade import TradeCreate, TradeUpdate, TradeResponse
from app.core.constants import TradeResult

router = APIRouter(prefix="/trades", tags=["trades"], dependencies=[Depends(get_current_user)])


@router.post("/", response_model=TradeResponse, status_code=status.HTTP_201_CREATED)
async def create_trade(payload: TradeCreate, service=Depends(get_trade_service)):
    try:
        return await service.create_trade(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/", response_model=list[TradeResponse])
async def list_trades(service=Depends(get_trade_service)):
    return await service.get_trades()


@router.get("/{trade_id}", response_model=TradeResponse)
async def get_trade(trade_id: str, service=Depends(get_trade_service)):
    try:
        return await service.get_trade(trade_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.patch("/{trade_id}", response_model=TradeResponse)
async def update_trade(
    trade_id: str,
    payload: TradeUpdate,
    service=Depends(get_trade_service),
):
    try:
        return await service.update_trade(trade_id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.delete("/{trade_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_trade(trade_id: str, service=Depends(get_trade_service)):
    try:
        await service.delete_trade(trade_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/result/{result}", response_model=list[TradeResponse])
async def list_by_result(result: TradeResult, service=Depends(get_trade_service)):
    return await service.get_result_trades(result)
