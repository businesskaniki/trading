from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID

from .position import (
    BacktestPosition,
    BacktestPositionStatus,
)


class BacktestPortfolioError(Exception):
    """Base exception for backtest portfolio failures."""


class BacktestInsufficientFundsError(BacktestPortfolioError):
    """Raised when the portfolio cannot support an operation."""


class BacktestPositionNotFoundError(BacktestPortfolioError):
    """Raised when a requested position does not exist."""


@dataclass(slots=True)
class BacktestPortfolio:
    """
    Shared simulated account portfolio for a backtest.

    A single portfolio may contain positions opened by:
    - multiple strategies
    - multiple symbols
    - multiple timeframes

    The portfolio is intentionally independent from:
    - the live broker
    - PostgreSQL
    - Redis
    - the Strategy Engine
    - the Risk Engine

    The Risk Engine decides whether a trade is allowed.

    The execution layer mutates this portfolio when a simulated
    order is filled.

    Margin is explicitly tracked at the portfolio level, but the
    portfolio does not determine leverage or broker-specific margin
    requirements. The execution layer is responsible for calculating
    required margin and passing it here when a position is opened.
    """

    account_id: UUID
    initial_balance: Decimal

    balance: Decimal | None = None

    positions: dict[UUID, BacktestPosition] = field(default_factory=dict)

    realized_pnl: Decimal = Decimal("0")
    commission_paid: Decimal = Decimal("0")
    swap_paid: Decimal = Decimal("0")

    peak_equity: Decimal | None = None

    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    current_time: datetime | None = None

    # ------------------------------------------------------------------
    # Mark-to-market state
    # ------------------------------------------------------------------

    _unrealized_pnl: Decimal = field(
        default=Decimal("0"),
        repr=False,
    )

    # ------------------------------------------------------------------
    # Margin state
    # ------------------------------------------------------------------

    # Margin is tracked per position so closing one position releases
    # exactly the amount reserved for that position.
    _reserved_margin_by_position: dict[UUID, Decimal] = field(
        default_factory=dict,
        repr=False,
    )

    def __post_init__(self) -> None:
        self.initial_balance = Decimal(str(self.initial_balance))

        if self.initial_balance < Decimal("0"):
            raise ValueError("Initial balance cannot be negative.")

        if self.balance is None:
            self.balance = self.initial_balance
        else:
            self.balance = Decimal(str(self.balance))

        if self.balance < Decimal("0"):
            raise ValueError("Balance cannot be negative.")

        self.realized_pnl = Decimal(str(self.realized_pnl))
        self.commission_paid = Decimal(str(self.commission_paid))
        self.swap_paid = Decimal(str(self.swap_paid))
        self._unrealized_pnl = Decimal(str(self._unrealized_pnl))

        if self.peak_equity is None:
            self.peak_equity = self.balance + self._unrealized_pnl
        else:
            self.peak_equity = Decimal(str(self.peak_equity))

        self.created_at = self._normalize_datetime(self.created_at)

        if self.current_time is not None:
            self.current_time = self._normalize_datetime(self.current_time)

        normalized_margin: dict[UUID, Decimal] = {}

        for position_id, margin in self._reserved_margin_by_position.items():
            normalized_margin[position_id] = self._validate_margin_amount(
                margin,
            )

        self._reserved_margin_by_position = normalized_margin

    # ------------------------------------------------------------------
    # ACCOUNT STATE
    # ------------------------------------------------------------------

    @property
    def equity(self) -> Decimal:
        """
        Current account equity.

        Equity is:

            balance + latest marked unrealized P&L

        Before the portfolio has been marked to market, unrealized P&L is
        zero and equity therefore equals balance.
        """

        return self.balance + self._unrealized_pnl

    @property
    def free_margin(self) -> Decimal:
        """
        Current simulated free margin.

        Free margin is:

            equity - used margin

        The value may become negative if a simulation permits equity to
        fall below reserved margin. Margin/risk rules are responsible for
        preventing additional exposure in that situation.
        """

        return self.equity - self.margin

    @property
    def margin(self) -> Decimal:
        """
        Current simulated used margin.

        Margin is the sum of margin reservations associated with all
        currently open positions.
        """

        return sum(
            self._reserved_margin_by_position.values(),
            Decimal("0"),
        )

    @property
    def margin_level(self) -> Decimal | None:
        """
        Current simulated margin level.

        Returns ``None`` when no margin is reserved.

        Margin level is:

            equity / used_margin × 100
        """

        margin = self.margin

        if margin <= Decimal("0"):
            return None

        return (self.equity / margin) * Decimal("100")

    @property
    def open_positions(self) -> list[BacktestPosition]:
        """Return all currently open positions."""

        return [
            position
            for position in self.positions.values()
            if position.status == BacktestPositionStatus.OPEN
        ]

    @property
    def closed_positions(self) -> list[BacktestPosition]:
        """Return all closed positions."""

        return [
            position
            for position in self.positions.values()
            if position.status == BacktestPositionStatus.CLOSED
        ]

    @property
    def open_position_count(self) -> int:
        """Number of currently open positions."""

        return len(self.open_positions)

    @property
    def closed_position_count(self) -> int:
        """Number of positions that have been closed."""

        return len(self.closed_positions)

    # ------------------------------------------------------------------
    # P&L
    # ------------------------------------------------------------------

    def total_unrealized_pnl(
        self,
        prices: dict[str, Decimal],
        contract_sizes: dict[str, Decimal] | None = None,
    ) -> Decimal:
        """
        Calculate unrealized P&L across every open position.

        ``prices`` is keyed by normalized symbol.

        ``contract_sizes`` allows instruments such as XAUUSD to use
        their actual contract size instead of the generic default of 1.

        Because this is a shared account portfolio, positions from all
        strategies are included in the same calculation.
        """

        if not self.open_positions:
            return Decimal("0")

        normalized_prices = {
            self._normalize_symbol(symbol): Decimal(str(price))
            for symbol, price in prices.items()
        }

        normalized_contract_sizes = self._normalize_contract_sizes(
            contract_sizes,
        )

        total = Decimal("0")

        for position in self.open_positions:
            symbol = self._normalize_symbol(position.symbol)

            try:
                current_price = normalized_prices[symbol]
            except KeyError as exc:
                raise ValueError(
                    f"Missing current price for open position " f"'{position.symbol}'."
                ) from exc

            contract_size = normalized_contract_sizes.get(
                symbol,
                Decimal("1"),
            )

            total += position.unrealized_pnl(
                current_price=current_price,
                contract_size=contract_size,
            )

        return total

    def mark_to_market(
        self,
        prices: dict[str, Decimal],
        contract_sizes: dict[str, Decimal] | None = None,
        timestamp: datetime | None = None,
    ) -> Decimal:
        """
        Mark the shared account to current market prices.

        Returns the resulting account equity and stores the latest
        unrealized P&L used by the account-state properties.
        """

        if timestamp is not None:
            self.current_time = self._normalize_datetime(timestamp)

        unrealized = self.total_unrealized_pnl(
            prices=prices,
            contract_sizes=contract_sizes,
        )

        self._unrealized_pnl = unrealized

        equity = self.balance + unrealized

        self._update_peak_equity(equity)

        return equity

    @property
    def total_realized_pnl(self) -> Decimal:
        """Alias for the account's realized P&L."""

        return self.realized_pnl

    @property
    def total_pnl(self) -> Decimal:
        """
        Realized account P&L relative to the initial balance.

        Unrealized P&L is excluded because it has not yet been realized
        into account balance.
        """

        return self.balance - self.initial_balance

    def drawdown_from_equity(
        self,
        equity: Decimal,
    ) -> Decimal:
        """
        Calculate absolute drawdown from peak equity.
        """

        peak = self.peak_equity or self.initial_balance

        return max(
            Decimal("0"),
            peak - Decimal(str(equity)),
        )

    def drawdown_percent_from_equity(
        self,
        equity: Decimal,
    ) -> Decimal:
        """
        Calculate percentage drawdown from peak equity.
        """

        peak = self.peak_equity or self.initial_balance

        if peak <= Decimal("0"):
            return Decimal("0")

        drawdown = self.drawdown_from_equity(equity)

        return (drawdown / peak) * Decimal("100")

    @property
    def drawdown(self) -> Decimal:
        """
        Drawdown using current account equity.
        """

        return self.drawdown_from_equity(self.equity)

    @property
    def drawdown_percent(self) -> Decimal:
        """Percentage drawdown using current account equity."""

        return self.drawdown_percent_from_equity(self.equity)

    # ------------------------------------------------------------------
    # MARGIN MANAGEMENT
    # ------------------------------------------------------------------

    def reserve_margin(
        self,
        position_id: UUID,
        margin: Decimal,
    ) -> None:
        """
        Reserve margin for an open position.

        The margin amount must be calculated by the execution/risk layer.
        This portfolio method only records the resulting reservation.
        """

        position = self.get_position(position_id)

        if position.status != BacktestPositionStatus.OPEN:
            raise BacktestPortfolioError(
                "Margin can only be reserved for an open position."
            )

        if position_id in self._reserved_margin_by_position:
            raise BacktestPortfolioError(
                f"Margin is already reserved for position '{position_id}'."
            )

        normalized_margin = self._validate_margin_amount(margin)

        if normalized_margin <= Decimal("0"):
            raise BacktestPortfolioError("Reserved margin must be greater than zero.")

        projected_margin = self.margin + normalized_margin
        projected_free_margin = self.equity - projected_margin

        if projected_free_margin < Decimal("0"):
            raise BacktestInsufficientFundsError(
                "Insufficient free margin to reserve "
                f"{normalized_margin} for position '{position_id}'. "
                f"Current equity: {self.equity}, "
                f"used margin: {self.margin}, "
                f"required margin: {normalized_margin}."
            )

        self._reserved_margin_by_position[position_id] = normalized_margin

    def release_margin(
        self,
        position_id: UUID,
    ) -> Decimal:
        """
        Release margin reserved for a position.

        Returns the released margin.

        It is valid to release zero margin for a position that was
        opened before margin tracking was introduced.
        """

        return self._reserved_margin_by_position.pop(
            position_id,
            Decimal("0"),
        )

    def reserved_margin_for_position(
        self,
        position_id: UUID,
    ) -> Decimal:
        """Return margin currently reserved for one position."""

        return self._reserved_margin_by_position.get(
            position_id,
            Decimal("0"),
        )

    # ------------------------------------------------------------------
    # POSITION MANAGEMENT
    # ------------------------------------------------------------------

    def add_position(
        self,
        position: BacktestPosition,
        reserved_margin: Decimal = Decimal("0"),
    ) -> None:
        """
        Register a newly opened position.

        ``reserved_margin`` is optional for backward compatibility with
        existing callers. New execution paths should provide the actual
        margin required by the simulated broker/account.

        Positions from any strategy and any supported symbol may be
        stored in this shared account portfolio.
        """

        if position.account_id != self.account_id:
            raise BacktestPortfolioError(
                "Position account does not match portfolio account."
            )

        if position.position_id in self.positions:
            raise BacktestPortfolioError(
                f"Position '{position.position_id}' already exists."
            )

        if position.status != BacktestPositionStatus.OPEN:
            raise BacktestPortfolioError(
                "Only open positions can be added to the portfolio."
            )

        normalized_margin = self._validate_margin_amount(
            reserved_margin,
        )

        if normalized_margin > Decimal("0"):
            projected_margin = self.margin + normalized_margin
            projected_free_margin = self.equity - projected_margin

            if projected_free_margin < Decimal("0"):
                raise BacktestInsufficientFundsError(
                    "Insufficient free margin to open position. "
                    f"Current equity: {self.equity}, "
                    f"current margin: {self.margin}, "
                    f"required margin: {normalized_margin}."
                )

            self._reserved_margin_by_position[position.position_id] = normalized_margin

        self.positions[position.position_id] = position

    def get_position(
        self,
        position_id: UUID,
    ) -> BacktestPosition:
        """Retrieve a position by ID."""

        try:
            return self.positions[position_id]
        except KeyError as exc:
            raise BacktestPositionNotFoundError(
                f"Backtest position '{position_id}' was not found."
            ) from exc

    def close_position(
        self,
        position_id: UUID,
        exit_price: Decimal,
        closed_at: datetime | None = None,
        exit_reason: str | None = None,
        contract_size: Decimal = Decimal("1"),
        commission: Decimal = Decimal("0"),
        swap: Decimal = Decimal("0"),
    ) -> BacktestPosition:
        """
        Close an existing position and update account balance.

        ``BacktestPosition.close()`` calculates gross realized P&L and
        stores commission/swap on the position.

        The portfolio applies the position's resulting
        ``net_realized_pnl`` exactly once.

        After the position closes, any margin reserved for it is released.
        """

        position = self.get_position(position_id)

        if position.status != BacktestPositionStatus.OPEN:
            raise BacktestPortfolioError(f"Position '{position_id}' is already closed.")

        close_timestamp = closed_at or self.current_time

        gross_pnl = position.close(
            exit_price=Decimal(str(exit_price)),
            closed_at=close_timestamp,
            exit_reason=exit_reason,
            contract_size=Decimal(str(contract_size)),
            commission=Decimal(str(commission)),
            swap=Decimal(str(swap)),
        )

        net_pnl = position.net_realized_pnl

        # Defensive fallback for compatibility with position
        # implementations that may not expose the property.
        if net_pnl is None:
            net_pnl = gross_pnl - Decimal(str(commission)) + Decimal(str(swap))

        self.balance += net_pnl
        self.realized_pnl += net_pnl

        self.commission_paid += Decimal(str(commission))
        self.swap_paid += Decimal(str(swap))

        # Closing a position realizes its P&L. Any previously cached
        # unrealized P&L belonging to the position is no longer valid.
        self._unrealized_pnl = self._unrealized_pnl - (gross_pnl)

        if self._unrealized_pnl < Decimal("0"):
            # The subtraction above is only a defensive compatibility
            # measure because the normal backtest flow marks the portfolio
            # before closure. Recalculate to zero rather than allowing a
            # stale negative cache to survive.
            self._unrealized_pnl = Decimal("0")

        # The position's margin is released only after the close succeeds.
        self.release_margin(position_id)

        if close_timestamp is not None:
            self.current_time = self._normalize_datetime(close_timestamp)

        self._update_peak_equity(self.equity)

        return position

    # ------------------------------------------------------------------
    # ACCOUNT SNAPSHOT
    # ------------------------------------------------------------------

    def snapshot(
        self,
        prices: dict[str, Decimal] | None = None,
        contract_sizes: dict[str, Decimal] | None = None,
    ) -> dict[str, Any]:
        """
        Return a serializable account snapshot.

        When prices are supplied, equity and unrealized P&L are
        recalculated across the entire multi-strategy portfolio.

        When prices are omitted, the most recently marked unrealized P&L
        is retained.
        """

        if prices is not None:
            unrealized = self.total_unrealized_pnl(
                prices=prices,
                contract_sizes=contract_sizes,
            )

            self._unrealized_pnl = unrealized
        else:
            unrealized = self._unrealized_pnl

        equity = self.balance + unrealized

        self._update_peak_equity(equity)

        drawdown = self.drawdown_from_equity(equity)

        margin = self.margin
        free_margin = equity - margin

        return {
            "account_id": str(self.account_id),
            "initial_balance": self.initial_balance,
            "balance": self.balance,
            "equity": equity,
            "realized_pnl": self.realized_pnl,
            "unrealized_pnl": unrealized,
            "total_pnl": self.balance - self.initial_balance,
            "commission_paid": self.commission_paid,
            "swap_paid": self.swap_paid,
            "margin": margin,
            "free_margin": free_margin,
            "margin_level": (
                (equity / margin) * Decimal("100") if margin > Decimal("0") else None
            ),
            "open_positions": self.open_position_count,
            "closed_positions": self.closed_position_count,
            "peak_equity": self.peak_equity,
            "drawdown": drawdown,
            "drawdown_percent": (
                (drawdown / self.peak_equity) * Decimal("100")
                if self.peak_equity and self.peak_equity > Decimal("0")
                else Decimal("0")
            ),
            "current_time": self.current_time,
        }

    # ------------------------------------------------------------------
    # STRATEGY / SYMBOL ATTRIBUTION
    # ------------------------------------------------------------------

    def positions_for_strategy(
        self,
        strategy_id: str,
    ) -> list[BacktestPosition]:
        """
        Return positions belonging to one strategy.

        The account remains shared; this method is only for attribution
        and reporting.
        """

        return [
            position
            for position in self.positions.values()
            if position.strategy_id == strategy_id
        ]

    def positions_for_symbol(
        self,
        symbol: str,
    ) -> list[BacktestPosition]:
        """Return positions belonging to one symbol."""

        normalized_symbol = self._normalize_symbol(symbol)

        return [
            position
            for position in self.positions.values()
            if self._normalize_symbol(position.symbol) == normalized_symbol
        ]

    # ------------------------------------------------------------------
    # INTERNAL
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_margin_amount(
        margin: Decimal,
    ) -> Decimal:
        """Normalize and validate a margin amount."""

        normalized_margin = Decimal(str(margin))

        if normalized_margin < Decimal("0"):
            raise ValueError("Margin cannot be negative.")

        if not normalized_margin.is_finite():
            raise ValueError("Margin must be finite.")

        return normalized_margin

    def _update_peak_equity(
        self,
        equity: Decimal,
    ) -> None:
        equity = Decimal(str(equity))

        if self.peak_equity is None or equity > self.peak_equity:
            self.peak_equity = equity

    @staticmethod
    def _normalize_symbol(symbol: str) -> str:
        normalized = str(symbol).strip().upper()

        if not normalized:
            raise ValueError("Symbol cannot be empty.")

        return normalized

    @classmethod
    def _normalize_contract_sizes(
        cls,
        contract_sizes: dict[str, Decimal] | None,
    ) -> dict[str, Decimal]:
        if not contract_sizes:
            return {}

        normalized: dict[str, Decimal] = {}

        for symbol, value in contract_sizes.items():
            size = Decimal(str(value))

            if size <= Decimal("0"):
                raise ValueError(f"Contract size for '{symbol}' must be positive.")

            if not size.is_finite():
                raise ValueError(f"Contract size for '{symbol}' must be finite.")

            normalized[cls._normalize_symbol(symbol)] = size

        return normalized

    @staticmethod
    def _normalize_datetime(value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)

        return value.astimezone(timezone.utc)
