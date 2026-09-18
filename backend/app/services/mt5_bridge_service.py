from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import httpx

from app.core.config import settings


class MT5BridgeError(Exception):
    """Raised when communication with the MT5 bridge fails."""

    pass


class MT5BridgeService:
    """
    AQE-side client for communicating with the MT5 bridge.

    This service does not interact with MetaTrader5 directly.
    It communicates with the MT5 bridge exclusively over HTTP.

    The bridge owns the MT5 connection and broker interaction.
    AQE owns the application-level market-data abstraction.
    """

    def __init__(
        self,
        bridge_url: str | None = None,
        timeout: float = 10.0,
    ) -> None:
        self.bridge_url = (bridge_url or settings.MT5_BRIDGE_URL).rstrip("/")
        self.bridge_token = settings.MT5_BRIDGE_TOKEN

        self.timeout = timeout

    # ------------------------------------------------------------------
    # CONNECTION
    # ------------------------------------------------------------------

    async def connect(
        self,
        login: int,
        password: str,
        server: str,
    ) -> dict[str, Any]:
        """
        Connect the MT5 bridge to a broker account.

        Credentials are supplied at runtime by AQE and are not stored
        inside the bridge configuration.
        """

        payload = {
            "login": login,
            "password": password,
            "server": server,
        }

        response = await self._request(
            method="POST",
            path="/connection/connect",
            json=payload,
        )

        if not isinstance(response, dict):
            raise MT5BridgeError("MT5 bridge returned an invalid connection response.")

        return response

    async def disconnect(self) -> dict[str, Any]:
        """Disconnect the active MT5 bridge session."""

        response = await self._request(
            method="POST",
            path="/connection/disconnect",
        )

        if not isinstance(response, dict):
            raise MT5BridgeError("MT5 bridge returned an invalid disconnect response.")

        return response

    async def status(self) -> dict[str, Any]:
        """Return the current MT5 bridge connection status."""

        response = await self._request(
            method="GET",
            path="/connection/status",
        )

        if not isinstance(response, dict):
            raise MT5BridgeError("MT5 bridge returned an invalid status response.")

        return response

    # ------------------------------------------------------------------
    # ACCOUNT
    # ------------------------------------------------------------------

    async def get_account(self) -> dict[str, Any]:
        """Retrieve account information from the MT5 bridge."""

        response = await self._request(
            method="GET",
            path="/account",
        )

        if not isinstance(response, dict):
            raise MT5BridgeError("MT5 bridge returned an invalid account response.")

        return response

    # ------------------------------------------------------------------
    # SYMBOLS
    # ------------------------------------------------------------------

    async def get_symbols(self) -> list[dict[str, Any]]:
        """Retrieve available symbols from the MT5 bridge."""

        response = await self._request(
            method="GET",
            path="/symbols",
        )

        if not isinstance(response, list):
            raise MT5BridgeError("MT5 bridge returned an invalid symbols response.")

        for index, item in enumerate(response):
            if not isinstance(item, dict):
                raise MT5BridgeError(
                    f"MT5 bridge returned an invalid symbol " f"at index {index}."
                )

        return response

    # ------------------------------------------------------------------
    # MARKET DATA - TICKS
    # ------------------------------------------------------------------

    async def get_tick(
        self,
        symbol: str,
    ) -> dict[str, Any]:
        """
        Retrieve the current broker tick for a symbol.

        Bridge endpoint:

            GET /market-data/tick/{symbol}
        """

        symbol = self._validate_symbol(symbol)

        response = await self._request(
            method="GET",
            path=f"/market-data/tick/{symbol}",
        )

        if not isinstance(response, dict):
            raise MT5BridgeError(
                f"MT5 bridge returned an invalid tick response " f"for {symbol}."
            )

        return response

    async def get_latest_tick(
        self,
        symbol: str,
    ) -> dict[str, Any]:
        """
        Retrieve the latest tick produced by the bridge's
        market-data streaming service.

        Bridge endpoint:

            GET /market-data/latest/{symbol}
        """

        symbol = self._validate_symbol(symbol)

        response = await self._request(
            method="GET",
            path=f"/market-data/latest/{symbol}",
        )

        if not isinstance(response, dict):
            raise MT5BridgeError(
                f"MT5 bridge returned an invalid latest tick " f"response for {symbol}."
            )

        return response

    # ------------------------------------------------------------------
    # MARKET DATA - SUBSCRIPTIONS
    # ------------------------------------------------------------------

    async def subscribe_symbol(
        self,
        symbol: str,
    ) -> dict[str, Any]:
        """
        Subscribe the MT5 bridge market-data service to a symbol.

        Bridge endpoint:

            POST /market-data/subscribe/{symbol}

        Symbol casing is intentionally preserved because MT5 broker
        symbols can be broker-specific, for example:

            XAUUSD.s
            EURUSD.s
            BTCUSDm
        """

        symbol = self._validate_symbol(symbol)

        response = await self._request(
            method="POST",
            path=f"/market-data/subscribe/{symbol}",
        )

        if not isinstance(response, dict):
            raise MT5BridgeError(
                f"MT5 bridge returned an invalid subscription "
                f"response for {symbol}."
            )

        return response

    async def unsubscribe_symbol(
        self,
        symbol: str,
    ) -> dict[str, Any]:
        """
        Remove a symbol from the bridge market-data subscription set.

        Bridge endpoint:

            DELETE /market-data/subscribe/{symbol}
        """

        symbol = self._validate_symbol(symbol)

        response = await self._request(
            method="DELETE",
            path=f"/market-data/subscribe/{symbol}",
        )

        if not isinstance(response, dict):
            raise MT5BridgeError(
                f"MT5 bridge returned an invalid unsubscribe " f"response for {symbol}."
            )

        return response

    async def get_subscriptions(self) -> dict[str, Any]:
        """
        Retrieve the bridge's current market-data subscriptions.

        Bridge endpoint:

            GET /market-data/subscriptions
        """

        response = await self._request(
            method="GET",
            path="/market-data/subscriptions",
        )

        if not isinstance(response, dict):
            raise MT5BridgeError(
                "MT5 bridge returned an invalid subscriptions response."
            )

        return response

    # ------------------------------------------------------------------
    # MARKET DATA - CANDLES
    # ------------------------------------------------------------------

    async def get_candles(
        self,
        symbol: str,
        timeframe: str = "M15",
        count: int | None = 200,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> list[dict[str, Any]]:
        """
        Retrieve historical candles from the MT5 bridge.

        Bridge endpoint:

            GET /market-data/candles/{symbol}

        Supported query parameters:

            timeframe=M15
            count=200
            start=2026-09-08T10:00:00Z
            end=2026-09-08T12:00:00Z

        Two retrieval modes are supported:

        1. Initial synchronization:

            count=200

           Retrieves the latest number of candles.

        2. Incremental synchronization:

            start=<timestamp>
            end=<timestamp>

           Retrieves candles for a specific historical range.

        `start` and `end` take precedence over `count`.

        The broker-specific symbol name is preserved exactly.
        """

        symbol = self._validate_symbol(symbol)

        timeframe = timeframe.strip().upper()

        if not timeframe:
            raise MT5BridgeError("Timeframe cannot be empty.")

        if count is not None and count <= 0:
            raise MT5BridgeError("Candle count must be greater than zero.")

        # --------------------------------------------------------------
        # Normalize timestamps to UTC.
        # --------------------------------------------------------------

        start = self._normalize_datetime(
            start,
            field_name="start",
        )

        end = self._normalize_datetime(
            end,
            field_name="end",
        )

        # --------------------------------------------------------------
        # Validate range.
        # --------------------------------------------------------------

        if start is not None and end is not None and start > end:
            raise MT5BridgeError(
                "Candle start time must be earlier than or equal to " "the end time."
            )

        # --------------------------------------------------------------
        # Build query parameters.
        # --------------------------------------------------------------

        params: dict[str, Any] = {
            "timeframe": timeframe,
        }

        if start is not None:
            params["start"] = start.isoformat()

        if end is not None:
            params["end"] = end.isoformat()

        # Only send count when no range is being requested.
        #
        # This preserves the semantics of:
        #
        #     count=200
        #
        # for initial synchronization.
        #
        # Incremental synchronization instead uses:
        #
        #     start=...
        #     end=...
        #
        if start is None and end is None:
            if count is None:
                count = 200

            params["count"] = count

        response = await self._request(
            method="GET",
            path=f"/market-data/candles/{symbol}",
            params=params,
        )

        # --------------------------------------------------------------
        # Normalize bridge response envelope.
        # --------------------------------------------------------------

        # The bridge returns:
        #
        # {
        #     "symbol": "XAUUSD.s",
        #     "timeframe": "M15",
        #     "count": 200,
        #     "candles": [...]
        # }
        #
        # Normalize this transport envelope here so the AQE market
        # layer receives only the candle collection.

        if isinstance(response, dict):
            candles = response.get("candles")

            if not isinstance(candles, list):
                raise MT5BridgeError(
                    f"MT5 bridge returned an invalid candles " f"response for {symbol}."
                )

            for index, candle in enumerate(candles):
                if not isinstance(candle, dict):
                    raise MT5BridgeError(
                        f"MT5 bridge returned an invalid candle "
                        f"at index {index} for {symbol}."
                    )

            return candles

        # Support a direct list response as well.
        #
        # This makes the service tolerant of a future bridge
        # response change.

        if isinstance(response, list):
            for index, candle in enumerate(response):
                if not isinstance(candle, dict):
                    raise MT5BridgeError(
                        f"MT5 bridge returned an invalid candle "
                        f"at index {index} for {symbol}."
                    )

            return response

        raise MT5BridgeError(
            f"MT5 bridge returned an invalid candles response " f"for {symbol}."
        )

    # ------------------------------------------------------------------
    # HTTP TRANSPORT
    # ------------------------------------------------------------------

    async def _request(
        self,
        method: str,
        path: str,
        **kwargs: Any,
    ) -> Any:
        """
        Execute an HTTP request against the MT5 bridge.

        All bridge communication passes through this method so that
        timeout, connection, HTTP, and response parsing errors are
        handled consistently.
        """

        url = f"{self.bridge_url}{path}"

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.request(
                    method=method,
                    url=url,
                    headers={"X-Bridge-Token": self.bridge_token},
                    **kwargs,
                )

        except httpx.TimeoutException as exc:
            raise MT5BridgeError("MT5 bridge request timed out.") from exc

        except httpx.ConnectError as exc:
            raise MT5BridgeError("Unable to connect to the MT5 bridge.") from exc

        except httpx.RequestError as exc:
            raise MT5BridgeError("MT5 bridge request failed.") from exc

        try:
            response_data = response.json()

        except ValueError:
            response_data = {
                "detail": response.text,
            }

        if response.is_error:
            detail = self._extract_error_detail(response_data)

            raise MT5BridgeError(
                f"MT5 bridge returned HTTP " f"{response.status_code}: {detail}"
            )

        return response_data

    # ------------------------------------------------------------------
    # VALIDATION / ERROR HANDLING
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_symbol(symbol: str) -> str:
        """
        Validate a broker symbol while preserving its exact casing.
        """

        if not isinstance(symbol, str):
            raise MT5BridgeError("Symbol must be a string.")

        symbol = symbol.strip()

        if not symbol:
            raise MT5BridgeError("Symbol cannot be empty.")

        return symbol

    @staticmethod
    def _normalize_datetime(
        value: datetime | None,
        field_name: str,
    ) -> datetime | None:
        """
        Normalize a datetime to timezone-aware UTC.

        Naive datetimes are interpreted as UTC.
        """

        if value is None:
            return None

        if not isinstance(value, datetime):
            raise MT5BridgeError(f"{field_name} must be a datetime.")

        if value.tzinfo is None:
            return value.replace(
                tzinfo=timezone.utc,
            )

        return value.astimezone(
            timezone.utc,
        )

    @staticmethod
    def _extract_error_detail(
        data: Any,
    ) -> str:
        """
        Extract a useful error message from a bridge response.
        """

        if isinstance(data, dict):
            detail = data.get("detail")

            if isinstance(detail, str):
                return detail

            if isinstance(detail, dict):
                message = detail.get("message")

                if isinstance(message, str):
                    return message

                return str(detail)

            if detail is not None:
                return str(detail)

            message = data.get("message")

            if isinstance(message, str):
                return message

        if isinstance(data, list):
            return str(data)

        return "Unknown MT5 bridge error."
