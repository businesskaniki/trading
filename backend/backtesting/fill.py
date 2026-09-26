from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID, uuid4

from app.schemas.execution import ExecutionOrder, OrderSide, OrderType


class BacktestFillError(Exception):
    """Base exception for simulated fill failures."""


class FillStatus(StrEnum):
    FILLED = "FILLED"
    NOT_FILLED = "NOT_FILLED"


class FillReason(StrEnum):
    MARKET = "MARKET"
    LIMIT_TRIGGERED = "LIMIT_TRIGGERED"
    STOP_TRIGGERED = "STOP_TRIGGERED"
    NOT_REACHED = "NOT_REACHED"


@dataclass(frozen=True, slots=True)
class BacktestCandle:
    """
    Minimal OHLC market representation used by the fill engine.
    """

    symbol: str
    timestamp: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal

    def __post_init__(self) -> None:
        if not self.symbol or not self.symbol.strip():
            raise ValueError("Candle symbol cannot be empty.")

        if self.open <= Decimal("0"):
            raise ValueError("Candle open must be positive.")

        if self.high <= Decimal("0"):
            raise ValueError("Candle high must be positive.")

        if self.low <= Decimal("0"):
            raise ValueError("Candle low must be positive.")

        if self.close <= Decimal("0"):
            raise ValueError("Candle close must be positive.")

        if self.high < max(self.open, self.close):
            raise ValueError("Candle high cannot be below open or close.")

        if self.low > min(self.open, self.close):
            raise ValueError("Candle low cannot be above open or close.")


@dataclass(frozen=True, slots=True)
class BacktestMarket:
    """
    Market conditions used when processing an order.

    bid/ask are optional because OHLC backtests may only provide
    candle data. When spread is configured, the fill engine derives
    executable bid/ask prices from the candle midpoint.
    """

    candle: BacktestCandle

    bid: Decimal | None = None
    ask: Decimal | None = None

    def __post_init__(self) -> None:
        if self.bid is not None and self.bid <= Decimal("0"):
            raise ValueError("Bid must be positive.")

        if self.ask is not None and self.ask <= Decimal("0"):
            raise ValueError("Ask must be positive.")

        if self.bid is not None and self.ask is not None and self.ask < self.bid:
            raise ValueError("Ask cannot be below bid.")

    @property
    def midpoint(self) -> Decimal:
        if self.bid is not None and self.ask is not None:
            return (self.bid + self.ask) / Decimal("2")

        return self.candle.close


