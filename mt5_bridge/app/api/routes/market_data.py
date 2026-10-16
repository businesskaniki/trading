
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import MetaTrader5 as mt5
from fastapi import APIRouter, HTTPException, Query

from app.broker.market_data import MarketDataBroker
from app.broker.mt5_lock import mt5_synchronized
from app.schemas.market_data import MarketTick
from app.services.connection_service import connection_service
from app.services.market_data_service import market_data_service


router = APIRouter(
    prefix="/market-data",
    tags=["Market Data"],
)

broker = MarketDataBroker()


# MT5 Python integration errors associated with IPC and internal
# communication failures. In particular, -10004 means No IPC connection.
MT5_CONNECTION_ERROR_CODES = {
    -10001,
    -10002,
    -10003,
    -10004,
    -10005,
}


# =============================================================
# ERROR HELPERS
# =============================================================

def _last_mt5_error() -> Any:
    """Read the latest MT5 error defensively."""

    try:
        return mt5.last_error()
    except Exception:
        return None


def _is_connection_error(error: Any) -> bool:
    """Identify MT5 IPC and internal connection errors."""

    if isinstance(error, (tuple, list)) and error:
        try:
            if int(error[0]) in MT5_CONNECTION_ERROR_CODES:
                return True
        except (TypeError, ValueError, OverflowError):
            pass

    message = str(error).lower()

    return any(
        phrase in message
        for phrase in (
            "no ipc connection",
            "ipc connection",
            "internal fail connect",
            "internal fail send",
            "internal fail receive",
            "internal fail timeout",
        )
    )


def _connection_unavailable(
    *,
    operation: str,
    symbol: str | None = None,
    mt5_error: Any = None,
) -> HTTPException:
    """Build a consistent HTTP response for an unavailable MT5 session."""

    detail = f"MT5 connection unavailable while {operation}."

    if symbol:
        detail += f" Symbol: {symbol}."

    if mt5_error is not None:
        detail += f" MT5 error: {mt5_error}."

    return HTTPException(
        status_code=503,
        detail=detail,
        headers={"Retry-After": "5"},
    )


def _require_connection(
    *,
    operation: str,
    symbol: str | None = None,
) -> None:
    """
    Verify the intended MT5 account before processing a request.

    This runs outside MT5_API_LOCK because ConnectionService performs
    its own synchronized connection checks. Do not call this function
    from inside a function decorated with mt5_synchronized.
    """

    if connection_service.is_connected():
        return

    raise _connection_unavailable(
        operation=operation,
        symbol=symbol,
        mt5_error=_last_mt5_error(),
    )


def _raise_if_connection_failed(
    *,
    operation: str,
    symbol: str,
    error: Any,
    terminal_connected: bool,
) -> None:
    """
    Determine whether a failed data request is actually a connection
    failure. Must be called after the shared MT5 lock has been released.
    """

    if (
        _is_connection_error(error)
        or not terminal_connected
        or not connection_service.is_connected()
    ):
        raise _connection_unavailable(
            operation=operation,
            symbol=symbol,
            mt5_error=error,
        )


# =============================================================
# SYNCHRONIZED MT5 OPERATIONS
# =============================================================

@mt5_synchronized
def _retrieve_tick(
    symbol: str,
) -> tuple[Any, Any, bool, bool]:
    """
    Retrieve a tick and capture related state under one shared lock.

    Returns:
        tick, last_error, terminal_connected, symbol_exists

    Capturing the error before performing additional MT5 calls
    prevents terminal inspection from overwriting the useful error.
    """

    tick = broker.get_tick(symbol)
    error = _last_mt5_error()

    terminal = mt5.terminal_info()
    terminal_connected = (
        terminal is not None
        and bool(getattr(terminal, "connected", False))
    )

    info = mt5.symbol_info(symbol)
    symbol_exists = info is not None

    return tick, error, terminal_connected, symbol_exists


@mt5_synchronized
def _prepare_symbol_subscription(
    symbol: str,
) -> tuple[str, Any]:
    """
    Validate and select a symbol while holding the shared MT5 lock.

    Returns:
        ("ok", None)
        ("connection", error)
        ("not_found", error)
        ("selection_failed", error)

    This function never invokes ConnectionService while holding
    MT5_API_LOCK, avoiding lock-order deadlocks.
    """

    terminal = mt5.terminal_info()
    error = _last_mt5_error()

    if terminal is None or not bool(
        getattr(terminal, "connected", False)
    ):
        return "connection", error

    account = mt5.account_info()
    error = _last_mt5_error()

    if account is None:
        return "connection", error

    info = mt5.symbol_info(symbol)
    error = _last_mt5_error()

    if info is None:
        if _is_connection_error(error):
            return "connection", error

        return "not_found", error

    if not bool(getattr(info, "visible", False)):
        selected = mt5.symbol_select(symbol, True)
        error = _last_mt5_error()

        if not selected:
            if _is_connection_error(error):
                return "connection", error

            return "selection_failed", error

    return "ok", None


