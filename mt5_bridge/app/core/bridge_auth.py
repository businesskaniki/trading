"""Shared-secret authentication between the AQE backend and the MT5 bridge.

This is NOT user authentication. It answers a narrower question: "is
this request actually coming from our backend?" User identity and
per-account ownership are already enforced on the backend side (see
backend/app/api/dependencies.py) before a request is ever made to the
bridge. Without this check, anyone who can reach the bridge's port
directly could call market-data or order endpoints - including
placing real trades - completely bypassing that.

Uses the bridge's existing MT5_BRIDGE_TOKEN setting (app.core.config)
rather than a separate secret - the bridge already enforced this
being configured via its own settings validator, so there was no
need to introduce a second value to keep in sync.
"""

from __future__ import annotations

import hmac

from fastapi import Header, HTTPException, status

from app.core.config import settings


async def verify_bridge_key(
    x_bridge_key: str = Header(
        default="",
        alias="X-Bridge-Key",
    ),
) -> None:
    if not x_bridge_key or not hmac.compare_digest(
        x_bridge_key,
        settings.MT5_BRIDGE_TOKEN,
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing bridge API key.",
        )