@dataclass(frozen=True, slots=True)
class BacktestFill:
    """
    Result of a simulated order fill.
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
        return self.status == FillStatus.FILLED


@dataclass(frozen=True, slots=True)
class BacktestFillConfig:
    """
    Deterministic execution assumptions for the backtest.

    spread:
        Fixed bid/ask spread in price units.

    slippage:
        Absolute price movement applied against the trader.

    commission_per_volume:
        Commission charged per unit of executed volume.

    market_fill_at:
        Controls where a market order is filled.

        "open" is appropriate when an order generated from the
        previous candle is executed at the next candle open.

        "close" is useful only when the engine explicitly defines
        the signal as executable at the same candle close.

    limit_fill_at:
        "price" means a triggered limit order fills at its limit.

    stop_fill_at:
        "price" means a triggered stop order fills at its stop price.

    gap_fill:
        When True, a pending order that gaps through its trigger
        fills at the candle open rather than at the requested price.
    """

    spread: Decimal = Decimal("0")
    slippage: Decimal = Decimal("0")
    commission_per_volume: Decimal = Decimal("0")

    market_fill_at: str = "open"
    limit_fill_at: str = "price"
    stop_fill_at: str = "price"

    gap_fill: bool = True

    def __post_init__(self) -> None:
        if self.spread < Decimal("0"):
            raise ValueError("Spread cannot be negative.")

        if self.slippage < Decimal("0"):
            raise ValueError("Slippage cannot be negative.")

        if self.commission_per_volume < Decimal("0"):
            raise ValueError("Commission cannot be negative.")

        if self.market_fill_at not in {"open", "close"}:
            raise ValueError("market_fill_at must be 'open' or 'close'.")

        if self.limit_fill_at != "price":
            raise ValueError("Only limit_fill_at='price' is currently supported.")

        if self.stop_fill_at != "price":
            raise ValueError("Only stop_fill_at='price' is currently supported.")


class BacktestFillEngine:
    """
    Converts ExecutionOrder instructions into simulated fills.

    This class does not:
    - manage positions
    - manage account balance
    - perform risk checks
    - call a real broker
    - persist anything

    It only answers:

        "Given this order and this market candle,
         did the order fill, and at what price?"
    """

    def __init__(
        self,
        config: BacktestFillConfig | None = None,
    ) -> None:
        self.config = config or BacktestFillConfig()

    def execute(
        self,
        order: ExecutionOrder,
        market: BacktestMarket,
        *,
        order_id: UUID | None = None,
    ) -> BacktestFill:
        """
        Attempt to fill an ExecutionOrder against the supplied market.
        """

        if order.symbol.upper() != market.candle.symbol.upper():
            raise BacktestFillError(
                f"Order symbol '{order.symbol}' does not match "
                f"market symbol '{market.candle.symbol}'."
            )

        if order.volume <= Decimal("0"):
            raise BacktestFillError("Order volume must be greater than zero.")

        resolved_order_id = order_id or uuid4()

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

        raise BacktestFillError(f"Unsupported order type: {order.order_type}")

    # ------------------------------------------------------------------
    # MARKET ORDERS
    # ------------------------------------------------------------------

    def _fill_market_order(
        self,
        order: ExecutionOrder,
        market: BacktestMarket,
        order_id: UUID,
    ) -> BacktestFill:
        candle = market.candle

        if self.config.market_fill_at == "open":
            base_price = candle.open
        else:
            base_price = candle.close

        executable_price = self._apply_spread(
            base_price=base_price,
            side=order.side,
        )

        executable_price = self._apply_slippage(
            price=executable_price,
            side=order.side,
        )

        commission = order.volume * self.config.commission_per_volume

        return BacktestFill(
            fill_id=uuid4(),
            order_id=order_id,
            symbol=order.symbol,
            side=order.side,
            order_type=order.order_type,
            volume=order.volume,
            price=executable_price,
            timestamp=candle.timestamp,
            status=FillStatus.FILLED,
            reason=FillReason.MARKET,
            commission=commission,
            slippage=abs(executable_price - base_price),
        )

    # ------------------------------------------------------------------
    # LIMIT ORDERS
    # ------------------------------------------------------------------

    def _fill_limit_order(
        self,
        order: ExecutionOrder,
        market: BacktestMarket,
        order_id: UUID,
    ) -> BacktestFill:
        if order.price is None:
            raise BacktestFillError("LIMIT order requires a price.")

        candle = market.candle
        limit_price = order.price

        if order.side == OrderSide.BUY:
            triggered = candle.low <= limit_price
        else:
            triggered = candle.high >= limit_price

        if not triggered:
            return self._not_filled(
                order=order,
                order_id=order_id,
                market=market,
                reason=FillReason.NOT_REACHED,
            )

        fill_price = limit_price

        # If the market opens beyond the limit in a favorable
        # direction, the order receives the opening price.
        if self.config.gap_fill:
            if order.side == OrderSide.BUY and candle.open < limit_price:
                fill_price = candle.open

            elif order.side == OrderSide.SELL and candle.open > limit_price:
                fill_price = candle.open

        fill_price = self._apply_slippage(
            price=fill_price,
            side=order.side,
        )

        commission = order.volume * self.config.commission_per_volume

        return BacktestFill(
            fill_id=uuid4(),
            order_id=order_id,
            symbol=order.symbol,
            side=order.side,
            order_type=order.order_type,
            volume=order.volume,
            price=fill_price,
            timestamp=candle.timestamp,
            status=FillStatus.FILLED,
            reason=FillReason.LIMIT_TRIGGERED,
            commission=commission,
            slippage=abs(fill_price - limit_price),
        )

    # ------------------------------------------------------------------
    # STOP ORDERS
    # ------------------------------------------------------------------

    def _fill_stop_order(
        self,
        order: ExecutionOrder,
        market: BacktestMarket,
        order_id: UUID,
    ) -> BacktestFill:
        if order.price is None:
            raise BacktestFillError("STOP order requires a price.")

        candle = market.candle
        stop_price = order.price

        if order.side == OrderSide.BUY:
            triggered = candle.high >= stop_price
        else:
            triggered = candle.low <= stop_price

        if not triggered:
            return self._not_filled(
                order=order,
                order_id=order_id,
                market=market,
                reason=FillReason.NOT_REACHED,
            )

        fill_price = stop_price

        # A gap through a stop executes at the opening price.
        if self.config.gap_fill:
            if order.side == OrderSide.BUY and candle.open > stop_price:
                fill_price = candle.open

            elif order.side == OrderSide.SELL and candle.open < stop_price:
                fill_price = candle.open

        fill_price = self._apply_slippage(
            price=fill_price,
            side=order.side,
        )

        commission = order.volume * self.config.commission_per_volume

        return BacktestFill(
            fill_id=uuid4(),
            order_id=order_id,
            symbol=order.symbol,
            side=order.side,
            order_type=order.order_type,
            volume=order.volume,
            price=fill_price,
            timestamp=candle.timestamp,
            status=FillStatus.FILLED,
            reason=FillReason.STOP_TRIGGERED,
            commission=commission,
            slippage=abs(fill_price - stop_price),
        )

    # ------------------------------------------------------------------
    # HELPERS
    # ------------------------------------------------------------------

    def _not_filled(
        self,
        order: ExecutionOrder,
        order_id: UUID,
        market: BacktestMarket,
        reason: FillReason,
    ) -> BacktestFill:
        return BacktestFill(
            fill_id=uuid4(),
            order_id=order_id,
            symbol=order.symbol,
            side=order.side,
            order_type=order.order_type,
            volume=order.volume,
            price=Decimal("0"),
            timestamp=market.candle.timestamp,
            status=FillStatus.NOT_FILLED,
            reason=reason,
        )

    def _apply_spread(
        self,
        base_price: Decimal,
        side: OrderSide,
    ) -> Decimal:
        half_spread = self.config.spread / Decimal("2")

        if side == OrderSide.BUY:
            return base_price + half_spread

        return base_price - half_spread

    def _apply_slippage(
        self,
        price: Decimal,
        side: OrderSide,
    ) -> Decimal:
        if self.config.slippage == Decimal("0"):
            return price

        if side == OrderSide.BUY:
            return price + self.config.slippage

        return price - self.config.slippage
