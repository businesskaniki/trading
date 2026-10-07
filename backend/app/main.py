from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.core.config import settings
from app.core.engine import get_aqe_engine
from app.core.engine import EngineStatus
from app.infrastructure.redis import redis_client

# ----------------------------------------------------------------------
# Logging
# ----------------------------------------------------------------------
#
# The backend does not have a dedicated logging configuration module.
# Configure the root logger here before the application starts so all
# application components can emit useful diagnostics.
# ----------------------------------------------------------------------

# logging.basicConfig(
#     level=logging.INFO if settings.DEBUG else logging.WARNING,
#     format="%(asctime)s %(levelname)s %(name)s %(message)s",
# )

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    AQE application lifecycle.

    FastAPI owns application infrastructure.

    AQEEngine has its own independent trading-runtime lifecycle.

    FastAPI startup does NOT start the AQE trading engine.

    Startup:
        1. Connect to Redis.
        2. Make the API available.
        3. Leave AQEEngine in STOPPED state.

    AQE Engine startup:
        Explicitly triggered through the engine control layer/API.

    Shutdown:
        1. Stop the AQE trading engine if it is active.
        2. Disconnect Redis.

    This separation is intentional:

        FastAPI application lifecycle
                    ≠
        AQE trading runtime lifecycle
    """

    # ==================================================================
    # APPLICATION STARTUP
    # ==================================================================

    logger.info("Starting AQE backend application.")

    # Redis is application infrastructure and can safely start with
    # FastAPI. This does NOT start market-data polling or trading.
    await redis_client.connect()

    logger.info("AQE Redis infrastructure connected.")

    aqe_engine = get_aqe_engine()

    # ------------------------------------------------------------------
    # IMPORTANT:
    #
    # Do NOT call:
    #
    #     await aqe_engine.start()
    #
    # here.
    #
    # Starting FastAPI must not automatically start:
    #
    #     - broker connection
    #     - MT5
    #     - market-data polling
    #     - symbol subscriptions
    #     - historical synchronization
    #     - strategy runtime
    #     - risk pipeline
    #     - execution pipeline
    #
    # Those are part of the AQE trading runtime and are started
    # explicitly through the engine control API.
    # ------------------------------------------------------------------

    logger.info(
        "AQE trading engine is not auto-started. " "Current engine status=%s",
        aqe_engine.context.status.value,
    )

    logger.info("AQE backend application started.")

    try:
        yield

    finally:
        # ==============================================================
        # APPLICATION SHUTDOWN
        # ==============================================================

        logger.info("Stopping AQE backend application.")

        try:
            # ----------------------------------------------------------
            # Stop the trading runtime only if it was explicitly
            # started during the lifetime of the application.
            # ----------------------------------------------------------

            if aqe_engine.context.status is not EngineStatus.STOPPED:
                logger.info(
                    "Stopping AQE trading engine. status=%s",
                    aqe_engine.context.status.value,
                )

                await aqe_engine.stop()

                logger.info("AQE trading engine stopped.")

            else:
                logger.info(
                    "AQE trading engine already stopped. "
                    "No trading-runtime shutdown required."
                )

        finally:
            # ----------------------------------------------------------
            # Redis belongs to the application infrastructure, so it
            # is disconnected when FastAPI shuts down.
            # ----------------------------------------------------------

            await redis_client.disconnect()

            logger.info("AQE Redis infrastructure disconnected.")

        logger.info("AQE backend application stopped.")


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
