
from __future__ import annotations

from typing import Any

import MetaTrader5 as mt5

from app.broker.mt5_lock import mt5_synchronized
from app.core.logging import logger


class MT5Client:
    """
    Low-level client for the MetaTrader 5 terminal.

    Trading credentials are supplied by AQE at runtime.

    Responsibilities:
        - Connect to a requested trading account.
        - Verify the actual account and server.
        - Reuse an existing healthy session.
        - Recover an inaccessible or disconnected session.
        - Expose account, terminal, version and error information.

    Connection lifecycle operations use the shared MT5 API lock.
    Credentials are not persisted by this client.
    """

    def __init__(self) -> None:
        self.connected = False
        self.login: int | None = None
        self.server: str | None = None
        self.last_error_message: str | None = None

    # =========================================================
    # INTERNAL HELPERS
    # =========================================================

    def _set_disconnected(
        self,
        message: str | None = None,
        *,
        clear_identity: bool = False,
    ) -> None:
        self.connected = False
        self.last_error_message = message

        if clear_identity:
            self.login = None
            self.server = None

    @staticmethod
    def _account_matches(
        account: Any,
        login: int,
        server: str,
    ) -> bool:
        if account is None:
            return False

        return (
            getattr(account, "login", None) == login
            and getattr(account, "server", None) == server
        )

    def _existing_session(
        self,
        login: int,
        server: str,
    ) -> tuple[bool, bool]:
        """
        Inspect the existing terminal session.

        Returns:
            (expected_session_exists, broker_connected)

        This method is called from connect(), which already holds
        the shared MT5 API lock.
        """

        try:
            terminal = mt5.terminal_info()
            account = mt5.account_info()

        except Exception:
            logger.exception(
                "Failed to inspect the existing MT5 session."
            )
            return False, False

        if terminal is None:
            return False, False

        if not self._account_matches(account, login, server):
            return False, False

        return (
            True,
            bool(getattr(terminal, "connected", False)),
        )

    @staticmethod
    def _shutdown_terminal() -> None:
        """
        Release the MT5 Python API connection.

        Call from a method already protected by the shared lock.
        """

        try:
            mt5.shutdown()
        except Exception:
            logger.debug(
                "MT5 shutdown raised an exception.",
                exc_info=True,
            )

    # =========================================================
    # CONNECT
    # =========================================================

    @mt5_synchronized
    def connect(
        self,
        login: int,
        password: str,
        server: str,
    ) -> bool:
        """
        Connect to the requested trading account.

        A healthy session for the requested account is reused.
        If the session is inaccessible or disconnected, the client
        attempts to initialize MT5 using the supplied credentials.
        """

        try:
            login = int(login)
            password = str(password)
            server = str(server).strip()

            if login <= 0:
                self._set_disconnected(
                    "MT5 login must be greater than zero."
                )
                return False

            if not password:
                self._set_disconnected(
                    "MT5 password cannot be empty."
                )
                return False

            if not server:
                self._set_disconnected(
                    "MT5 server cannot be empty."
                )
                return False

            # Reuse the already healthy session.
            if self.login == login and self.server == server:
                session_exists, broker_connected = (
                    self._existing_session(login, server)
                )

                if session_exists and broker_connected:
                    self.connected = True
                    self.last_error_message = None

                    logger.debug(
                        "Reusing healthy MT5 session for account %s "
                        "on server %s.",
                        login,
                        server,
                    )
                    return True

                if session_exists:
                    logger.warning(
                        "MT5 account %s is selected, but broker "
                        "connectivity is unhealthy. Attempting "
                        "controlled reinitialization.",
                        login,
                    )
                else:
                    logger.warning(
                        "Existing MT5 session could not be verified "
                        "for account %s. Attempting recovery.",
                        login,
                    )

            # No reusable healthy session exists. Reset the API
            # connection while holding the shared lock.
            self.connected = False
            self.last_error_message = None

            self._shutdown_terminal()

            initialized = mt5.initialize(
                login=login,
                password=password,
                server=server,
            )

            if not initialized:
                error = mt5.last_error()
                message = (
                    f"MT5 initialization failed for account {login} "
                    f"on server {server}: {error}"
                )

                self._set_disconnected(
                    message,
                    clear_identity=True,
                )
                logger.error("%s", message)
                return False

            # Verify both terminal availability and account identity.
            terminal = mt5.terminal_info()
            account = mt5.account_info()

            if terminal is None or account is None:
                error = mt5.last_error()
                message = (
                    "MT5 initialized, but terminal or account "
                    f"information is unavailable: {error}"
                )

                logger.error("%s", message)
                self._shutdown_terminal()

                self._set_disconnected(
                    message,
                    clear_identity=True,
                )
                return False

            actual_login = getattr(account, "login", None)
            actual_server = getattr(account, "server", None)

            if actual_login != login or actual_server != server:
                message = (
                    "MT5 account verification failed. "
                    f"Expected login={login}, server={server!r}; "
                    f"actual login={actual_login}, "
                    f"server={actual_server!r}."
                )

                logger.error("%s", message)
                self._shutdown_terminal()

                self._set_disconnected(
                    message,
                    clear_identity=True,
                )
                return False

            # Preserve the verified identity, even when broker
            # connectivity is not yet ready.
            self.login = actual_login
            self.server = actual_server

            if not bool(getattr(terminal, "connected", False)):
                message = (
                    "The expected MT5 account is selected, but "
                    "the terminal is not connected to the broker."
                )

                self._set_disconnected(message)
                logger.warning("%s", message)

                # The ConnectionService retains the credentials and
                # can retry initialization later.
                return False

            self.connected = True
            self.last_error_message = None

            logger.info(
                "Connected to MT5 account %s on server %s.",
                self.login,
                self.server,
            )
            return True

        except (TypeError, ValueError) as exc:
            message = f"Invalid MT5 connection parameters: {exc}"
            self._set_disconnected(message)
            logger.warning("%s", message)
            return False

        except Exception as exc:
            message = f"Unexpected MT5 connection error: {exc}"
            logger.exception("Unexpected MT5 connection error.")

            self._shutdown_terminal()
            self._set_disconnected(
                message,
                clear_identity=True,
            )
            return False

    # =========================================================
    # DISCONNECT
    # =========================================================

    @mt5_synchronized
    def disconnect(self) -> None:
        """Disconnect the bridge's MT5 API session."""

        self._shutdown_terminal()
        self._set_disconnected(clear_identity=True)

        logger.info("MT5 bridge connection disconnected.")

    # =========================================================
    # CONNECTION HEALTH
    # =========================================================

    @mt5_synchronized
    def is_connected(self) -> bool:
        """
        Verify terminal connectivity and account identity.

        This method checks health but does not attempt reconnection.
        """

        if self.login is None or self.server is None:
            self.connected = False
            return False

        try:
            terminal = mt5.terminal_info()
            account = mt5.account_info()

            if terminal is None:
                self._set_disconnected(
                    "MT5 terminal information is unavailable: "
                    f"{mt5.last_error()}"
                )
                return False

            if account is None:
                self._set_disconnected(
                    "MT5 account information is unavailable: "
                    f"{mt5.last_error()}"
                )
                return False

            actual_login = getattr(account, "login", None)
            actual_server = getattr(account, "server", None)

            if actual_login != self.login or actual_server != self.server:
                message = (
                    "MT5 account identity mismatch. "
                    f"Expected login={self.login}, "
                    f"server={self.server!r}; "
                    f"actual login={actual_login}, "
                    f"server={actual_server!r}."
                )

                self._set_disconnected(message)
                logger.error("%s", message)
                return False

            if not bool(getattr(terminal, "connected", False)):
                self._set_disconnected(
                    "MT5 terminal is available, but broker "
                    "connectivity is unavailable."
                )
                return False

            self.connected = True
            self.last_error_message = None
            return True

        except Exception as exc:
            self._set_disconnected(
                f"MT5 connection health check failed: {exc}"
            )
            logger.exception("MT5 connection health check failed.")
            return False

    # =========================================================
    # ACCOUNT
    # =========================================================

    @mt5_synchronized
    def account_info(self) -> Any:
        """Return the current MT5 account information."""
        return mt5.account_info()

    # =========================================================
    # TERMINAL
    # =========================================================

    @mt5_synchronized
    def terminal_info(self) -> Any:
        """Return MT5 terminal information."""
        return mt5.terminal_info()

    # =========================================================
    # VERSION
    # =========================================================

    @mt5_synchronized
    def version(self) -> Any:
        """Return the MT5 terminal version."""
        return mt5.version()

    # =========================================================
    # LAST ERROR
    # =========================================================

    @mt5_synchronized
    def last_error(self) -> Any:
        """Return the bridge-level or underlying MT5 error."""
        if self.last_error_message is not None:
            return self.last_error_message

        return mt5.last_error()
