from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from enum import StrEnum
from uuid import UUID, uuid4


class BacktestPositionSide(StrEnum):
    """Side of a simulated position."""

    LONG = "LONG"
    SHORT = "SHORT"


class BacktestPositionStatus(StrEnum):
    """Lifecycle state of a simulated position."""

    OPEN = "OPEN"
    CLOSED = "CLOSED"


@dataclass(slots=True)
class BacktestPosition:
    """
    Represents a single simulated trading position.

    This is a pure backtesting domain object. It is deliberately
    independent of database models and live broker models.
    """

    position_id: UUID
    account_id: UUID
    symbol: str
    side: BacktestPositionSide

    volume: Decimal
    entry_price: Decimal
    opened_at: datetime

    stop_loss: Decimal | None = None
    take_profit: Decimal | None = None

    strategy_id: str | None = None
    strategy_name: str | None = None

    status: BacktestPositionStatus = BacktestPositionStatus.OPEN

    exit_price: Decimal | None = None
    closed_at: datetime | None = None

    realized_pnl: Decimal = Decimal("0")
    commission: Decimal = Decimal("0")
    swap: Decimal = Decimal("0")

    exit_reason: str | None = None

    @classmethod
    def open(
        cls,
        *,
        account_id: UUID,
        symbol: str,
        side: BacktestPositionSide,
        volume: Decimal,
        entry_price: Decimal,
        opened_at: datetime | None = None,
        stop_loss: Decimal | None = None,
        take_profit: Decimal | None = None,
        strategy_id: str | None = None,
        strategy_name: str | None = None,
    ) -> BacktestPosition:
        """
        Create a new open simulated position.
        """

        if volume <= Decimal("0"):
            raise ValueError("Position volume must be greater than zero.")

        if entry_price <= Decimal("0"):
            raise ValueError("Entry price must be greater than zero.")

        if stop_loss is not None and stop_loss <= Decimal("0"):
            raise ValueError("Stop loss must be greater than zero.")

        if take_profit is not None and take_profit <= Decimal("0"):
            raise ValueError("Take profit must be greater than zero.")

        timestamp = opened_at or datetime.now(timezone.utc)

        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)

        return cls(
            position_id=uuid4(),
            account_id=account_id,
            symbol=symbol.upper(),
            side=side,
            volume=volume,
            entry_price=entry_price,
            opened_at=timestamp,
            stop_loss=stop_loss,
            take_profit=take_profit,
            strategy_id=strategy_id,
            strategy_name=strategy_name,
        )

    @property
    def is_open(self) -> bool:
        """Return whether the position is currently open."""

        return self.status == BacktestPositionStatus.OPEN

    @property
    def is_closed(self) -> bool:
        """Return whether the position has been closed."""

        return self.status == BacktestPositionStatus.CLOSED

    def unrealized_pnl(
        self,
        current_price: Decimal,
        contract_size: Decimal = Decimal("1"),
    ) -> Decimal:
        """
        Calculate unrealized P&L at the supplied market price.

        The calculation is:

            LONG  = (current - entry) * volume * contract_size
            SHORT = (entry - current) * volume * contract_size
        """

        if current_price <= Decimal("0"):
            raise ValueError("Current price must be greater than zero.")

        if contract_size <= Decimal("0"):
            raise ValueError("Contract size must be greater than zero.")

        if self.side == BacktestPositionSide.LONG:
            price_difference = current_price - self.entry_price
        else:
            price_difference = self.entry_price - current_price

        return price_difference * self.volume * contract_size

    def close(
        self,
        *,
        exit_price: Decimal,
        closed_at: datetime | None = None,
        reason: str | None = None,
        contract_size: Decimal = Decimal("1"),
        commission: Decimal = Decimal("0"),
        swap: Decimal = Decimal("0"),
    ) -> Decimal:
        """
        Close the position and calculate realized P&L.

        Returns:
            Realized gross P&L before commission and swap.
        """

        if self.is_closed:
            raise ValueError(
                f"Position {self.position_id} is already closed."
            )

        if exit_price <= Decimal("0"):
            raise ValueError("Exit price must be greater than zero.")

        if contract_size <= Decimal("0"):
            raise ValueError("Contract size must be greater than zero.")

        if commission < Decimal("0"):
            raise ValueError("Commission cannot be negative.")

        if swap < Decimal("0"):
            raise ValueError("Swap cannot be negative.")

        timestamp = closed_at or datetime.now(timezone.utc)

        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)

        gross_pnl = self._calculate_pnl(
            exit_price=exit_price,
            contract_size=contract_size,
        )

        self.exit_price = exit_price
        self.closed_at = timestamp
        self.status = BacktestPositionStatus.CLOSED

        self.realized_pnl = gross_pnl
        self.commission = commission
        self.swap = swap
        self.exit_reason = reason

        return gross_pnl

    def _calculate_pnl(
        self,
        *,
        exit_price: Decimal,
        contract_size: Decimal,
    ) -> Decimal:
        """Calculate gross realized P&L."""

        if self.side == BacktestPositionSide.LONG:
            price_difference = exit_price - self.entry_price
        else:
            price_difference = self.entry_price - exit_price

        return price_difference * self.volume * contract_size

    def __post_init__(self) -> None:
        """Normalize and validate directly constructed positions."""

        self.symbol = self.symbol.strip().upper()

        if not self.symbol:
            raise ValueError("Position symbol cannot be empty.")

        if self.volume <= Decimal("0"):
            raise ValueError("Position volume must be greater than zero.")

        if self.entry_price <= Decimal("0"):
            raise ValueError("Entry price must be greater than zero.")

        if self.opened_at.tzinfo is None:
            self.opened_at = self.opened_at.replace(
                tzinfo=timezone.utc
            )