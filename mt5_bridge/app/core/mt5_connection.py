import asyncio
import logging
import time
from typing import Optional

import MetaTrader5 as mt5


logger = logging.getLogger("mt5_connection")


class MT5ConnectionManager:

    def __init__(
        self,
        monitor_interval: float = 5.0,
    ):
        self.monitor_interval = monitor_interval

        self.connected: bool = False

        self.login: Optional[int] = None
        self.name: Optional[str] = None
        self.server: Optional[str] = None

        self.balance: Optional[float] = None
        self.equity: Optional[float] = None

        self.last_error: Optional[str] = None

        self.last_connected_at: Optional[float] = None
        self.last_disconnected_at: Optional[float] = None

        self._monitor_task: Optional[asyncio.Task] = None
        self._stopping: bool = False

    # =========================================================
    # CONNECT
    # =========================================================

    def connect(self) -> bool:

        try:
            # Initialize MT5
            initialized = mt5.initialize()

            if not initialized:

                error = mt5.last_error()

                self.connected = False
                self.last_error = str(error)

                logger.error(
                    "Failed to initialize MT5: %s",
                    error,
                )

                return False

            # Verify that we can actually access the account
            account = mt5.account_info()

            if account is None:

                error = mt5.last_error()

                self.connected = False
                self.last_error = str(error)

                logger.error(
                    "MT5 initialized but account information "
                    "could not be retrieved: %s",
                    error,
                )

                return False

            # Store connection information
            self.connected = True

            self.login = account.login
            self.name = account.name
            self.server = account.server

            self.balance = account.balance
            self.equity = account.equity

            self.last_error = None
            self.last_connected_at = time.time()

            logger.info(
                "Connected to MT5 account %s",
                account.login,
            )

            return True

        except Exception as exc:

            self.connected = False
            self.last_error = str(exc)

            logger.exception(
                "Unexpected MT5 connection error"
            )

            return False

    # =========================================================
    # DISCONNECT
    # =========================================================

    def disconnect(self):

        try:
            mt5.shutdown()

        except Exception as exc:

            logger.exception(
                "Error while shutting down MT5: %s",
                exc,
            )

        finally:

            self.connected = False
            self.last_disconnected_at = time.time()

            logger.info(
                "Disconnected from MT5"
            )

    # =========================================================
    # CONNECTION CHECK
    # =========================================================

    def is_connected(self) -> bool:

        try:

            # account_info() is a useful lightweight
            # connectivity check.

            account = mt5.account_info()

            if account is None:

                return False

            # Update account information while we're here.
            self.login = account.login
            self.name = account.name
            self.server = account.server

            self.balance = account.balance
            self.equity = account.equity

            return True

        except Exception:

            return False

    # =========================================================
    # ENSURE CONNECTION
    # =========================================================

    def ensure_connection(self) -> bool:

        if self.is_connected():

            self.connected = True
            self.last_error = None

            return True

        # Connection has been lost.
        self.connected = False
        self.last_disconnected_at = time.time()

        logger.warning(
            "MT5 connection lost. Attempting to reconnect..."
        )

        return self.connect()

    # =========================================================
    # BACKGROUND MONITOR
    # =========================================================

    async def monitor(self):

        logger.info(
            "MT5 connection monitor started "
            "(interval=%s seconds)",
            self.monitor_interval,
        )

        while not self._stopping:

            try:

                connected = self.ensure_connection()

                if connected:

                    logger.debug(
                        "MT5 connection healthy."
                    )

                else:

                    logger.warning(
                        "MT5 connection is unavailable."
                    )

            except Exception as exc:

                logger.exception(
                    "MT5 connection monitor error: %s",
                    exc,
                )

            await asyncio.sleep(
                self.monitor_interval
            )

        logger.info(
            "MT5 connection monitor stopped."
        )

    # =========================================================
    # START MONITOR
    # =========================================================

    def start_monitor(self):

        self._stopping = False

        if (
            self._monitor_task is None
            or self._monitor_task.done()
        ):

            self._monitor_task = asyncio.create_task(
                self.monitor()
            )

            logger.info(
                "MT5 monitor task created."
            )

    # =========================================================
    # STOP MONITOR
    # =========================================================

    async def stop_monitor(self):

        self._stopping = True

        if self._monitor_task is not None:

            self._monitor_task.cancel()

            try:

                await self._monitor_task

            except asyncio.CancelledError:

                pass

            finally:

                self._monitor_task = None

        logger.info(
            "MT5 monitor task stopped."
        )

    # =========================================================
    # STATUS
    # =========================================================

    def status(self) -> dict:

        return {
            "connected": self.connected,
            "login": self.login,
            "name": self.name,
            "server": self.server,
            "balance": self.balance,
            "equity": self.equity,
            "last_error": self.last_error,
            "last_connected_at": self.last_connected_at,
            "last_disconnected_at": self.last_disconnected_at,
        }


# =============================================================
# GLOBAL CONNECTION MANAGER
# =============================================================

mt5_connection = MT5ConnectionManager(
    monitor_interval=5.0,
)