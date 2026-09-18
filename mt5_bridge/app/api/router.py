
import hmac

from fastapi import APIRouter, Depends, Header, HTTPException, status

from app.core.config import settings


async def require_bridge_token(
	x_bridge_token: str | None = Header(default=None),
) -> None:
	configured = settings.MT5_BRIDGE_TOKEN
	if not configured or not x_bridge_token or not hmac.compare_digest(
		x_bridge_token,
		configured,
	):
		raise HTTPException(
			status_code=status.HTTP_401_UNAUTHORIZED,
			detail="Invalid bridge credentials.",
		)

from app.api.routes.account import router as account_router
from app.api.routes.connection import router as connection_router
from app.api.routes.history import router as history_router
from app.api.routes.market_data import router as market_data_router
from app.api.routes.orders import router as orders_router
from app.api.routes.positions import router as positions_router
from app.api.routes.symbols import router as symbols_router


router = APIRouter(dependencies=[Depends(require_bridge_token)])


router.include_router(connection_router)

router.include_router(account_router)

router.include_router(symbols_router)

router.include_router(orders_router)

router.include_router(positions_router)

router.include_router(history_router)

router.include_router(market_data_router)
