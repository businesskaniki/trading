from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.router import router
from app.core.mt5_connection import mt5_connection


@asynccontextmanager
async def lifespan(app: FastAPI):

    # =========================================================
    # STARTUP
    # =========================================================

    print("Starting MT5 Bridge...")

    connected = mt5_connection.connect()

    if connected:

        print("MT5 connection established.")

    else:

        print(
            "WARNING: MT5 connection failed during startup."
        )

    # Start the background connection monitor
    mt5_connection.start_monitor()

    print(
        "MT5 connection monitor started."
    )

    # Give control back to FastAPI
    yield

    # =========================================================
    # SHUTDOWN
    # =========================================================

    print(
        "Stopping MT5 connection monitor..."
    )

    await mt5_connection.stop_monitor()

    print(
        "Disconnecting from MT5..."
    )

    mt5_connection.disconnect()

    print(
        "MT5 Bridge shutdown complete."
    )


app = FastAPI(
    title="MT5 Bridge",
    version="1.0.0",
    lifespan=lifespan,
)


app.include_router(router)