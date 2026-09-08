from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.core.config import settings
from app.infrastructure.redis import redis_client
from app.market_data.consumer import market_data_redis_consumer


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    AQE application lifecycle.

    Startup:
        1. Connect to Redis.
        2. Start the market-data Redis consumer.

    Shutdown:
        1. Stop the market-data Redis consumer.
        2. Disconnect from Redis.
    """

    # =========================================================
    # STARTUP
    # =========================================================

    await redis_client.connect()

    await market_data_redis_consumer.start()

    try:
        yield

    finally:
        # =====================================================
        # SHUTDOWN
        # =====================================================

        await market_data_redis_consumer.stop()

        await redis_client.disconnect()


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    lifespan=lifespan,
)


# =============================================================
# CORS
# =============================================================

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        origin.strip() for origin in settings.CORS_ORIGINS.split(",") if origin.strip()
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# =============================================================
# API ROUTES
# =============================================================

app.include_router(
    api_router,
    prefix=settings.API_PREFIX,
)


# =============================================================
# ROOT
# =============================================================


@app.get("/")
async def root():
    return {
        "status": "running",
    }