@mt5_synchronized
def _retrieve_candles(
    *,
    symbol: str,
    timeframe: int,
    count: int | None,
    start: datetime | None,
    end: datetime | None,
) -> tuple[Any, Any, bool, bool]:
    """
    Retrieve candles and snapshot connection diagnostics under one lock.

    Returns:
        rates, last_error, terminal_connected, symbol_exists
    """

    rates = broker.get_candles(
        symbol=symbol,
        timeframe=timeframe,
        count=count,
        start=start,
        end=end,
    )

    error = _last_mt5_error()

    terminal = mt5.terminal_info()
    terminal_connected = (
        terminal is not None
        and bool(getattr(terminal, "connected", False))
    )

    info = mt5.symbol_info(symbol)
    symbol_exists = info is not None

    return rates, error, terminal_connected, symbol_exists


# =============================================================
# LATEST TICK
# =============================================================

@router.get(
    "/tick/{symbol}",
    response_model=MarketTick,
)
def get_tick(symbol: str):
    """Return the latest market tick directly from MT5."""

    symbol = symbol.strip()

    if not symbol:
        raise HTTPException(
            status_code=400,
            detail="Symbol cannot be empty.",
        )

    _require_connection(
        operation="retrieving a market tick",
        symbol=symbol,
    )

    try:
        tick, error, terminal_connected, symbol_exists = (
            _retrieve_tick(symbol)
        )

    except Exception as exc:
        logger_exception = exc

        # The synchronized operation has exited, so checking the
        # connection service here cannot deadlock with its MT5 lock.
        if not connection_service.is_connected():
            raise _connection_unavailable(
                operation="retrieving a market tick",
                symbol=symbol,
                mt5_error=_last_mt5_error(),
            ) from logger_exception

        raise HTTPException(
            status_code=502,
            detail=f"MT5 failed to retrieve a tick for {symbol}.",
        ) from logger_exception

    if tick is None:
        _raise_if_connection_failed(
            operation="retrieving a market tick",
            symbol=symbol,
            error=error,
            terminal_connected=terminal_connected,
        )

        if not symbol_exists:
            raise HTTPException(
                status_code=404,
                detail=f"Symbol not found: {symbol}",
            )

        raise HTTPException(
            status_code=404,
            detail=f"No market tick available for {symbol}.",
        )

    try:
        data = tick._asdict()

        return MarketTick(
            symbol=symbol,
            timestamp=int(data.get("time", 0)),
            bid=float(data.get("bid", 0.0)),
            ask=float(data.get("ask", 0.0)),
            last=float(data.get("last", 0.0)),
            volume=int(data.get("volume", 0)),
            volume_real=float(data.get("volume_real", 0.0)),
        )

    except (AttributeError, TypeError, ValueError, OverflowError) as exc:
        raise HTTPException(
            status_code=502,
            detail=f"MT5 returned invalid tick data for {symbol}.",
        ) from exc


# =============================================================
# SUBSCRIPTIONS
# =============================================================

@router.post("/subscribe/{symbol}")
def subscribe_symbol(symbol: str):
    """Subscribe a broker symbol for continuous market-data collection."""

    symbol = symbol.strip()

    if not symbol:
        raise HTTPException(
            status_code=400,
            detail="Symbol cannot be empty.",
        )

    _require_connection(
        operation="subscribing to market data",
        symbol=symbol,
    )

    try:
        result, error = _prepare_symbol_subscription(symbol)
    except Exception as exc:
        if not connection_service.is_connected():
            raise _connection_unavailable(
                operation="subscribing to market data",
                symbol=symbol,
                mt5_error=_last_mt5_error(),
            ) from exc

        raise HTTPException(
            status_code=502,
            detail=f"Failed to prepare market-data subscription for {symbol}.",
        ) from exc

    if result == "connection":
        raise _connection_unavailable(
            operation="subscribing to market data",
            symbol=symbol,
            mt5_error=error,
        )

    if result == "not_found":
        raise HTTPException(
            status_code=404,
            detail=f"Symbol not found: {symbol}",
        )

    if result == "selection_failed":
        raise HTTPException(
            status_code=502,
            detail=f"Unable to select MT5 symbol {symbol}: {error}",
        )

    market_data_service.subscribe(symbol)

    return {
        "success": True,
        "symbol": symbol,
        "subscribed": True,
        "subscriptions": market_data_service.subscriptions(),
    }


@router.delete("/subscribe/{symbol}")
def unsubscribe_symbol(symbol: str):
    """Remove a symbol from the live market-data subscription set."""

    symbol = symbol.strip()

    if not symbol:
        raise HTTPException(
            status_code=400,
            detail="Symbol cannot be empty.",
        )

    market_data_service.unsubscribe(symbol)

    return {
        "success": True,
        "symbol": symbol,
        "subscribed": False,
        "subscriptions": market_data_service.subscriptions(),
    }


