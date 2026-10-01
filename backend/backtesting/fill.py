"""Deterministic order-fill simulation for AQE backtesting."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID, uuid4

from app.schemas.execution import (
    ExecutionOrder,
    OrderSide,
    OrderType,
)

from .market import BacktestMarket

# ======================================================================
# ERRORS
# ======================================================================


class BacktestFillError(Exception):
    """Base exception for simulated fill failures."""


# ======================================================================
# ENUMS
# ======================================================================


class FillStatus(StrEnum):
    """Final state of an attempted order fill."""

    FILLED = "FILLED"
    NOT_FILLED = "NOT_FILLED"


class FillReason(StrEnum):
    """Reason associated with the resulting fill state."""

    MARKET = "MARKET"
    LIMIT_TRIGGERED = "LIMIT_TRIGGERED"
    STOP_TRIGGERED = "STOP_TRIGGERED"
    NOT_REACHED = "NOT_REACHED"


# ======================================================================
# FILL RESULT
# ======================================================================


@dataclass(frozen=True, slots=True)
class BacktestFill:
    """
    Result of one simulated order-fill attempt.

    A non-filled order still produces a BacktestFill record so the
    execution layer can preserve a deterministic audit trail.
    """

    fill_id: UUID
    order_id: UUID

    symbol: str

    side: OrderSide
    order_type: OrderType

    volume: Decimal
    price: Decimal

    timestamp: datetime

    status: FillStatus
    reason: FillReason

    commission: Decimal = Decimal("0")
    slippage: Decimal = Decimal("0")

    @property
    def filled(self) -> bool:
        """Return True when the order was successfully filled."""

        return self.status == FillStatus.FILLED


# ======================================================================
# FILL CONFIGURATION
# ======================================================================


@dataclass(frozen=True, slots=True)
class BacktestFillConfig:
    """
    Deterministic execution assumptions used by the fill engine.

    spread:
        Fixed total bid/ask spread in price units when explicit bid/ask
        values are not available.

    slippage:
        Adverse absolute price movement applied to MARKET and STOP
        executions.

    commission_per_volume:
        Commission charged per executed volume unit.

    market_fill_at:
        ``close``:
            Fill a MARKET order at the current candle close.

        ``open``:
            Fill a MARKET order at the current candle open.

        The default is ``close`` because AQE strategies evaluate the
        current candle before submitting MARKET orders. Using ``open``
        in that architecture would introduce look-ahead bias.

    limit_fill_at:
        Currently only ``price`` is supported.

        A triggered LIMIT order is filled at its requested limit price
        or at a better gap price when gap filling is enabled.

    stop_fill_at:
        Currently only ``price`` is supported.

        A triggered STOP order is filled at its stop price unless the
        market gaps through the stop.

    gap_fill:
        When enabled, pending LIMIT/STOP orders crossed by the candle
        opening price may receive the opening price where appropriate.
    """

    spread: Decimal = Decimal("0")
    slippage: Decimal = Decimal("0")
    commission_per_volume: Decimal = Decimal("0")

    # IMPORTANT:
    # Strategy evaluation occurs after the current candle is available.
    # Therefore MARKET orders default to the candle close rather than
    # the candle open to avoid look-ahead bias.
    market_fill_at: str = "close"

    limit_fill_at: str = "price"
    stop_fill_at: str = "price"

    gap_fill: bool = True

    def __post_init__(self) -> None:
        spread = self._to_finite_decimal(
            self.spread,
            "Spread",
        )

        slippage = self._to_finite_decimal(
            self.slippage,
            "Slippage",
        )

        commission = self._to_finite_decimal(
            self.commission_per_volume,
            "Commission",
        )

        if spread < Decimal("0"):
            raise ValueError(
                "Spread cannot be negative.",
            )

        if slippage < Decimal("0"):
            raise ValueError(
                "Slippage cannot be negative.",
            )

        if commission < Decimal("0"):
            raise ValueError(
                "Commission cannot be negative.",
            )

        object.__setattr__(
            self,
            "spread",
            spread,
        )

        object.__setattr__(
            self,
            "slippage",
            slippage,
        )

        object.__setattr__(
            self,
            "commission_per_volume",
            commission,
        )

        market_fill_at = (
            str(
                self.market_fill_at,
            )
            .strip()
            .lower()
        )

        if market_fill_at not in {
            "open",
            "close",
        }:
            raise ValueError(
                "market_fill_at must be 'open' or 'close'.",
            )

        object.__setattr__(
            self,
            "market_fill_at",
            market_fill_at,
        )

        limit_fill_at = (
            str(
                self.limit_fill_at,
            )
            .strip()
            .lower()
        )

        if limit_fill_at != "price":
            raise ValueError(
                "Only limit_fill_at='price' is currently supported.",
            )

        object.__setattr__(
            self,
            "limit_fill_at",
            limit_fill_at,
        )

        stop_fill_at = (
            str(
                self.stop_fill_at,
            )
            .strip()
            .lower()
        )

        if stop_fill_at != "price":
            raise ValueError(
                "Only stop_fill_at='price' is currently supported.",
            )

        object.__setattr__(
            self,
            "stop_fill_at",
            stop_fill_at,
        )

        object.__setattr__(
            self,
            "gap_fill",
            bool(self.gap_fill),
        )

    @staticmethod
    def _to_finite_decimal(
        value: Decimal,
        field_name: str,
    ) -> Decimal:
        """Convert a configuration value into a finite Decimal."""

        try:
            result = value if isinstance(value, Decimal) else Decimal(str(value))
        except Exception as exc:
            raise ValueError(
                f"{field_name} must be a valid decimal value.",
            ) from exc

        if not result.is_finite():
            raise ValueError(
                f"{field_name} must be finite.",
            )

        return result


# ======================================================================
# FILL ENGINE
# ======================================================================


class BacktestFillEngine:
    """
    Convert ExecutionOrder instructions into deterministic simulated
    fills.

    Responsibilities:

        ExecutionOrder + current market
            ↓
        fill decision
            ↓
        BacktestFill

    This class does NOT:

        - manage positions
        - modify account balance
        - calculate risk
        - manage pending-order lifecycle
        - call a real broker
        - persist anything
        - generate strategy signals

    Pending-order persistence and multi-candle lifecycle management
    belong to the higher-level backtest execution engine.
    """

    def __init__(
        self,
        config: BacktestFillConfig | None = None,
    ) -> None:
        self.config = config if config is not None else BacktestFillConfig()

    # ==================================================================
    # PUBLIC EXECUTION
    # ==================================================================

    def execute(
        self,
        order: ExecutionOrder,
        market: BacktestMarket,
        *,
        order_id: UUID | None = None,
    ) -> BacktestFill:
        """
        Attempt to fill one ExecutionOrder against the supplied market.

        The market object is the canonical backtesting market contract
        from ``backtesting.market``.
        """

        if order is None:
            raise BacktestFillError(
                "ExecutionOrder is required.",
            )

        if not isinstance(
            order,
            ExecutionOrder,
        ):
            raise BacktestFillError(
                "order must be an ExecutionOrder.",
            )

        if market is None:
            raise BacktestFillError(
                "BacktestMarket is required.",
            )

        order_symbol = self._normalize_symbol(
            order.symbol,
        )

        market_symbol = self._normalize_symbol(
            market.candle.symbol,
        )

        if order_symbol != market_symbol:
            raise BacktestFillError(
                f"Order symbol '{order_symbol}' does not match "
                f"market symbol '{market_symbol}'.",
            )

        self._validate_volume(
            order.volume,
        )

        resolved_order_id = order_id if order_id is not None else uuid4()

        if not isinstance(
            resolved_order_id,
            UUID,
        ):
            raise BacktestFillError(
                "order_id must be a UUID.",
            )

        if order.order_type == OrderType.MARKET:
            return self._fill_market_order(
                order=order,
                market=market,
                order_id=resolved_order_id,
            )

        if order.order_type == OrderType.LIMIT:
            return self._fill_limit_order(
                order=order,
                market=market,
                order_id=resolved_order_id,
            )

        if order.order_type == OrderType.STOP:
            return self._fill_stop_order(
                order=order,
                market=market,
                order_id=resolved_order_id,
            )

        raise BacktestFillError(
            f"Unsupported order type: {order.order_type}",
        )

    # ==================================================================
    # MARKET ORDERS
    # ==================================================================

    def _fill_market_order(
        self,
        order: ExecutionOrder,
        market: BacktestMarket,
        order_id: UUID,
    ) -> BacktestFill:
        """
        Fill a MARKET order against the configured market reference.

        In the AQE backtest lifecycle, strategy evaluation happens after
        the current candle has been observed. The default therefore uses
        candle.close rather than candle.open.
        """

        candle = market.candle

        if self.config.market_fill_at == "open":
            base_price = self._positive_price(
                candle.open,
                "Candle open",
            )
        else:
            base_price = self._positive_price(
                candle.close,
                "Candle close",
            )

        executable_price = self._resolve_market_execution_price(
            base_price=base_price,
            market=market,
            side=order.side,
        )

        commission = order.volume * self.config.commission_per_volume

        total_slippage = abs(
            executable_price - base_price,
        )

        return BacktestFill(
            fill_id=uuid4(),
            order_id=order_id,
            symbol=self._normalize_symbol(
                order.symbol,
            ),
            side=order.side,
            order_type=order.order_type,
            volume=order.volume,
            price=executable_price,
            timestamp=self._normalize_timestamp(
                candle.timestamp,
            ),
            status=FillStatus.FILLED,
            reason=FillReason.MARKET,
            commission=commission,
            slippage=total_slippage,
        )

    # ==================================================================
    # LIMIT ORDERS
    # ==================================================================

    def _fill_limit_order(
        self,
        order: ExecutionOrder,
        market: BacktestMarket,
        order_id: UUID,
    ) -> BacktestFill:
        """
        Determine whether a LIMIT order was reached during the candle.

        A LIMIT order must never be filled at a worse price than its
        specified limit.

        Slippage is deliberately not applied adversely to LIMIT orders.
        A limit order provides price protection.
        """

        if order.price is None:
            raise BacktestFillError(
                "LIMIT order requires a price.",
            )

        candle = market.candle

        limit_price = self._positive_price(
            order.price,
            "LIMIT order price",
        )

        # --------------------------------------------------------------
        # Trigger detection.
        # --------------------------------------------------------------

        if order.side == OrderSide.BUY:
            triggered = candle.low <= limit_price

        elif order.side == OrderSide.SELL:
            triggered = candle.high >= limit_price

        else:
            raise BacktestFillError(
                f"Unsupported limit order side: {order.side}",
            )

        if not triggered:
            return self._not_filled(
                order=order,
                order_id=order_id,
                market=market,
                reason=FillReason.NOT_REACHED,
            )

        # --------------------------------------------------------------
        # Default execution is the requested limit price.
        # --------------------------------------------------------------

        fill_price = limit_price

        # --------------------------------------------------------------
        # Gap improvement.
        #
        # BUY LIMIT:
        #   candle opens below the requested limit.
        #
        # SELL LIMIT:
        #   candle opens above the requested limit.
        #
        # In either case, the trader receives the better opening price.
        # --------------------------------------------------------------

        if self.config.gap_fill:
            if order.side == OrderSide.BUY and candle.open < limit_price:
                fill_price = candle.open

            elif order.side == OrderSide.SELL and candle.open > limit_price:
                fill_price = candle.open

        fill_price = self._apply_limit_protection(
            price=fill_price,
            limit_price=limit_price,
            side=order.side,
        )

        self._validate_positive_price(
            fill_price,
            "LIMIT execution price",
        )

        commission = order.volume * self.config.commission_per_volume

        return BacktestFill(
            fill_id=uuid4(),
            order_id=order_id,
            symbol=self._normalize_symbol(
                order.symbol,
            ),
            side=order.side,
            order_type=order.order_type,
            volume=order.volume,
            price=fill_price,
            timestamp=self._normalize_timestamp(
                candle.timestamp,
            ),
            status=FillStatus.FILLED,
            reason=FillReason.LIMIT_TRIGGERED,
            commission=commission,
            slippage=abs(
                fill_price - limit_price,
            ),
        )

    # ==================================================================
    # STOP ORDERS
    # ==================================================================

    def _fill_stop_order(
        self,
        order: ExecutionOrder,
        market: BacktestMarket,
        order_id: UUID,
    ) -> BacktestFill:
        """
        Determine whether a STOP order triggered during the candle.

        Stops become marketable after triggering and may therefore suffer
        adverse slippage.
        """

        if order.price is None:
            raise BacktestFillError(
                "STOP order requires a price.",
            )

        candle = market.candle

        stop_price = self._positive_price(
            order.price,
            "STOP order price",
        )

        # --------------------------------------------------------------
        # Trigger detection.
        # --------------------------------------------------------------

        if order.side == OrderSide.BUY:
            triggered = candle.high >= stop_price

        elif order.side == OrderSide.SELL:
            triggered = candle.low <= stop_price

        else:
            raise BacktestFillError(
                f"Unsupported stop order side: {order.side}",
            )

        if not triggered:
            return self._not_filled(
                order=order,
                order_id=order_id,
                market=market,
                reason=FillReason.NOT_REACHED,
            )

        fill_price = stop_price

        # --------------------------------------------------------------
        # Gap-through behavior.
        #
        # BUY STOP:
        #   market opens above stop.
        #
        # SELL STOP:
        #   market opens below stop.
        # --------------------------------------------------------------

        if self.config.gap_fill:
            if order.side == OrderSide.BUY and candle.open > stop_price:
                fill_price = candle.open

            elif order.side == OrderSide.SELL and candle.open < stop_price:
                fill_price = candle.open

        fill_price = self._apply_slippage(
            price=fill_price,
            side=order.side,
        )

        self._validate_positive_price(
            fill_price,
            "STOP execution price",
        )

        commission = order.volume * self.config.commission_per_volume

        return BacktestFill(
            fill_id=uuid4(),
            order_id=order_id,
            symbol=self._normalize_symbol(
                order.symbol,
            ),
            side=order.side,
            order_type=order.order_type,
            volume=order.volume,
            price=fill_price,
            timestamp=self._normalize_timestamp(
                candle.timestamp,
            ),
            status=FillStatus.FILLED,
            reason=FillReason.STOP_TRIGGERED,
            commission=commission,
            slippage=abs(
                fill_price - stop_price,
            ),
        )

    # ==================================================================
    # MARKET EXECUTION PRICE
    # ==================================================================

    def _resolve_market_execution_price(
        self,
        *,
        base_price: Decimal,
        market: BacktestMarket,
        side: OrderSide,
    ) -> Decimal:
        """
        Resolve the executable MARKET price.

        Explicit bid/ask from BacktestMarket take precedence over the
        configured synthetic spread.

        When bid/ask are unavailable, the configured total spread is
        split equally around the reference price.
        """

        base_price = self._positive_price(
            base_price,
            "Market reference price",
        )

        if market.bid is not None and market.ask is not None:
            bid = self._positive_price(
                market.bid,
                "Market bid",
            )

            ask = self._positive_price(
                market.ask,
                "Market ask",
            )

            if bid > ask:
                raise BacktestFillError(
                    "Market bid cannot be greater than market ask.",
                )

            if side == OrderSide.BUY:
                price = ask

            elif side == OrderSide.SELL:
                price = bid

            else:
                raise BacktestFillError(
                    f"Unsupported order side: {side}",
                )

        else:
            price = self._apply_spread(
                base_price=base_price,
                side=side,
            )

        price = self._apply_slippage(
            price=price,
            side=side,
        )

        self._validate_positive_price(
            price,
            "Market execution price",
        )

        return price

    # ==================================================================
    # NOT FILLED
    # ==================================================================

    def _not_filled(
        self,
        *,
        order: ExecutionOrder,
        order_id: UUID,
        market: BacktestMarket,
        reason: FillReason,
    ) -> BacktestFill:
        """
        Build a deterministic non-fill result.

        Price, commission, and slippage remain zero because no execution
        occurred.
        """

        return BacktestFill(
            fill_id=uuid4(),
            order_id=order_id,
            symbol=self._normalize_symbol(
                order.symbol,
            ),
            side=order.side,
            order_type=order.order_type,
            volume=order.volume,
            price=Decimal("0"),
            timestamp=self._normalize_timestamp(
                market.candle.timestamp,
            ),
            status=FillStatus.NOT_FILLED,
            reason=reason,
            commission=Decimal("0"),
            slippage=Decimal("0"),
        )

    # ==================================================================
    # SPREAD
    # ==================================================================

    def _apply_spread(
        self,
        *,
        base_price: Decimal,
        side: OrderSide,
    ) -> Decimal:
        """
        Apply half of the configured total spread around the reference.

        BUY:
            reference + half spread

        SELL:
            reference - half spread
        """

        half_spread = self.config.spread / Decimal("2")

        if side == OrderSide.BUY:
            return base_price + half_spread

        if side == OrderSide.SELL:
            return base_price - half_spread

        raise BacktestFillError(
            f"Unsupported order side: {side}",
        )

    # ==================================================================
    # SLIPPAGE
    # ==================================================================

    def _apply_slippage(
        self,
        *,
        price: Decimal,
        side: OrderSide,
    ) -> Decimal:
        """
        Apply adverse slippage to a marketable execution.

        BUY:
            price increases

        SELL:
            price decreases
        """

        if self.config.slippage == Decimal("0"):
            return price

        if side == OrderSide.BUY:
            return price + self.config.slippage

        if side == OrderSide.SELL:
            return price - self.config.slippage

        raise BacktestFillError(
            f"Unsupported order side: {side}",
        )

    # ==================================================================
    # LIMIT PROTECTION
    # ==================================================================

    @staticmethod
    def _apply_limit_protection(
        *,
        price: Decimal,
        limit_price: Decimal,
        side: OrderSide,
    ) -> Decimal:
        """
        Ensure a LIMIT order cannot execute worse than its limit.

        BUY LIMIT:
            execution <= limit

        SELL LIMIT:
            execution >= limit
        """

        if side == OrderSide.BUY:
            return min(
                price,
                limit_price,
            )

        if side == OrderSide.SELL:
            return max(
                price,
                limit_price,
            )

        raise BacktestFillError(
            f"Unsupported order side: {side}",
        )

    # ==================================================================
    # VALIDATION
    # ==================================================================

    @staticmethod
    def _validate_volume(
        volume: Decimal,
    ) -> None:
        """Validate an execution volume."""

        if not isinstance(
            volume,
            Decimal,
        ):
            try:
                volume = Decimal(
                    str(volume),
                )
            except Exception as exc:
                raise BacktestFillError(
                    "Order volume must be a valid Decimal.",
                ) from exc

        if not volume.is_finite():
            raise BacktestFillError(
                "Order volume must be finite.",
            )

        if volume <= Decimal("0"):
            raise BacktestFillError(
                "Order volume must be greater than zero.",
            )

    @staticmethod
    def _positive_price(
        price: Decimal,
        field_name: str,
    ) -> Decimal:
        """Convert and validate a strictly positive price."""

        try:
            normalized = price if isinstance(price, Decimal) else Decimal(str(price))
        except Exception as exc:
            raise BacktestFillError(
                f"{field_name} must be a valid decimal value.",
            ) from exc

        if not normalized.is_finite():
            raise BacktestFillError(
                f"{field_name} must be finite.",
            )

        if normalized <= Decimal("0"):
            raise BacktestFillError(
                f"{field_name} must be greater than zero.",
            )

        return normalized

    @staticmethod
    def _validate_positive_price(
        price: Decimal,
        field_name: str,
    ) -> None:
        """Validate that an already-normalized price is positive."""

        if not isinstance(
            price,
            Decimal,
        ):
            raise BacktestFillError(
                f"{field_name} must be a Decimal.",
            )

        if not price.is_finite():
            raise BacktestFillError(
                f"{field_name} must be finite.",
            )

        if price <= Decimal("0"):
            raise BacktestFillError(
                f"{field_name} must be greater than zero.",
            )

    # ==================================================================
    # HELPERS
    # ==================================================================

    @staticmethod
    def _normalize_symbol(
        symbol: str,
    ) -> str:
        """Normalize a broker symbol."""

        if not isinstance(
            symbol,
            str,
        ):
            raise BacktestFillError(
                "Order symbol must be a string.",
            )

        normalized = symbol.strip().upper()

        if not normalized:
            raise BacktestFillError(
                "Order symbol cannot be empty.",
            )

        return normalized

    @staticmethod
    def _normalize_timestamp(
        timestamp: datetime,
    ) -> datetime:
        """Validate and return the candle timestamp."""

        if not isinstance(
            timestamp,
            datetime,
        ):
            raise BacktestFillError(
                "Fill timestamp must be a datetime.",
            )

        return timestamp
