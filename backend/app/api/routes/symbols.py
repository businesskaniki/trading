from uuid import UUID

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user
from app.database.session import get_db
from app.repositories.symbol_repository import SymbolRepository
from app.schemas.symbol import (
    SymbolCreate,
    SymbolListResponse,
    SymbolResponse,
    SymbolUpdate,
)
from app.services.symbol_service import SymbolService

router = APIRouter(
    prefix="/symbols",
    tags=["Symbols"],
)


def get_symbol_service(
    db: AsyncSession = Depends(get_db),
) -> SymbolService:
    repository = SymbolRepository(db)

    return SymbolService(
        repository=repository,
    )


@router.post(
    "/",
    response_model=SymbolResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_symbol(
    data: SymbolCreate,
    current_user=Depends(get_current_user),
    service: SymbolService = Depends(get_symbol_service),
):
    """
    Create a canonical AQE trading symbol.
    """

    return await service.create_symbol(
        data=data,
    )


@router.get(
    "/",
    response_model=SymbolListResponse,
)
async def list_symbols(
    active_only: bool = False,
    current_user=Depends(get_current_user),
    service: SymbolService = Depends(get_symbol_service),
):
    """
    Return canonical trading symbols.
    """

    symbols = await service.list_symbols(
        active_only=active_only,
    )

    return SymbolListResponse(
        items=symbols,
        total=len(symbols),
    )


@router.get(
    "/{symbol_id}",
    response_model=SymbolResponse,
)
async def get_symbol(
    symbol_id: UUID,
    current_user=Depends(get_current_user),
    service: SymbolService = Depends(get_symbol_service),
):
    """
    Return a canonical trading symbol.
    """

    return await service.get_symbol(
        symbol_id=symbol_id,
    )


@router.patch(
    "/{symbol_id}",
    response_model=SymbolResponse,
)
async def update_symbol(
    symbol_id: UUID,
    data: SymbolUpdate,
    current_user=Depends(get_current_user),
    service: SymbolService = Depends(get_symbol_service),
):
    """
    Update a canonical trading symbol.
    """

    return await service.update_symbol(
        symbol_id=symbol_id,
        data=data,
    )


@router.delete(
    "/{symbol_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_symbol(
    symbol_id: UUID,
    current_user=Depends(get_current_user),
    service: SymbolService = Depends(get_symbol_service),
):
    """
    Delete a canonical trading symbol.
    """

    await service.delete_symbol(
        symbol_id=symbol_id,
    )

    return Response(
        status_code=status.HTTP_204_NO_CONTENT,
    )
