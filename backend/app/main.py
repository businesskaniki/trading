from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.core.config import settings
from app.infrastructure.redis import redis_client
from app.market_data.consumer import market_data_redis_consumer
from app.market_data.live import live_tick_hub
from app.market_data.subscription_manager import (
    market_data_subscription_manager,
)
from app.market_data.historical_synchronizer import (
    historical_data_synchronizer,
)

# The backend's core/ has no dedicated logging module (unlike the
# bridge's app/core/logging.py), so nothing was configuring a root
# handler. Every logger.info()/logger.exception() call across the
# whole app - including MarketDataConsumer's diagnostic logging -
# was silently going nowhere. This must run before anything else
# below produces a single log line.
logging.basicConfig(
    level=logging.INFO if settings.DEBUG else logging.WARNING,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """AQE application lifecycle.

    Startup:
        1. Connect to Redis.
        2. Start the market-data Redis consumer.
        3. Reconcile market-data subscriptions with the MT5 Bridge.
        4. Start the historical-data synchronizer.

    Shutdown:
        1. Stop the historical-data synchronizer.
        2. Stop the market-data Redis consumer.
        3. Disconnect from Redis.
    """

    # ==================================================================
    # STARTUP
    # ==================================================================

    await redis_client.connect()

    await market_data_redis_consumer.start()
    await live_tick_hub.start()

    # --------------------------------------------------------------
    # Reconcile live market-data subscriptions.
    # --------------------------------------------------------------
    #
    # This is intentionally best-effort.
    #
    # If the MT5 Bridge is not connected/authenticated yet, AQE
    # should still start.
    #
    # The database remains the source of truth and a later
    # reconciliation can restore the desired subscriptions.
    #
    # NOTE: previously this was a bare `except Exception: pass`,
    # which meant a genuine reconciliation failure (bridge
    # unreachable, bad response shape, a bug in reconcile() itself)
    # produced zero visibility anywhere - the app just started with
    # subscriptions silently missing. Logging it doesn't change the
    # best-effort behavior (startup still continues either way), it
    # just means the failure is no longer invisible.
    #
    try:
        await market_data_subscription_manager.reconcile()

    except Exception:
        logger.exception(
            "Failed to reconcile market-data subscriptions on startup. "
            "AQE will continue starting; subscriptions may be missing "
            "until the next successful reconciliation."
        )

    # --------------------------------------------------------------
    # Start automatic historical-data synchronization.
    # --------------------------------------------------------------
    #
    # The synchronizer will continuously inspect AccountSymbol.enabled
    # and synchronize historical data for the current trading universe.
    #
    # It runs independently from the live market-data subscription
    # manager.
    #
    try:
        await historical_data_synchronizer.start()

    except Exception:
        # Historical synchronization must not prevent AQE from
        # starting. The background service is responsible for
        # handling subsequent synchronization attempts. Logged for
        # the same reason as the reconcile() failure above - silent
        # here previously meant no way to know it happened at all.
        logger.exception(
            "Failed to start historical-data synchronizer on startup."
        )

    try:
        yield

    finally:

        # ==============================================================
        # SHUTDOWN
        # ==============================================================

        # Stop historical synchronization first so it cannot start
        # another database/bridge operation while the application is
        # shutting down.
        await historical_data_synchronizer.stop()

        # Stop the live market-data consumer.
        await market_data_redis_consumer.stop()
        await live_tick_hub.stop()

        # Finally disconnect Redis.
        await redis_client.disconnect()


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    lifespan=lifespan,
)


app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        origin.strip() for origin in settings.CORS_ORIGINS.split(",") if origin.strip()
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


app.include_router(
    api_router,
    prefix=settings.API_PREFIX,
)


@app.get("/")
async def root():
    return {
        "status": "running",
    }