
from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI

from app.api.router import router
from app.infrastructure.redis.client import redis_client
from app.services.connection_service import connection_service
from app.services.market_data_service import market_data_service


logger = logging.getLogger("mt5_bridge.lifecycle")

REDIS_RETRY_INTERVAL = 5.0


async def _maintain_redis_connection() -> None:
    """
    Keep the bridge's Redis connection available.

    Redis outages must not prevent the MT5 bridge from starting.
    Failed connections are retried until Redis becomes available.

    Market-data publication already handles Redis publishing errors,
    so a temporary Redis outage does not terminate the polling task.
    """

    while True:
        try:
            if redis_client.is_connected:
                await redis_client.ping()
            else:
                await redis_client.connect()
                logger.info("Redis connection established or restored.")

        except asyncio.CancelledError:
            raise

        except Exception as exc:
            logger.warning(
                "Redis is unavailable. Retrying in %.1f seconds. Error: %s",
                REDIS_RETRY_INTERVAL,
                exc,
            )

            # Reset the failed client and pool so the next attempt
            # creates a fresh connection.
            await redis_client.disconnect()

        await asyncio.sleep(REDIS_RETRY_INTERVAL)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Manage the MT5 Bridge application lifecycle.

    Startup:
        1. Start Redis connection maintenance.
        2. Start the MT5 connection monitor.
        3. Start market-data polling.

    Shutdown:
        1. Stop market-data polling.
        2. Stop MT5 connection monitoring.
        3. Stop Redis maintenance.
        4. Close Redis resources.
    """

    redis_task: asyncio.Task | None = None
    connection_monitor_started = False

    logger.info("Starting MT5 Bridge.")

    try:
        # Redis recovery runs independently of application startup.
        # If Redis is unavailable, its task retries in the background.
        redis_task = asyncio.create_task(
            _maintain_redis_connection(),
            name="mt5-bridge-redis-maintenance",
        )

        # The monitor only reconnects accounts whose credentials have
        # already been supplied through the authenticated connection API.
        await connection_service.start_monitor()
        connection_monitor_started = True

        # Polling can remain idle until symbols and an MT5 connection
        # become available.
        market_data_service.start()

        logger.info("MT5 Bridge services started.")

        yield

    finally:
        logger.info("Stopping MT5 Bridge.")

        # Stop polling before closing the shared Redis connection.
        try:
            await market_data_service.stop()
        except Exception:
            logger.exception("Failed to stop market-data service cleanly.")

        if connection_monitor_started:
            try:
                await connection_service.stop_monitor()
            except Exception:
                logger.exception("Failed to stop MT5 monitor cleanly.")

        if redis_task is not None:
            redis_task.cancel()
            with suppress(asyncio.CancelledError):
                await redis_task

        await redis_client.disconnect()

        logger.info("MT5 Bridge shutdown complete.")


app = FastAPI(
    title="MT5 Bridge",
    version="1.0.0",
    lifespan=lifespan,
)

# Authentication is provided by app.api.router.
# Do not add a second bridge-token dependency here.
app.include_router(router)
