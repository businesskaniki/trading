from fastapi import APIRouter, HTTPException

from app.schemas.account import AccountResponse
from app.services.account_service import AccountService

router = APIRouter(
    prefix="/account",
    tags=["Account"],
)

service = AccountService()


@router.get(
    "",
    response_model=AccountResponse,
)
def get_account():

    try:

        account = service.get_account()

        return AccountResponse(**account)

    except Exception as exc:

        raise HTTPException(
            status_code=500,
            detail=str(exc),
        )