import MetaTrader5 as mt5

from app.core.logging import logger


class MT5Client:
    """
    Low-level client responsible for communicating with MetaTrader 5.
    """

    def __init__(self):
        self.connected = False

    def connect(
        self,
        login: int,
        password: str,
        server: str,
    ) -> bool:
        """
        Initialize the MT5 terminal and authenticate
        against the requested trading account.
        """

        try:
            if not mt5.initialize():
                logger.error(
                    "MT5 initialize failed: %s",
                    mt5.last_error(),
                )
                self.connected = False
                return False

            authorized = mt5.login(
                login=login,
                password=password,
                server=server,
            )

            if not authorized:
                logger.error(
                    "MT5 login failed for account %s: %s",
                    login,
                    mt5.last_error(),
                )

                mt5.shutdown()
                self.connected = False

                return False

            account = mt5.account_info()

            if account is None:
                logger.error(
                    "MT5 login succeeded but account information "
                    "could not be retrieved: %s",
                    mt5.last_error(),
                )

                mt5.shutdown()
                self.connected = False

                return False

            self.connected = True

            logger.info(
                "Connected to MT5 account %s on server %s",
                account.login,
                account.server,
            )

            return True

        except Exception:
            self.connected = False

            logger.exception("Unexpected MT5 connection error")

            return False

    def disconnect(self) -> None:
        """
        Disconnect from the MT5 terminal.
        """

        try:
            mt5.shutdown()

        finally:
            self.connected = False

            logger.info("Disconnected from MT5")

    def is_connected(self) -> bool:
        """
        Check whether MT5 is currently accessible.
        """

        if not self.connected:
            return False

        try:
            account = mt5.account_info()

            if account is None:
                self.connected = False
                return False

            return True

        except Exception:
            self.connected = False
            return False

    def account_info(self):
        """
        Return the currently authenticated MT5 account.
        """

        return mt5.account_info()

    def terminal_info(self):
        """
        Return MT5 terminal information.
        """

        return mt5.terminal_info()

    def version(self):
        """
        Return the MT5 terminal version.
        """

        return mt5.version()

    def last_error(self):
        """
        Return the latest MT5 error.
        """

        return mt5.last_error()
