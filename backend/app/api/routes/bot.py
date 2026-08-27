from fastapi import APIRouter, Depends, HTTPException, status

from app.api.dependencies import get_bot_service, get_current_user
from app.schemas.bot import BotStartRequest, BotStatusResponse


router = APIRouter(
    prefix="/bot",
    tags=["bot"],
    dependencies=[Depends(get_current_user)],
)


@router.get("/status", response_model=BotStatusResponse)
async def get_bot_status(
    current_user=Depends(get_current_user),
    service=Depends(get_bot_service),
):
    return await service.status(current_user.id)


@router.post("/start", response_model=BotStatusResponse, status_code=status.HTTP_201_CREATED)
async def start_bot(
    payload: BotStartRequest,
    current_user=Depends(get_current_user),
    service=Depends(get_bot_service),
):
    try:
        return await service.start(current_user.id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.post("/stop", response_model=BotStatusResponse)
async def stop_bot(
    current_user=Depends(get_current_user),
    service=Depends(get_bot_service),
):
    return await service.stop(current_user.id)