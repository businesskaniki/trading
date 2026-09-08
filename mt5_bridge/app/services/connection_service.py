from app.broker.mt5_client import MT5Client


class ConnectionService:
    """
    Application service responsible for MT5 connection management.
    """

    def __init__(self):
        self.client = MT5Client()

        self.login: int | None = None
        self.server: str | None = None
        self.name: str | None = None
        self.last_error: str | None = None

    def connect(
        self,
        login: int,
        password: str,
        server: str,
    ) -> bool:
        """
        Connect to a specific MT5 trading account.
        """

        connected = self.client.connect(
            login=login,
            password=password,
            server=server,
        )

        if not connected:
            self.last_error = str(
                self.client.last_error()
            )

            return False

        account = self.client.account_info()

        if account is not None:
            self.login = account.login
            self.server = account.server
            self.name = account.name

        self.last_error = None

        return True

    def disconnect(self) -> dict:
        """
        Disconnect the currently connected MT5 account.
        """

        self.client.disconnect()

        self.login = None
        self.server = None
        self.name = None

        return {
            "success": True,
            "message": "Disconnected successfully.",
        }

    def is_connected(self) -> bool:
        """
        Check whether the current MT5 connection is healthy.
        """

        connected = self.client.is_connected()

        if not connected:
            self.last_error = str(
                self.client.last_error()
            )

        return connected

    def status(self) -> dict:
        """
        Return connection status.
        """

        connected = self.is_connected()

        return {
            "connected": connected,
            "login": self.login,
            "server": self.server,
            "name": self.name,
            "last_error": self.last_error,
        }

    def version(self):
        return self.client.version()

    def terminal_info(self):
        return self.client.terminal_info()