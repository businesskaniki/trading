from fastapi import APIRouter, HTTPException

from app.core.mt5_connection import mt5_connection


router = APIRouter(
    prefix="/connection",
    tags=["Connection"],
)


@router.post("/connect")
def connect():

    connected = mt5_connection.connect()

    if not connected:
        raise HTTPException(
            status_code=500,
            detail={
                "message": "Failed to connect to MetaTrader 5",
                "status": mt5_connection.status(),
            },
        )

    return mt5_connection.status()


@router.post("/disconnect")
def disconnect():

    mt5_connection.disconnect()

    return {
        "connected": False,
        "message": "Disconnected from MetaTrader 5",
    }


@router.get("/status")
def status():

    return mt5_connection.status()