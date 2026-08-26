from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    status,
)

from app.api.dependencies import (
    get_current_user,
    get_risk_service,
)
from app.risk.exceptions import (
    DailyLossLimitExceeded,
    DrawdownLimitExceeded,
    InvalidRiskConfiguration,
    OpenRiskLimitExceeded,
    PositionLimitExceeded,
    RiskCalculationError,
    RiskProfileNotFound,
    RiskLimitExceeded,
    StrategyExposureLimitExceeded,
    SymbolExposureLimitExceeded,
)
from app.risk.schemas import (
    RiskCheckRequest,
    RiskCheckResponse,
    RiskProfileCreate,
    RiskProfileResponse,
    RiskProfileUpdate,
    RiskSizingRequest,
    RiskSizingResponse,
)
from app.risk.service import RiskService


router = APIRouter(
    prefix="/risk",
    tags=["risk"],
    dependencies=[
        Depends(get_current_user),
    ],
)


# ==========================================================
# GET RISK PROFILE
# ==========================================================

@router.get(
    "/accounts/{account_id}",
    response_model=RiskProfileResponse,
)
async def get_risk_profile(
    account_id: UUID,
    service: RiskService = Depends(
        get_risk_service
    ),
):
    try:
        return await service.get_profile(
            account_id
        )

    except RiskProfileNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc


# ==========================================================
# CREATE RISK PROFILE
# ==========================================================

@router.post(
    "/accounts/{account_id}",
    response_model=RiskProfileResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_risk_profile(
    account_id: UUID,
    payload: RiskProfileCreate,
    service: RiskService = Depends(
        get_risk_service
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

    try:
        return await service.create_profile(
            payload
        )

    except InvalidRiskConfiguration as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc


# ==========================================================
# UPDATE RISK PROFILE
# ==========================================================

@router.patch(
    "/accounts/{account_id}",
    response_model=RiskProfileResponse,
)
async def update_risk_profile(
    account_id: UUID,
    payload: RiskProfileUpdate,
    service: RiskService = Depends(
        get_risk_service
    ),
):

    try:
        return await service.update_profile(
            account_id=account_id,
            data=payload,
        )

    except RiskProfileNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

    except InvalidRiskConfiguration as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc


# ==========================================================
# EFFECTIVE RISK
# ==========================================================

@router.get(
    "/accounts/{account_id}/effective-risk",
)
async def get_effective_risk(
    account_id: UUID,
    service: RiskService = Depends(
        get_risk_service
    ),
):
    try:
        risk_percent = (
            await service.get_effective_risk_percent(
                account_id
            )
        )

        return {
            "account_id": account_id,
            "effective_risk_percent": (
                risk_percent
            ),
        }

    except RiskProfileNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc


# ==========================================================
# POSITION SIZE CALCULATOR
# ==========================================================

@router.post(
    "/accounts/{account_id}/position-size",
    response_model=RiskSizingResponse,
)
async def calculate_position_size(
    account_id: UUID,
    payload: RiskSizingRequest,
    service: RiskService = Depends(
        get_risk_service
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

    try:
        return await service.calculate_position_size(payload)

    except RiskProfileNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

    except (InvalidRiskConfiguration, RiskCalculationError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc


# ==========================================================
# RISK CHECK
# ==========================================================

@router.post(
    "/accounts/{account_id}/check",
    response_model=RiskCheckResponse,
)
async def check_risk(
    account_id: UUID,
    payload: RiskCheckRequest,
    service: RiskService = Depends(
        get_risk_service
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

    try:
        return await service.check_trade(
            payload
        )

    except RiskProfileNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

    except (
        DailyLossLimitExceeded,
        DrawdownLimitExceeded,
        OpenRiskLimitExceeded,
        PositionLimitExceeded,
        SymbolExposureLimitExceeded,
        StrategyExposureLimitExceeded,
        RiskLimitExceeded,
    ) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc

    except InvalidRiskConfiguration as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    except RiskCalculationError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc