from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Optional

import MetaTrader5 as mt5

logger = logging.getLogger("mt5_connection")


class MT5ConnectionManager:
    """
    Manages the bridge's connection to a MetaTrader 5 terminal
    and trading account.

    Account credentials are supplied at runtime by AQE.

    The bridge does NOT obtain trading credentials from environment
    variables or configuration files.

    Responsibilities:
        - establish the MT5 terminal connection;
        - authenticate the requested MT5 trading account;
        - verify the connected account;
        - monitor connection health;
        - reconnect using the same runtime credentials;
        - expose connection/account status.

    This manager deliberately does NOT:
        - persist credentials;
        - perform order execution;
        - perform risk calculations;
        - manage strategies;
        - access the AQE database.
    """

    def __init__(
        self,
        monitor_interval: float = 5.0,
    ):
        if monitor_interval <= 0:
            raise ValueError("MT5 monitor interval must be greater than zero.")

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

        # Runtime-only credentials.
        #
        # These are intentionally kept in memory so the connection
        # monitor can reconnect to the same account after a transient
        # terminal/network failure.
        #
        # They are never included in status() or log messages.
        self._credentials: Optional[dict[str, Any]] = None

        self._monitor_task: Optional[asyncio.Task] = None
        self._stopping: bool = False

    # =========================================================
    # CREDENTIAL NORMALIZATION
    # =========================================================

    @staticmethod
    def _normalize_credentials(
        credentials: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Validate and normalize runtime MT5 credentials.

        Expected fields:

            login
                MT5 account number.

            password
                MT5 trading password.

            server
                Exact MT5 trade-server name.
        """

        if not isinstance(credentials, dict):
            raise ValueError("MT5 credentials must be provided as an object.")

        login_raw = credentials.get("login")
        password_raw = credentials.get("password")
        server_raw = credentials.get("server")

        if login_raw is None:
            raise ValueError("MT5 login is required.")

        if password_raw is None:
            raise ValueError("MT5 password is required.")

        if server_raw is None:
            raise ValueError("MT5 server is required.")

        try:
            login = int(login_raw)
        except (TypeError, ValueError) as exc:
            raise ValueError(
                "MT5 login must be a valid integer account number."
            ) from exc

        if login <= 0:
            raise ValueError("MT5 login must be greater than zero.")

        password = str(password_raw)

        if not password:
            raise ValueError("MT5 password cannot be empty.")

        server = str(server_raw).strip()

        if not server:
            raise ValueError("MT5 server cannot be empty.")

        return {
            "login": login,
            "password": password,
            "server": server,
        }

    # =========================================================
    # CONNECT
    # =========================================================

    def connect(
        self,
        credentials: Optional[dict[str, Any]] = None,
    ) -> bool:
        """
        Connect to the requested MT5 trading account.

        Credentials are supplied by AQE at runtime.

        When credentials are explicitly supplied they replace any
        previously stored runtime credentials.

        When credentials are omitted, the previously supplied runtime
        credentials are used. This is specifically for automatic
        reconnection by the connection monitor.

        The method deliberately does NOT call mt5.initialize()
        without credentials because doing so can attach to the
        terminal's previously selected/default account.
        """

        try:

            # -----------------------------------------------------
            # Resolve credentials
            # -----------------------------------------------------

            if credentials is not None:
                normalized_credentials = self._normalize_credentials(credentials)

                self._credentials = normalized_credentials

            elif self._credentials is not None:
                normalized_credentials = dict(self._credentials)

            else:
                self.connected = False
                self.last_error = (
                    "MT5 account credentials are required " "to establish a connection."
                )

                logger.error("MT5 connection attempted without runtime credentials.")

                return False

            login = normalized_credentials["login"]
            password = normalized_credentials["password"]
            server = normalized_credentials["server"]

            # -----------------------------------------------------
            # Reset any existing MT5 session
            # -----------------------------------------------------

            #
            # MT5 exposes a process-level terminal connection. When
            # switching accounts, explicitly shut down the existing
            # connection before initializing the requested account.
            #

            try:
                mt5.shutdown()
            except Exception:
                logger.debug(
                    "MT5 shutdown before reconnect raised an exception.",
                    exc_info=True,
                )

            self.connected = False

            # -----------------------------------------------------
            # Initialize MT5 against the requested account
            # -----------------------------------------------------

            initialized = mt5.initialize(
                login=login,
                password=password,
                server=server,
            )

            if not initialized:

                error = mt5.last_error()

                self.connected = False
                self.last_error = str(error)

                logger.error(
                    "Failed to initialize MT5 for account %s " "on server %s: %s",
                    login,
                    server,
                    error,
                )

                return False

            # -----------------------------------------------------
            # Verify the actual connected account
            # -----------------------------------------------------

            account = mt5.account_info()

            if account is None:

                error = mt5.last_error()

                self.connected = False
                self.last_error = str(error)

                logger.error(
                    "MT5 initialized but account information "
                    "could not be retrieved for account %s: %s",
                    login,
                    error,
                )

                try:
                    mt5.shutdown()
                except Exception:
                    logger.debug(
                        "MT5 shutdown after failed account verification "
                        "raised an exception.",
                        exc_info=True,
                    )

                return False

            # -----------------------------------------------------
            # Prevent accidental connection to the wrong account
            # -----------------------------------------------------

            actual_login = getattr(
                account,
                "login",
                None,
            )

            actual_server = getattr(
                account,
                "server",
                None,
            )

            if actual_login != login:

                self.connected = False
                self.last_error = (
                    "MT5 connected to an unexpected account. "
                    f"Requested login={login}, "
                    f"actual login={actual_login}."
                )

                logger.error(
                    "MT5 account verification failed: "
                    "requested login=%s, actual login=%s",
                    login,
                    actual_login,
                )

                try:
                    mt5.shutdown()
                except Exception:
                    logger.debug(
                        "MT5 shutdown after account mismatch " "raised an exception.",
                        exc_info=True,
                    )

                return False

            if actual_server != server:

                self.connected = False
                self.last_error = (
                    "MT5 connected to an unexpected server. "
                    f"Requested server={server!r}, "
                    f"actual server={actual_server!r}."
                )

                logger.error(
                    "MT5 server verification failed: "
                    "requested server=%s, actual server=%s",
                    server,
                    actual_server,
                )

                try:
                    mt5.shutdown()
                except Exception:
                    logger.debug(
                        "MT5 shutdown after server mismatch " "raised an exception.",
                        exc_info=True,
                    )

                return False

            # -----------------------------------------------------
            # Store verified connection information
            # -----------------------------------------------------

            self.connected = True

            self.login = actual_login
            self.name = getattr(
                account,
                "name",
                None,
            )
            self.server = actual_server

            self.balance = getattr(
                account,
                "balance",
                None,
            )
            self.equity = getattr(
                account,
                "equity",
                None,
            )

            self.last_error = None
            self.last_connected_at = time.time()

            logger.info(
                "Connected to MT5 account %s on server %s",
                self.login,
                self.server,
            )

            return True

        except ValueError as exc:

            self.connected = False
            self.last_error = str(exc)

            logger.error(
                "Invalid MT5 connection credentials: %s",
                exc,
            )

            return False

        except Exception as exc:

            self.connected = False
            self.last_error = str(exc)

            logger.exception("Unexpected MT5 connection error")

            try:
                mt5.shutdown()
            except Exception:
                logger.debug(
                    "MT5 shutdown after unexpected connection "
                    "failure raised an exception.",
                    exc_info=True,
                )

            return False

    # =========================================================
    # DISCONNECT
    # =========================================================

    def disconnect(self) -> None:
        """
        Disconnect from MT5.

        Manual disconnect clears the runtime credentials so the
        background monitor does not immediately reconnect to the
        account that was intentionally disconnected.
        """

        try:
            mt5.shutdown()

        except Exception as exc:

            logger.exception(
                "Error while shutting down MT5: %s",
                exc,
            )

        finally:

            self.connected = False

            self.login = None
            self.name = None
            self.server = None

            self.balance = None
            self.equity = None

            self.last_disconnected_at = time.time()

            self._credentials = None

            logger.info("Disconnected from MT5")

    # =========================================================
    # CONNECTION CHECK
    # =========================================================

    def is_connected(self) -> bool:
        """
        Verify that the MT5 terminal is connected to the expected
        runtime-specified trading account.
        """

        try:

            account = mt5.account_info()

            if account is None:
                self.connected = False
                return False

            # -----------------------------------------------------
            # If runtime credentials exist, verify account identity.
            # -----------------------------------------------------

            if self._credentials is not None:

                expected_login = self._credentials["login"]

                expected_server = self._credentials["server"]

                actual_login = getattr(
                    account,
                    "login",
                    None,
                )

                actual_server = getattr(
                    account,
                    "server",
                    None,
                )

                if actual_login != expected_login:

                    self.connected = False
                    self.last_error = (
                        "MT5 account changed unexpectedly. "
                        f"Expected login={expected_login}, "
                        f"actual login={actual_login}."
                    )

                    logger.error(
                        "Unexpected MT5 account detected: "
                        "expected login=%s, actual login=%s",
                        expected_login,
                        actual_login,
                    )

                    return False

                if actual_server != expected_server:

                    self.connected = False
                    self.last_error = (
                        "MT5 server changed unexpectedly. "
                        f"Expected server={expected_server!r}, "
                        f"actual server={actual_server!r}."
                    )

                    logger.error(
                        "Unexpected MT5 server detected: "
                        "expected server=%s, actual server=%s",
                        expected_server,
                        actual_server,
                    )

                    return False

            # -----------------------------------------------------
            # Update account state
            # -----------------------------------------------------

            self.login = getattr(
                account,
                "login",
                None,
            )

            self.name = getattr(
                account,
                "name",
                None,
            )

            self.server = getattr(
                account,
                "server",
                None,
            )

            self.balance = getattr(
                account,
                "balance",
                None,
            )

            self.equity = getattr(
                account,
                "equity",
                None,
            )

            self.connected = True
            self.last_error = None

            return True

        except Exception as exc:

            self.connected = False
            self.last_error = str(exc)

            return False

    # =========================================================
    # ENSURE CONNECTION
    # =========================================================

    def ensure_connection(self) -> bool:
        """
        Ensure the bridge remains connected to the expected MT5
        trading account.

        Automatic reconnection is only possible when runtime
        credentials are available in memory.
        """

        if self.is_connected():

            self.connected = True
            self.last_error = None

            return True

        self.connected = False
        self.last_disconnected_at = time.time()

        # ---------------------------------------------------------
        # Never fall back to mt5.initialize() without credentials.
        # ---------------------------------------------------------

        if self._credentials is None:

            self.last_error = (
                "MT5 connection unavailable and no runtime "
                "credentials are available for reconnection."
            )

            logger.warning(
                "MT5 connection is unavailable and no runtime "
                "credentials are available for reconnection."
            )

            return False

        logger.warning(
            "MT5 connection lost for account %s. " "Attempting to reconnect...",
            self._credentials.get("login"),
        )

        return self.connect()

    # =========================================================
    # BACKGROUND MONITOR
    # =========================================================

    async def monitor(self) -> None:
        """
        Continuously monitor MT5 connection health.
        """

        logger.info(
            "MT5 connection monitor started " "(interval=%s seconds)",
            self.monitor_interval,
        )

        while not self._stopping:

            try:

                connected = self.ensure_connection()

                if connected:

                    logger.debug("MT5 connection healthy.")

                else:

                    logger.warning("MT5 connection is unavailable.")

            except Exception as exc:

                logger.exception(
                    "MT5 connection monitor error: %s",
                    exc,
                )

            await asyncio.sleep(self.monitor_interval)

        logger.info("MT5 connection monitor stopped.")

    # =========================================================
    # START MONITOR
    # =========================================================

    def start_monitor(self) -> None:
        """
        Start the background MT5 connection monitor.
        """

        self._stopping = False

        if self._monitor_task is None or self._monitor_task.done():

            self._monitor_task = asyncio.create_task(self.monitor())

            logger.info("MT5 monitor task created.")

    # =========================================================
    # STOP MONITOR
    # =========================================================

    async def stop_monitor(self) -> None:
        """
        Stop the background MT5 connection monitor.
        """

        self._stopping = True

        if self._monitor_task is not None:

            self._monitor_task.cancel()

            try:

                await self._monitor_task

            except asyncio.CancelledError:

                pass

            finally:

                self._monitor_task = None

        logger.info("MT5 monitor task stopped.")

    # =========================================================
    # STATUS
    # =========================================================

    def status(self) -> dict[str, Any]:
        """
        Return safe connection/account status.

        Password and other credentials are intentionally never
        exposed.
        """

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
