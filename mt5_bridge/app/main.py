from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.router import router
from app.infrastructure.redis.client import redis_client
from app.services.market_data_service import market_data_service


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Manage the MT5 Bridge application lifecycle.

    Startup order:
        1. Connect to Redis.
        2. Verify Redis connectivity.
        3. Start market-data service.

    Shutdown order:
        1. Stop market-data service.
        2. Disconnect Redis.
    """

    print("Starting MT5 Bridge...")

    # ---------------------------------------------------------
    # Startup
    # ---------------------------------------------------------

    # Redis must be available before the market-data service
    # starts publishing ticks.
    await redis_client.connect()

    # Confirm the Redis connection is healthy.
    await redis_client.ping()

    print("Redis connection established.")

    # Start market-data polling only after Redis is ready.
    market_data_service.start()

    print("Market-data service started.")

    try:
        yield

    finally:
        # -----------------------------------------------------
        # Shutdown
        # -----------------------------------------------------

        print("Stopping MT5 Bridge...")

        # Stop market-data polling before closing Redis.
        await market_data_service.stop()

        print("Market-data service stopped.")

        # Close the Redis connection after all publishers
        # have stopped using it.
        await redis_client.disconnect()

        print("Redis connection closed.")
        print("MT5 Bridge shutdown complete.")


app = FastAPI(
    title="MT5 Bridge",
    version="1.0.0",
    lifespan=lifespan,
)

app.include_router(router)
