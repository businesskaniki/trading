from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from app.core.engine import get_aqe_engine
from engine.exceptions import EngineStateError

router = APIRouter(
    prefix="/engine",
    tags=["Engine"],
)


class EngineStartRequest(BaseModel):
    """
    Request payload used to start the AQE trading runtime.

    The account ID identifies which TradingAccount should be resolved
    and used to construct the account-specific execution runtime.
    """

    account_id: UUID


@router.get("/status")
async def get_engine_status() -> dict:
    """
    Return the current AQE engine state and component status.
    """

    engine = get_aqe_engine()

    return engine.snapshot()


@router.post("/start")
async def start_engine(
    request: EngineStartRequest,
) -> dict:
    """
    Explicitly start the AQE trading runtime for a trading account.

    Starting the FastAPI application does not start AQE.

    The selected TradingAccount is resolved by the execution runtime
    factory. Broker credentials are retrieved internally and are never
    supplied by this API request.

    Starting AQE initializes:

        - trading account runtime
        - broker connection
        - market-data runtime
        - live subscriptions
        - historical synchronization
        - strategy runtime
        - risk pipeline
        - execution pipeline
    """

    engine = get_aqe_engine()

    try:
        await engine.start(
            account_id=request.account_id,
        )

    except EngineStateError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc

    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to start AQE engine: {exc}",
        ) from exc

    return engine.snapshot()


@router.post("/stop")
async def stop_engine() -> dict:
    """
    Explicitly stop the AQE trading runtime.

    This stops the runtime components owned by AQEEngine, including:

        - signal/risk/execution pipeline
        - strategies
        - historical synchronization
        - live tick hub
        - market-data consumer
        - broker connection

    The selected runtime account is released after shutdown.
    """

    engine = get_aqe_engine()

    try:
        await engine.stop()

    except EngineStateError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc

    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to stop AQE engine: {exc}",
        ) from exc

    return engine.snapshot()


@router.post("/pause")
async def pause_engine() -> dict:
    """
    Pause the AQE trading runtime.

    Broker connectivity and market-data infrastructure remain active.
    Running strategies are paused.
    """

    engine = get_aqe_engine()

    try:
        await engine.pause()

    except EngineStateError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc

    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to pause AQE engine: {exc}",
        ) from exc

    return engine.snapshot()


@router.post("/resume")
async def resume_engine() -> dict:
    """
    Resume the AQE trading runtime from PAUSED state.
    """

    engine = get_aqe_engine()

    try:
        await engine.resume()

    except EngineStateError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc

    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to resume AQE engine: {exc}",
        ) from exc

    return engine.snapshot()
