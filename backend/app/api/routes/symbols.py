from fastapi import APIRouter, Depends, HTTPException, status

from app.api.dependencies import get_current_user, get_symbol_service
from app.schemas.symbol import SymbolCreate, SymbolUpdate, SymbolResponse
from app.database.models.symbol import Symbol

router = APIRouter(prefix="/symbols", tags=["symbols"], dependencies=[Depends(get_current_user)])


@router.post("/", response_model=SymbolResponse, status_code=status.HTTP_201_CREATED)
async def create_symbol(
    payload: SymbolCreate,
    service=Depends(get_symbol_service),
):
    try:
        symbol = await service.create_symbol(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return symbol


@router.get("/", response_model=list[SymbolResponse])
async def list_symbols(service=Depends(get_symbol_service)):
    return await service.get_symbols()


@router.get("/{symbol_id}", response_model=SymbolResponse)
async def get_symbol(symbol_id: str, service=Depends(get_symbol_service)):
    try:
        return await service.get_symbol(symbol_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.patch("/{symbol_id}", response_model=SymbolResponse)
async def update_symbol(
    symbol_id: str,
    payload: SymbolUpdate,
    service=Depends(get_symbol_service),
):
    try:
        return await service.update_symbol(symbol_id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.delete("/{symbol_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_symbol(symbol_id: str, service=Depends(get_symbol_service)):
    try:
        await service.delete_symbol(symbol_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
