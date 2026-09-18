import httpx


class MT5Client:

    def __init__(
        self,
        bridge_url: str,
        bridge_token: str,
        timeout: float = 10.0,
    ):
        self.bridge_url = bridge_url.rstrip("/")
        self.headers = {"X-Bridge-Token": bridge_token}
        self.timeout = timeout

    async def get(self, endpoint: str):

        async with httpx.AsyncClient(
            timeout=self.timeout
        ) as client:

            response = await client.get(
                f"{self.bridge_url}{endpoint}",
                headers=self.headers,
            )

            response.raise_for_status()

            return response.json()

    async def post(
        self,
        endpoint: str,
        data: dict | None = None,
    ):

        async with httpx.AsyncClient(
            timeout=self.timeout
        ) as client:

            response = await client.post(
                f"{self.bridge_url}{endpoint}",
                json=data,
                headers=self.headers,
            )

            response.raise_for_status()

            return response.json()