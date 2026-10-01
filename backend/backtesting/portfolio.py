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

        if self.peak_equity is None:
            self.peak_equity = self.balance
        else:
            self.peak_equity = Decimal(str(self.peak_equity))

        self.created_at = self._normalize_datetime(self.created_at)

        if self.current_time is not None:
            self.current_time = self._normalize_datetime(self.current_time)

    # ------------------------------------------------------------------
    # ACCOUNT STATE
    # ------------------------------------------------------------------

    @property
    def equity(self) -> Decimal:
        """
        Current account equity.

        Equity is:

            balance + unrealized P&L

        The portfolio cannot calculate unrealized P&L without current
        market prices, so callers that need a marked-to-market equity
        value should use ``mark_to_market()`` or ``snapshot()``.

        If no prices are available, the property returns balance.
        """

        return self.balance

    @property
    def free_margin(self) -> Decimal:
        """
        Current simulated free margin.

        Margin reservation is deliberately kept outside this portfolio
        until symbol-specific margin requirements are introduced.

        For the current backtest model, free margin is therefore the
        account equity represented by ``balance``.
        """

        return self.balance

    @property
    def margin(self) -> Decimal:
        """
        Current simulated margin usage.

        Margin accounting is currently delegated to the risk layer.
        """

        return Decimal("0")

    @property
    def margin_level(self) -> Decimal | None:
        """
        Current simulated margin level.

        Returns ``None`` when no margin is reserved.
        """

        margin = self.margin

        if margin <= Decimal("0"):
            return None

        return (self.balance / margin) * Decimal("100")

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

        normalized_contract_sizes = self._normalize_contract_sizes(contract_sizes)

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

        Returns the resulting account equity.
        """

        if timestamp is not None:
            self.current_time = self._normalize_datetime(timestamp)

        unrealized = self.total_unrealized_pnl(
            prices=prices,
            contract_sizes=contract_sizes,
        )

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

        Unrealized P&L is deliberately excluded because it is not yet
        reflected in account balance.
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
        Drawdown using the current realized account balance.

        For a marked-to-market drawdown use ``snapshot()`` or
        ``mark_to_market()`` with current prices.
        """

        return self.drawdown_from_equity(self.balance)

    @property
    def drawdown_percent(self) -> Decimal:
        """Percentage drawdown using current account balance."""

        return self.drawdown_percent_from_equity(self.balance)

    # ------------------------------------------------------------------
    # POSITION MANAGEMENT
    # ------------------------------------------------------------------

    def add_position(
        self,
        position: BacktestPosition,
    ) -> None:
        """
        Register a newly opened position.

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

        The portfolio then applies the position's resulting
        ``net_realized_pnl`` exactly once.

        This is important because transaction costs must not be
        subtracted twice.
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

        # ``BacktestPosition.close()`` stores the net realized P&L
        # separately from the gross P&L.
        net_pnl = position.net_realized_pnl

        # Defensive fallback for compatibility with position
        # implementations that may not expose the property.
        if net_pnl is None:
            net_pnl = gross_pnl - Decimal(str(commission)) + Decimal(str(swap))

        self.balance += net_pnl
        self.realized_pnl += net_pnl

        self.commission_paid += Decimal(str(commission))
        self.swap_paid += Decimal(str(swap))

        if close_timestamp is not None:
            self.current_time = self._normalize_datetime(close_timestamp)

        self._update_peak_equity(self.balance)

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
        calculated across the entire multi-strategy portfolio.

        When prices are omitted, equity falls back to balance.
        """

        unrealized = Decimal("0")

        if prices is not None:
            unrealized = self.total_unrealized_pnl(
                prices=prices,
                contract_sizes=contract_sizes,
            )

        equity = self.balance + unrealized

        self._update_peak_equity(equity)

        drawdown = self.drawdown_from_equity(equity)

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
            "margin": self.margin,
            "free_margin": equity,
            "margin_level": self.margin_level,
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

            normalized[cls._normalize_symbol(symbol)] = size

        return normalized

    @staticmethod
    def _normalize_datetime(value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)

        return value.astimezone(timezone.utc)
