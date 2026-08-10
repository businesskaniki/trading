from app.broker.mt5_client import MT5Client


class ConnectionService:

    def __init__(self):
        self.client = MT5Client()

    def connect(
        self,
        login: int,
        password: str,
        server: str,
    ):

        return self.client.connect(
            login=login,
            password=password,
            server=server,
        )

    def disconnect(self):

        self.client.disconnect()

        return {
            "message": "Disconnected successfully."
        }

    def status(self):

        return {
            "connected": self.client.is_connected()
        }

    def version(self):

        return self.client.version()

    def terminal_info(self):

        return self.client.terminal_info()