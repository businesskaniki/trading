import MetaTrader5 as mt5

from app.core.logging import logger


class MT5Client:
    """
    Handles the connection to the MetaTrader 5 terminal.
    """

    def __init__(self):
        self.connected = False

    def connect(
        self,
        login: int,
        password: str,
        server: str,
    ) -> bool:

        if not mt5.initialize():
            logger.error(
                f"MT5 initialize failed: {mt5.last_error()}"
            )
            return False

        authorized = mt5.login(
            login=login,
            password=password,
            server=server,
        )

        if not authorized:
            logger.error(
                f"MT5 login failed: {mt5.last_error()}"
            )
            mt5.shutdown()
            return False

        self.connected = True

        logger.info(
            f"Connected to MT5 account {login}"
        )

        return True

    def disconnect(self):

        mt5.shutdown()

        self.connected = False

        logger.info("Disconnected from MT5")

    def is_connected(self):

        return self.connected

    def terminal_info(self):

        return mt5.terminal_info()

    def version(self):

        return mt5.version()