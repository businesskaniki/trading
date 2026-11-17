"""Calculate required margin through MT5 without submitting an order."""

from __future__ import annotations

import math
from decimal import Decimal

import MetaTrader5 as mt5

from app.broker.mt5_lock import mt5_synchronized
from app.broker.orders import OrderBroker
from app.schemas.margin import (
    MarginCalculationRequest,
    MarginCalculationResponse,
)


class MarginCalculationService:
    """Perform a serialized, read-only MT5 order margin calculation."""

    def __init__(self, broker: OrderBroker | None = None) -> None:
        self.broker = broker or OrderBroker()

    @mt5_synchronized
    def calculate(
        self,
        request: MarginCalculationRequest,
    ) -> MarginCalculationResponse:
        """Return MT5's margin estimate for a proposed BUY/SELL request.

        The lock covers symbol lookup/selection and ``order_calc_margin`` as
        one logical MT5 operation. This method never calls order_check or
        order_send and cannot submit an order.
        """

        symbol = request.symbol.strip()
        volume = float(request.volume)
        price = float(request.price)
        side = request.side

        if not symbol:
            raise ValueError("Margin calculation symbol cannot be empty.")
        if not math.isfinite(volume) or volume <= 0:
            raise ValueError("Margin calculation volume must be finite and positive.")
        if not math.isfinite(price) or price <= 0:
            raise ValueError("Margin calculation price must be finite and positive.")

        symbol_info = self._ensure_symbol_ready(symbol)
        action = mt5.ORDER_TYPE_BUY if side == "BUY" else mt5.ORDER_TYPE_SELL

        result = mt5.order_calc_margin(
            action,
            symbol,
            volume,
            price,
        )

        if result is None:
            raise RuntimeError(
                "MT5 order_calc_margin returned no result. "
                f"symbol={symbol!r}, side={side}, volume={volume}, price={price}, "
                f"terminal_error={self.broker.last_error()!r}"
            )

        required_margin = float(result)
        if not math.isfinite(required_margin) or required_margin < 0:
            raise RuntimeError(
                "MT5 order_calc_margin returned an invalid margin amount. "
                f"symbol={symbol!r}, result={result!r}"
            )

        account_info = mt5.account_info()
        account_currency = (
            getattr(account_info, "currency", None)
            if account_info is not None
            else None
        )

        # A zero margin amount is retained as returned by MT5. It is not
        # rewritten or treated as an API failure; MarginRiskRule will compare
        # the returned amount with free margin.
        return MarginCalculationResponse(
            symbol=symbol,
            side=side,
            volume=Decimal(str(volume)),
            price=Decimal(str(price)),
            required_margin=Decimal(str(required_margin)),
            currency=account_currency,
        )

    def _ensure_symbol_ready(self, symbol: str):
        """Ensure the symbol exists and is selected in Market Watch."""

        symbol_info = self.broker.symbol_info(symbol)
        if symbol_info is None:
            raise RuntimeError(
                "MT5 symbol is unavailable for margin calculation. "
                f"symbol={symbol}; error={self.broker.last_error()!r}"
            )

        if not getattr(symbol_info, "visible", True):
            selected = self.broker.symbol_select(symbol, True)
            if not selected:
                raise RuntimeError(
                    "Unable to select MT5 symbol for margin calculation. "
                    f"symbol={symbol}; error={self.broker.last_error()!r}"
                )
            symbol_info = self.broker.symbol_info(symbol)
            if symbol_info is None:
                raise RuntimeError(
                    "MT5 symbol became unavailable after Market Watch selection. "
                    f"symbol={symbol}"
                )

        return symbol_info