@router.get("/subscriptions")
def get_subscriptions():
    """Return market-data service and Redis publication diagnostics."""

    last_error_at = market_data_service.last_publish_error_at
    last_success_at = market_data_service.last_publish_success_at

    return {
        "running": market_data_service.running,
        "subscriptions": market_data_service.subscriptions(),
        "last_publish_error": market_data_service.last_publish_error,
        "last_publish_error_at": (
            last_error_at.isoformat()
            if last_error_at is not None
            else None
        ),
        "last_publish_success_at": (
            last_success_at.isoformat()
            if last_success_at is not None
            else None
        ),
    }


@router.get(
    "/latest/{symbol}",
    response_model=MarketTick,
)
def get_latest_tick(symbol: str):
    """
    Return the most recently collected tick.

    This is cached data. It may be stale if MT5 has disconnected.
    """

    symbol = symbol.strip()

    if not symbol:
        raise HTTPException(
            status_code=400,
            detail="Symbol cannot be empty.",
        )

    tick = market_data_service.last_tick(symbol)

    if tick is None:
        raise HTTPException(
            status_code=404,
            detail=f"No streamed tick available for {symbol}.",
        )

    return tick


# =============================================================
# HISTORICAL CANDLES
# =============================================================

@router.get("/candles/{symbol}")
def get_candles(
    symbol: str,
    timeframe: str = Query(
        default="M1",
        description="MT5 timeframe: M1, M5, M15, M30, H1, H4, D1",
    ),
    count: int | None = Query(
        default=None,
        ge=1,
        le=5000,
        description=(
            "Maximum number of candles for latest-N retrieval. "
            "For date-range retrieval, the broker may return the full range."
        ),
    ),
    start: datetime | None = Query(
        default=None,
        description="Inclusive UTC start datetime.",
    ),
    end: datetime | None = Query(
        default=None,
        description="Inclusive UTC end datetime.",
    ),
):
    """
    Retrieve historical OHLCV candles from MT5.

    Connection failures return HTTP 503.
    Missing symbols return HTTP 404.
    A valid empty candle range returns HTTP 200 with an empty list.
    Other MT5 retrieval failures return HTTP 502.
    """

    symbol = symbol.strip()
    timeframe = timeframe.upper().strip()

    if not symbol:
        raise HTTPException(
            status_code=400,
            detail="Symbol cannot be empty.",
        )

    timeframe_map = {
        name: getattr(mt5, f"TIMEFRAME_{name}")
        for name in (
            "M1", "M2", "M3", "M4", "M5", "M6",
            "M10", "M12", "M15", "M20", "M30",
            "H1", "H2", "H3", "H4", "H6", "H8",
            "H12", "D1", "W1", "MN1",
        )
        if hasattr(mt5, f"TIMEFRAME_{name}")
    }

    mt5_timeframe = timeframe_map.get(timeframe)

    if mt5_timeframe is None:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported timeframe: {timeframe}",
        )

    # Normalize request datetimes to UTC.
    if start is not None:
        if start.tzinfo is None:
            start = start.replace(tzinfo=timezone.utc)
        else:
            start = start.astimezone(timezone.utc)

    if end is not None:
        if end.tzinfo is None:
            end = end.replace(tzinfo=timezone.utc)
        else:
            end = end.astimezone(timezone.utc)

    if start is not None and end is not None and start > end:
        raise HTTPException(
            status_code=400,
            detail="start must be earlier than or equal to end.",
        )

    _require_connection(
        operation="retrieving historical candles",
        symbol=symbol,
    )

    try:
        rates, error, terminal_connected, symbol_exists = (
            _retrieve_candles(
                symbol=symbol,
                timeframe=mt5_timeframe,
                count=count,
                start=start,
                end=end,
            )
        )

    except Exception as exc:
        if not connection_service.is_connected():
            raise _connection_unavailable(
                operation="retrieving historical candles",
                symbol=symbol,
                mt5_error=_last_mt5_error(),
            ) from exc

        raise HTTPException(
            status_code=502,
            detail=f"MT5 failed to retrieve candles for {symbol}.",
        ) from exc

    if rates is None:
        _raise_if_connection_failed(
            operation="retrieving historical candles",
            symbol=symbol,
            error=error,
            terminal_connected=terminal_connected,
        )

        if not symbol_exists:
            raise HTTPException(
                status_code=404,
                detail=f"Symbol not found: {symbol}",
            )

        raise HTTPException(
            status_code=502,
            detail=(
                f"MT5 failed to retrieve candles for {symbol}. "
                f"MT5 error: {error}"
            ),
        )

    candles = []

    for rate in rates:
        candles.append(
            {
                "time": int(rate["time"]),
                "open": float(rate["open"]),
                "high": float(rate["high"]),
                "low": float(rate["low"]),
                "close": float(rate["close"]),
                "volume": int(rate["tick_volume"]),
                "spread": int(rate["spread"]),
            }
        )

    return {
        "symbol": symbol,
        "timeframe": timeframe,
        "count": len(candles),
        "start": start.isoformat() if start is not None else None,
        "end": end.isoformat() if end is not None else None,
        "candles": candles,
    }
