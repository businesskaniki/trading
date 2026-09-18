from fastapi import APIRouter, HTTPException, status

from app.schemas.connection import (
    ConnectRequest,
    ConnectionStatus,
    DisconnectResponse,
)
from app.services.connection_service import connection_service


router = APIRouter(
    prefix="/connection",
    tags=["Connection"],
)


@router.post(
    "/connect",
    response_model=ConnectionStatus,
)
def connect(data: ConnectRequest):

    connected = connection_service.connect(
        login=data.login,
        password=data.password,
        server=data.server,
    )

    if not connected:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to connect to MetaTrader 5.",
        )

    return connection_service.status()


@router.post(
    "/disconnect",
    response_model=DisconnectResponse,
)
def disconnect():

    return connection_service.disconnect()


@router.get(
    "/status",
    response_model=ConnectionStatus,
)
def status():

    return connection_service.status()