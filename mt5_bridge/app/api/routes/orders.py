from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, status

from app.schemas.margin import (
    MarginCalculationRequest,
    MarginCalculationResponse,
)
from app.schemas.order import OrderRequest, OrderResponse
from app.services.margin_calculation_service import MarginCalculationService
from app.services.order_service import OrderService

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/orders",
    tags=["Orders"],
)

service = OrderService()
margin_calculation_service = MarginCalculationService()


@router.post(
    "",
    response_model=OrderResponse,
    status_code=status.HTTP_200_OK,
    summary="Submit a market order",
    description=(
        "Returns the broker outcome in OrderResponse. REJECTED, UNKNOWN, "
        "NOT_SUBMITTED, PLACED, PARTIALLY_FILLED, and FILLED are response "
        "outcomes; they are not converted into HTTP errors merely because "
        "the broker did not confirm a complete fill."
    ),
)
def create_order(
    request: OrderRequest,
) -> OrderResponse:
    """Submit a market order and preserve the service's classified outcome.

    OrderService is responsible for classifying broker outcomes. A normal
    OrderResponse—including REJECTED or UNKNOWN—must be returned as-is so
    callers can distinguish a known rejection from an uncertain submission.
    Only an exception that escapes OrderService becomes an HTTP gateway error.
    """
    try:
        return service.send_order(request.model_dump())

    except HTTPException:
        # Preserve deliberate HTTP errors if the service starts raising them.
        raise

    except Exception as exc:
        logger.exception(
            "MT5 market order handler failed "
            "for symbol=%s volume=%s order_type=%s",
            request.symbol,
            request.volume,
            request.order_type,
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=(
                "Unable to obtain a classified result for the market order. "
                "Check the order and broker history before retrying."
            ),
        ) from exc


@router.get(
    "",
    response_model=list[dict[str, Any]],
    summary="List active broker orders",
)
def list_orders() -> list[dict[str, Any]]:
    """Return active/pending broker-order snapshots."""
    try:
        return service.list_orders()

    except HTTPException:
        raise

    except Exception as exc:
        logger.exception("Failed to retrieve active MT5 orders.")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Unable to retrieve active broker orders.",
        ) from exc


@router.post(
    "/pending",
    response_model=OrderResponse,
    status_code=status.HTTP_200_OK,
    summary="Submit a pending order",
    description=(
        "Returns PLACED when the broker confirms placement without a fill, "
        "and FILLED or PARTIALLY_FILLED only when the service has sufficient "
        "execution evidence."
    ),
)
def create_pending_order(
    request: OrderRequest,
) -> OrderResponse:
    """Submit a pending order and preserve the classified broker outcome."""
    try:
        return service.create_pending_order(
            symbol=request.symbol,
            volume=request.volume,
            order_type=request.order_type,
            price=request.price,
            sl=request.sl,
            tp=request.tp,
            deviation=request.deviation,
            magic=request.magic,
            comment=request.comment,
        )

    except HTTPException:
        raise

    except Exception as exc:
        logger.exception(
            "MT5 pending order handler failed "
            "for symbol=%s volume=%s order_type=%s",
            request.symbol,
            request.volume,
            request.order_type,
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=(
                "Unable to obtain a classified result for the pending order. "
                "Check the order and broker history before retrying."
            ),
        ) from exc


@router.post(
    "/margin",
    response_model=MarginCalculationResponse,
    status_code=status.HTTP_200_OK,
    summary="Calculate required margin without submitting an order",
    description=(
        "Calls MT5 order_calc_margin for a proposed BUY/SELL. "
        "This endpoint does not call order_check or order_send."
    ),
)
def calculate_order_margin(
    request: MarginCalculationRequest,
) -> MarginCalculationResponse:
    """Return MT5's margin estimate for the proposed trade."""
    try:
        return margin_calculation_service.calculate(request)
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception(
            "MT5 margin calculation failed: symbol=%s side=%s volume=%s",
            request.symbol,
            request.side,
            request.volume,
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=(
                "MT5 could not calculate the required margin. "
                "The trade must not be approved or submitted."
            ),
        ) from exc