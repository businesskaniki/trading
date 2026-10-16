"""Exchange-session helpers for historical market-data validation."""

from __future__ import annotations

from datetime import datetime, timezone
from functools import lru_cache
from typing import Any

UTC = timezone.utc


def is_us_stocks_asset_class(asset_class: Any) -> bool:
    """Return whether the asset class is STOCKS."""

    value = getattr(asset_class, "value", asset_class)

    return str(value or "").strip().upper() == "STOCKS"


def _as_utc(value: datetime) -> datetime:
    """Normalize a datetime or pandas Timestamp to UTC."""

    if not isinstance(value, datetime) and hasattr(value, "to_pydatetime"):
        value = value.to_pydatetime()

    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)

    return value.astimezone(UTC)


@lru_cache(maxsize=1)
def _us_equity_calendar():
    """Return the cached US equity exchange calendar."""

    import pandas_market_calendars as mcal

    # NYSE is used as the current US-equity holiday and regular-session
    # calendar for this universe, which includes AAPL and ABNB.
    return mcal.get_calendar("NYSE")


def us_equity_session_overlaps(
    start: datetime,
    end: datetime,
) -> bool:
    """
    Return whether a US equity regular trading session overlaps [start, end).

    The interval is start-inclusive and end-exclusive. This function
    identifies scheduled regular exchange sessions; it does not claim
    to model broker-specific CFD extended-hours trading.
    """

    start_utc = _as_utc(start)
    end_utc = _as_utc(end)

    if start_utc >= end_utc:
        return False

    calendar = _us_equity_calendar()

    schedule = calendar.schedule(
        start_date=start_utc.date().isoformat(),
        end_date=end_utc.date().isoformat(),
    )

    if schedule.empty:
        return False

    for market_open, market_close in schedule[
        ["market_open", "market_close"]
    ].itertuples(index=False, name=None):
        market_open_utc = _as_utc(market_open)
        market_close_utc = _as_utc(market_close)

        if market_open_utc < end_utc and market_close_utc > start_utc:
            return True

    return False
