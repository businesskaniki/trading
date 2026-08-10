import httpx


class MT5Client:

    def __init__(
        self,
        bridge_url: str,
        timeout: float = 10.0,
    ):
        self.bridge_url = bridge_url.rstrip("/")
        self.timeout = timeout

    async def get(self, endpoint: str):

        async with httpx.AsyncClient(
            timeout=self.timeout
        ) as client:

            response = await client.get(
                f"{self.bridge_url}{endpoint}"
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
            )

            response.raise_for_status()

            return response.json()