from __future__ import annotations

from typing import Any

import httpx


class MT5Client:
    """
    Lightweight HTTP client for the AQE MT5 Bridge.

    Responsibilities:
        - communicate with the MT5 Bridge;
        - attach the bridge authentication token;
        - serialize request payloads;
        - deserialize JSON responses;
        - surface HTTP/network failures to the MT5 adapter.

    This client deliberately contains no:
        - MT5 trading logic;
        - order mapping;
        - risk logic;
        - execution logic;
        - database logic;
        - strategy logic.
    """

    def __init__(
        self,
        bridge_url: str,
        bridge_token: str,
        timeout: float = 10.0,
    ) -> None:
        bridge_url = bridge_url.strip().rstrip("/")

        if not bridge_url:
            raise ValueError(
                "MT5 bridge URL cannot be empty.",
            )

        if timeout <= 0:
            raise ValueError(
                "MT5 bridge timeout must be greater than zero.",
            )

        self.bridge_url = bridge_url
        self.headers = {
            "X-Bridge-Token": bridge_token,
        }
        self.timeout = timeout

    # ==================================================================
    # INTERNAL REQUEST HELPER
    # ==================================================================

    async def _request(
        self,
        method: str,
        endpoint: str,
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
    ) -> Any:
        """
        Execute an HTTP request against the MT5 Bridge.

        HTTP errors, connection failures, timeouts, and invalid JSON are
        surfaced as RuntimeError so the MT5Adapter can translate them
        into the appropriate broker-layer exception.
        """

        endpoint = str(endpoint).strip()

        if not endpoint:
            raise RuntimeError(
                "MT5 Bridge endpoint cannot be empty.",
            )

        if not endpoint.startswith("/"):
            endpoint = f"/{endpoint}"

        url = f"{self.bridge_url}{endpoint}"

        try:
            async with httpx.AsyncClient(
                timeout=self.timeout,
            ) as client:
                response = await client.request(
                    method=method,
                    url=url,
                    params=params,
                    json=json,
                    headers=self.headers,
                )

            response.raise_for_status()

        except httpx.TimeoutException as exc:
            raise RuntimeError(
                f"MT5 Bridge request timed out: " f"{method} {endpoint}",
            ) from exc

        except httpx.ConnectError as exc:
            raise RuntimeError(
                f"Unable to connect to MT5 Bridge: " f"{method} {endpoint}",
            ) from exc

        except httpx.HTTPStatusError as exc:
            response = exc.response

            detail: str | None = None

            try:
                payload = response.json()

                if isinstance(payload, dict):
                    raw_detail = payload.get("detail")

                    if raw_detail is not None:
                        detail = str(raw_detail)

            except ValueError:
                detail = None

            if detail:
                raise RuntimeError(
                    f"MT5 Bridge returned HTTP "
                    f"{response.status_code} for "
                    f"{method} {endpoint}: {detail}",
                ) from exc

            raise RuntimeError(
                f"MT5 Bridge returned HTTP "
                f"{response.status_code} for "
                f"{method} {endpoint}.",
            ) from exc

        except httpx.RequestError as exc:
            raise RuntimeError(
                f"MT5 Bridge request failed: " f"{method} {endpoint}: {exc}",
            ) from exc

        try:
            return response.json()

        except ValueError as exc:
            raise RuntimeError(
                f"MT5 Bridge returned invalid JSON for " f"{method} {endpoint}.",
            ) from exc

    # ==================================================================
    # GET
    # ==================================================================

    async def get(
        self,
        endpoint: str,
        *,
        params: dict[str, Any] | None = None,
    ) -> Any:
        """
        Send a GET request to the MT5 Bridge.

        Example:

            await client.get(
                "/symbols/XAUUSD.s/candles",
                params={
                    "timeframe": "M15",
                    "count": 200,
                },
            )
        """

        return await self._request(
            "GET",
            endpoint,
            params=params,
        )

    # ==================================================================
    # POST
    # ==================================================================

    async def post(
        self,
        endpoint: str,
        data: dict[str, Any] | None = None,
        *,
        params: dict[str, Any] | None = None,
    ) -> Any:
        """
        Send a POST request to the MT5 Bridge.

        `data` is serialized as JSON.
        """

        return await self._request(
            "POST",
            endpoint,
            params=params,
            json=data,
        )

    # ==================================================================
    # PATCH
    # ==================================================================

    async def patch(
        self,
        endpoint: str,
        data: dict[str, Any] | None = None,
        *,
        params: dict[str, Any] | None = None,
    ) -> Any:
        """
        Send a PATCH request to the MT5 Bridge.

        Used primarily for broker-side position modifications such
        as stop-loss and take-profit changes.
        """

        return await self._request(
            "PATCH",
            endpoint,
            params=params,
            json=data,
        )
