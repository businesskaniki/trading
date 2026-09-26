from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

from .position import (
    BacktestPosition,
    BacktestPositionSide,
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
    Portfolio state for a single backtest account.

    The portfolio is deliberately independent from:
    - the Risk Engine
    - the Strategy Engine
    - the live broker
    - PostgreSQL

    It represents the simulated account state used by the
    backtesting execution environment.
    """

    account_id: UUID

    initial_balance: Decimal

    balance: Decimal | None = None

    positions: dict[UUID, BacktestPosition] = field(default_factory=dict)

    realized_pnl: Decimal = Decimal("0")
    commission_paid: Decimal = Decimal("0")
    swap_paid: Decimal = Decimal("0")

    peak_equity: Decimal | None = None

    created_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    current_time: datetime | None = None

    def __post_init__(self) -> None:
        if self.initial_balance < Decimal("0"):
            raise ValueError("Initial balance cannot be negative.")

        if self.balance is None:
            self.balance = self.initial_balance

        if self.balance < Decimal("0"):
            raise ValueError("Balance cannot be negative.")

        if self.peak_equity is None:
            self.peak_equity = self.balance

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

        Equity = balance + unrealized P&L of all open positions.
        """

        unrealized = self.total_unrealized_pnl()

        equity = self.balance + unrealized

        if self.peak_equity is None or equity > self.peak_equity:
            self.peak_equity = equity

        return equity

    @property
    def free_margin(self) -> Decimal:
        """
        Backtest free margin.

        Margin reservation is intentionally handled by the
        backtest broker/execution layer rather than the portfolio
        itself. For the initial engine this represents equity.

        The Risk Engine remains responsible for margin validation.
        """

        return self.equity

    @property
    def margin(self) -> Decimal:
        """
        Current simulated margin usage.

        Margin accounting will be introduced when the BacktestBroker
        applies symbol-specific margin requirements.
        """

        return Decimal("0")

    @property
    def margin_level(self) -> Decimal | None:
        """
        Simulated margin level.

        Returns None when no margin is currently used.
        """

        if self.margin <= Decimal("0"):
            return None

        return (self.equity / self.margin) * Decimal("100")

    @property
    def open_positions(self) -> list[BacktestPosition]:
        return [
            position
            for position in self.positions.values()
            if position.status == BacktestPositionStatus.OPEN
        ]

    @property
    def closed_positions(self) -> list[BacktestPosition]:
        return [
            position
            for position in self.positions.values()
            if position.status == BacktestPositionStatus.CLOSED
        ]

    @property
    def open_position_count(self) -> int:
        return len(self.open_positions)

    # ------------------------------------------------------------------
    # P&L
    # ------------------------------------------------------------------

    def total_unrealized_pnl(
        self,
        prices: dict[str, Decimal] | None = None,
        contract_sizes: dict[str, Decimal] | None = None,
    ) -> Decimal:
        """
        Calculate unrealized P&L for all open positions.

        Parameters
        ----------
        prices:
            Optional symbol -> current price mapping.

        contract_sizes:
            Optional symbol -> contract size mapping.

        When prices are omitted, positions must have an externally
        supplied current price in the future market layer. For now,
        the method requires prices for open positions.
        """

        if not self.open_positions:
            return Decimal("0")

        if prices is None:
            raise ValueError(
                "Current prices are required to calculate unrealized P&L."
            )

        contract_sizes = contract_sizes or {}

        total = Decimal("0")

        for position in self.open_positions:
            symbol = position.symbol

            if symbol not in prices:
                raise ValueError(
                    f"Missing current price for open position '{symbol}'."
                )

            current_price = prices[symbol]

            contract_size = contract_sizes.get(
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
        Mark all open positions to the supplied market prices.

        Returns current account equity.
        """

        if timestamp is not None:
            self.current_time = self._normalize_datetime(timestamp)

        return self.total_unrealized_pnl(
            prices=prices,
            contract_sizes=contract_sizes,
        ) + self.balance

    @property
    def total_realized_pnl(self) -> Decimal:
        return self.realized_pnl

    @property
    def total_pnl(self) -> Decimal:
        """
        Total P&L since the beginning of the backtest.

        This is based on the account balance relative to the
        initial balance.
        """

        return self.balance - self.initial_balance

    @property
    def drawdown(self) -> Decimal:
        """
        Current absolute drawdown from peak equity.
        """

        peak = self.peak_equity or self.initial_balance
        return max(Decimal("0"), peak - self.equity)

    @property
    def drawdown_percent(self) -> Decimal:
        """
        Current percentage drawdown from peak equity.
        """

        peak = self.peak_equity or self.initial_balance

        if peak <= Decimal("0"):
            return Decimal("0")

        return (self.drawdown / peak) * Decimal("100")

    # ------------------------------------------------------------------
    # POSITION MANAGEMENT
    # ------------------------------------------------------------------

    def add_position(self, position: BacktestPosition) -> None:
        """
        Register a newly opened position.
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

    def get_position(self, position_id: UUID) -> BacktestPosition:
        """
        Retrieve a position by ID.
        """

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

        The position calculates gross P&L.

        The portfolio then applies:
            net P&L = gross P&L - commission - swap

        The account balance is updated by the net P&L.
        """

        position = self.get_position(position_id)

        if position.status != BacktestPositionStatus.OPEN:
            raise BacktestPortfolioError(
                f"Position '{position_id}' is already closed."
            )

        gross_pnl = position.close(
            exit_price=exit_price,
            closed_at=closed_at or self.current_time,
            exit_reason=exit_reason,
            contract_size=contract_size,
            commission=commission,
            swap=swap,
        )

        net_pnl = gross_pnl - commission - swap

        position.realized_pnl = net_pnl

        self.balance += net_pnl
        self.realized_pnl += net_pnl
        self.commission_paid += commission
        self.swap_paid += swap

        if closed_at is not None:
            self.current_time = self._normalize_datetime(closed_at)

        self._update_peak_equity()

        return position

    # ------------------------------------------------------------------
    # ACCOUNT SNAPSHOT
    # ------------------------------------------------------------------

    def snapshot(
        self,
        prices: dict[str, Decimal] | None = None,
        contract_sizes: dict[str, Decimal] | None = None,
    ) -> dict:
        """
        Return a serializable portfolio snapshot.

        This is intentionally a plain dictionary so the backtest
        result layer can later convert it into whatever persistence
        or reporting model AQE requires.
        """

        unrealized = Decimal("0")

        if prices is not None:
            unrealized = self.total_unrealized_pnl(
                prices=prices,
                contract_sizes=contract_sizes,
            )

        equity = self.balance + unrealized

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
            "open_positions": self.open_position_count,
            "peak_equity": self.peak_equity,
            "drawdown": max(
                Decimal("0"),
                (self.peak_equity or self.initial_balance) - equity,
            ),
        }

    # ------------------------------------------------------------------
    # INTERNAL
    # ------------------------------------------------------------------

    def _update_peak_equity(self) -> None:
        equity = self.equity

        if self.peak_equity is None or equity > self.peak_equity:
            self.peak_equity = equity

    @staticmethod
    def _normalize_datetime(value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)

        return value.astimezone(timezone.utc)