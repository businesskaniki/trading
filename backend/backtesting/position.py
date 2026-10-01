"""Position domain model for AQE backtesting."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from enum import StrEnum
from uuid import UUID, uuid4

# ======================================================================
# ENUMS
# ======================================================================


class BacktestPositionSide(StrEnum):
    """Directional side of a simulated position."""

    LONG = "LONG"
    SHORT = "SHORT"


class BacktestPositionStatus(StrEnum):
    """Lifecycle state of a simulated position."""

    OPEN = "OPEN"
    CLOSED = "CLOSED"


# ======================================================================
# POSITION
# ======================================================================


@dataclass(slots=True)
class BacktestPosition:
    """
    Pure backtesting position domain object.

    A BacktestPosition represents one simulated position belonging to
    the shared account-level backtest portfolio.

    The object deliberately has no dependency on:

        - SQLAlchemy
        - PostgreSQL
        - Redis
        - MT5
        - broker position models
        - strategy runtime classes
        - RiskEngine

    Strategy attribution is stored as simple identifiers so a shared
    account-level backtest can report which strategy opened a position.

    Accounting convention
    ---------------------

    ``realized_pnl`` is gross price P&L.

    ``commission`` is the total commission paid over the complete
    position lifecycle:

        entry commission + exit commission

    ``swap`` represents the accumulated financing/swap adjustment and
    may be positive or negative.

    Therefore:

        net_realized_pnl =
            realized_pnl - commission + swap
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

    # Gross price P&L before transaction costs.
    realized_pnl: Decimal = Decimal("0")

    # Total commission for the complete position lifecycle.
    #
    # This includes both:
    #
    #     entry commission
    #     + exit commission
    #
    commission: Decimal = Decimal("0")

    # Accumulated swap/financing adjustment.
    swap: Decimal = Decimal("0")

    exit_reason: str | None = None

    # ==================================================================
    # FACTORY
    # ==================================================================

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
        entry_commission: Decimal = Decimal("0"),
    ) -> BacktestPosition:
        """
        Create a new OPEN simulated position.

        ``entry_commission`` is recorded immediately because the
        commission is incurred when the entry fill occurs.

        The position's ``commission`` field therefore already contains
        the entry cost while the position is OPEN. When the position is
        subsequently closed, the exit commission is added to that
        existing amount.
        """

        cls._validate_account_id(
            account_id,
        )

        normalized_symbol = cls._normalize_symbol(
            symbol,
        )

        normalized_side = cls._validate_side(
            side,
        )

        normalized_volume = cls._validate_positive_decimal(
            volume,
            "Position volume",
        )

        normalized_entry_price = cls._validate_positive_decimal(
            entry_price,
            "Entry price",
        )

        normalized_stop_loss = cls._validate_optional_positive_decimal(
            stop_loss,
            "Stop loss",
        )

        normalized_take_profit = cls._validate_optional_positive_decimal(
            take_profit,
            "Take profit",
        )

        normalized_entry_commission = cls._validate_non_negative_decimal(
            entry_commission,
            "Entry commission",
        )

        timestamp = cls._normalize_timestamp(
            opened_at if opened_at is not None else datetime.now(timezone.utc)
        )

        return cls(
            position_id=uuid4(),
            account_id=account_id,
            symbol=normalized_symbol,
            side=normalized_side,
            volume=normalized_volume,
            entry_price=normalized_entry_price,
            opened_at=timestamp,
            stop_loss=normalized_stop_loss,
            take_profit=normalized_take_profit,
            strategy_id=cls._normalize_strategy(
                strategy_id,
            ),
            strategy_name=cls._normalize_strategy(
                strategy_name,
            ),
            commission=normalized_entry_commission,
        )

    # ==================================================================
    # STATE
    # ==================================================================

    @property
    def is_open(self) -> bool:
        """Return whether the position is currently open."""

        return self.status == BacktestPositionStatus.OPEN

    @property
    def is_closed(self) -> bool:
        """Return whether the position has been closed."""

        return self.status == BacktestPositionStatus.CLOSED

    # ==================================================================
    # ACCOUNTING
    # ==================================================================

    @property
    def net_realized_pnl(self) -> Decimal:
        """
        Return realized net P&L after commission and swap.

        Convention:

            net = gross realized P&L
                  - total commission
                  + swap

        Commission is stored as a positive cost magnitude.

        ``commission`` includes both entry and exit commission.
        """

        return self.realized_pnl - self.commission + self.swap

    # ==================================================================
    # UNREALIZED P&L
    # ==================================================================

    def unrealized_pnl(
        self,
        current_price: Decimal,
        contract_size: Decimal = Decimal("1"),
    ) -> Decimal:
        """
        Calculate current gross unrealized P&L.

        LONG:

            (current_price - entry_price)
                * volume
                * contract_size

        SHORT:

            (entry_price - current_price)
                * volume
                * contract_size
        """

        current = self._validate_positive_decimal(
            current_price,
            "Current price",
        )

        contract = self._validate_positive_decimal(
            contract_size,
            "Contract size",
        )

        if self.side == BacktestPositionSide.LONG:
            price_difference = current - self.entry_price

        elif self.side == BacktestPositionSide.SHORT:
            price_difference = self.entry_price - current

        else:
            raise ValueError(f"Unsupported position side: {self.side!r}")

        return price_difference * self.volume * contract

    # ==================================================================
    # CLOSE
    # ==================================================================

    def close(
        self,
        *,
        exit_price: Decimal,
        closed_at: datetime | None = None,
        exit_reason: str | None = None,
        contract_size: Decimal = Decimal("1"),
        commission: Decimal = Decimal("0"),
        swap: Decimal = Decimal("0"),
    ) -> Decimal:
        """
        Close the position and calculate gross realized P&L.

        Returns:
            Gross realized price P&L before commission and swap.

        Commission handling
        -------------------

        ``self.commission`` already contains any commission incurred
        when the position was opened.

        The commission supplied here represents the commission incurred
        by the closing transaction.

        Therefore the closing operation accumulates commission:

            total_commission =
                existing_commission + exit_commission

        It does NOT replace the entry commission.

        Swap is accumulated in the same manner so repeated accounting
        adjustments cannot silently overwrite previously recorded swap.
        """

        if self.is_closed:
            raise ValueError(f"Position {self.position_id} is already closed.")

        normalized_exit_price = self._validate_positive_decimal(
            exit_price,
            "Exit price",
        )

        normalized_contract_size = self._validate_positive_decimal(
            contract_size,
            "Contract size",
        )

        normalized_commission = self._validate_non_negative_decimal(
            commission,
            "Commission",
        )

        normalized_swap = self._validate_decimal(
            swap,
            "Swap",
        )

        timestamp = self._normalize_timestamp(
            closed_at if closed_at is not None else datetime.now(timezone.utc)
        )

        if timestamp < self.opened_at:
            raise ValueError("Position closed_at cannot be before opened_at.")

        gross_pnl = self._calculate_pnl(
            exit_price=normalized_exit_price,
            contract_size=normalized_contract_size,
        )

        self.exit_price = normalized_exit_price
        self.closed_at = timestamp
        self.status = BacktestPositionStatus.CLOSED

        self.realized_pnl = gross_pnl

        # IMPORTANT:
        #
        # The position may already contain entry commission.
        # Closing adds exit commission rather than replacing it.
        self.commission += normalized_commission

        # Swap is accumulated rather than overwritten.
        self.swap += normalized_swap

        self.exit_reason = self._normalize_exit_reason(
            exit_reason,
        )

        return gross_pnl

    # ==================================================================
    # P&L
    # ==================================================================

    def _calculate_pnl(
        self,
        *,
        exit_price: Decimal,
        contract_size: Decimal,
    ) -> Decimal:
        """Calculate gross realized price P&L."""

        if self.side == BacktestPositionSide.LONG:
            price_difference = exit_price - self.entry_price

        elif self.side == BacktestPositionSide.SHORT:
            price_difference = self.entry_price - exit_price

        else:
            raise ValueError(f"Unsupported position side: {self.side!r}")

        return price_difference * self.volume * contract_size

    # ==================================================================
    # DIRECT-CONSTRUCTION VALIDATION
    # ==================================================================

    def __post_init__(self) -> None:
        """
        Normalize and validate directly constructed positions.

        Most callers should prefer BacktestPosition.open(), but the
        dataclass remains safe when instantiated directly.
        """

        self._validate_account_id(
            self.account_id,
        )

        self.symbol = self._normalize_symbol(
            self.symbol,
        )

        self.side = self._validate_side(
            self.side,
        )

        self.volume = self._validate_positive_decimal(
            self.volume,
            "Position volume",
        )

        self.entry_price = self._validate_positive_decimal(
            self.entry_price,
            "Entry price",
        )

        self.opened_at = self._normalize_timestamp(
            self.opened_at,
        )

        self.stop_loss = self._validate_optional_positive_decimal(
            self.stop_loss,
            "Stop loss",
        )

        self.take_profit = self._validate_optional_positive_decimal(
            self.take_profit,
            "Take profit",
        )

        if self.exit_price is not None:
            self.exit_price = self._validate_positive_decimal(
                self.exit_price,
                "Exit price",
            )

        if self.closed_at is not None:
            self.closed_at = self._normalize_timestamp(
                self.closed_at,
            )

            if self.closed_at < self.opened_at:
                raise ValueError("closed_at cannot be before opened_at.")

        if not isinstance(
            self.status,
            BacktestPositionStatus,
        ):
            try:
                self.status = BacktestPositionStatus(
                    str(self.status).strip().upper(),
                )

            except ValueError as exc:
                raise ValueError(f"Invalid position status: {self.status!r}") from exc

        self.realized_pnl = self._validate_decimal(
            self.realized_pnl,
            "Realized P&L",
        )

        self.commission = self._validate_non_negative_decimal(
            self.commission,
            "Commission",
        )

        self.swap = self._validate_decimal(
            self.swap,
            "Swap",
        )

        self.strategy_id = self._normalize_strategy(
            self.strategy_id,
        )

        self.strategy_name = self._normalize_strategy(
            self.strategy_name,
        )

        self.exit_reason = self._normalize_exit_reason(
            self.exit_reason,
        )

        # --------------------------------------------------------------
        # OPEN STATE
        # --------------------------------------------------------------

        if self.status == BacktestPositionStatus.OPEN:
            if self.exit_price is not None:
                raise ValueError("An OPEN position cannot have an exit_price.")

            if self.closed_at is not None:
                raise ValueError("An OPEN position cannot have closed_at.")

            if self.exit_reason is not None:
                raise ValueError("An OPEN position cannot have an exit_reason.")

            if self.realized_pnl != Decimal("0"):
                raise ValueError("An OPEN position cannot have realized P&L.")

        # --------------------------------------------------------------
        # CLOSED STATE
        # --------------------------------------------------------------

        if self.status == BacktestPositionStatus.CLOSED:
            if self.exit_price is None:
                raise ValueError("A CLOSED position must have an exit_price.")

            if self.closed_at is None:
                raise ValueError("A CLOSED position must have closed_at.")

    # ==================================================================
    # VALIDATION HELPERS
    # ==================================================================

    @staticmethod
    def _validate_account_id(
        account_id: UUID,
    ) -> None:
        if not isinstance(
            account_id,
            UUID,
        ):
            raise ValueError("account_id must be a UUID.")

    @staticmethod
    def _normalize_symbol(
        symbol: str,
    ) -> str:
        if not isinstance(
            symbol,
            str,
        ):
            raise ValueError("Position symbol must be a string.")

        normalized = symbol.strip().upper()

        if not normalized:
            raise ValueError("Position symbol cannot be empty.")

        return normalized

    @staticmethod
    def _validate_side(
        side: BacktestPositionSide,
    ) -> BacktestPositionSide:
        if isinstance(
            side,
            BacktestPositionSide,
        ):
            return side

        try:
            return BacktestPositionSide(
                str(side).strip().upper(),
            )

        except ValueError as exc:
            raise ValueError(f"Invalid position side: {side!r}") from exc

    @staticmethod
    def _validate_positive_decimal(
        value: Decimal,
        field_name: str,
    ) -> Decimal:
        normalized = BacktestPosition._validate_decimal(
            value,
            field_name,
        )

        if normalized <= Decimal("0"):
            raise ValueError(f"{field_name} must be greater than zero.")

        return normalized

    @staticmethod
    def _validate_non_negative_decimal(
        value: Decimal,
        field_name: str,
    ) -> Decimal:
        normalized = BacktestPosition._validate_decimal(
            value,
            field_name,
        )

        if normalized < Decimal("0"):
            raise ValueError(f"{field_name} cannot be negative.")

        return normalized

    @staticmethod
    def _validate_decimal(
        value: Decimal,
        field_name: str,
    ) -> Decimal:
        if value is None:
            raise ValueError(f"{field_name} cannot be None.")

        if isinstance(
            value,
            Decimal,
        ):
            normalized = value

        else:
            try:
                normalized = Decimal(
                    str(value),
                )

            except Exception as exc:
                raise ValueError(f"{field_name} must be a valid decimal.") from exc

        if not normalized.is_finite():
            raise ValueError(f"{field_name} must be finite.")

        return normalized

    @classmethod
    def _validate_optional_positive_decimal(
        cls,
        value: Decimal | None,
        field_name: str,
    ) -> Decimal | None:
        if value is None:
            return None

        return cls._validate_positive_decimal(
            value,
            field_name,
        )

    @staticmethod
    def _normalize_timestamp(
        value: datetime,
    ) -> datetime:
        if not isinstance(
            value,
            datetime,
        ):
            raise ValueError("Position timestamp must be a datetime.")

        if value.tzinfo is None:
            return value.replace(
                tzinfo=timezone.utc,
            )

        return value.astimezone(
            timezone.utc,
        )

    @staticmethod
    def _normalize_strategy(
        value: str | None,
    ) -> str | None:
        if value is None:
            return None

        if not isinstance(
            value,
            str,
        ):
            raise ValueError("Strategy identifier/name must be a string.")

        normalized = value.strip()

        return normalized or None

    @staticmethod
    def _normalize_exit_reason(
        value: str | None,
    ) -> str | None:
        if value is None:
            return None

        if not isinstance(
            value,
            str,
        ):
            raise ValueError("Exit reason must be a string.")

        normalized = value.strip().upper()

        return normalized or None
