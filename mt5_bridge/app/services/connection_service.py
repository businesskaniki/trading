import asyncio
from contextlib import suppress
from threading import RLock

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
        self._lock = RLock()
        self._password: str | None = None
        self._auto_reconnect = False
        self._monitor_task: asyncio.Task | None = None

    def connect(
        self,
        login: int,
        password: str,
        server: str,
    ) -> bool:
        """
        Connect to a specific MT5 trading account.
        """

        with self._lock:
            was_auto_reconnect = self._auto_reconnect
            connected = self.client.connect(
                login=login,
                password=password,
                server=server,
            )

            if not connected:
                if not was_auto_reconnect:
                    self._clear_state()
                self.last_error = str(self.client.last_error())
                return False

            account = self.client.account_info()

            if account is None or account.login != login or account.server != server:
                self.client.disconnect()
                if not was_auto_reconnect:
                    self._clear_state()
                self.last_error = "MT5 connected to an unexpected account."
                return False

            self.login = account.login
            self.server = account.server
            self.name = account.name
            self.last_error = None
            self._password = password
            self._auto_reconnect = True
            return True

    def _clear_state(self) -> None:
        self.login = None
        self.server = None
        self.name = None

    def disconnect(self) -> dict:
        """
        Disconnect the currently connected MT5 account.
        """

        with self._lock:
            self.client.disconnect()
            self._clear_state()
            self._password = None
            self._auto_reconnect = False

        return {
            "success": True,
            "message": "Disconnected successfully.",
        }

    async def start_monitor(self) -> None:
        if self._monitor_task is None:
            self._monitor_task = asyncio.create_task(self._monitor())

    async def stop_monitor(self) -> None:
        task = self._monitor_task
        self._monitor_task = None
        if task is not None:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task

    async def _monitor(self) -> None:
        from app.core.config import settings

        while True:
            await asyncio.sleep(settings.MT5_RECONNECT_INTERVAL)
            if not self._auto_reconnect or not self.login or not self._password:
                continue

            connected = await asyncio.to_thread(self.is_connected)
            if connected:
                continue

            login = self.login
            password = self._password
            server = self.server
            await asyncio.to_thread(self.connect, login, password, server)

    def is_connected(self) -> bool:
        """
        Check whether the current MT5 connection is healthy.
        """

        with self._lock:
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


connection_service = ConnectionService()