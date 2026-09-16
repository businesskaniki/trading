"""Domain models for the AQE Risk Engine."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator

from strategies.core.signal import (
    OrderType,
    SignalDirection,
    SignalType,
    TradingSignal,
)

from .config import RiskConfig
from .enums import RiskDecisionStatus, RiskRejectionReason


class AccountRiskSnapshot(BaseModel):
    """Point-in-time account state used for risk evaluation."""

    model_config = ConfigDict(extra="forbid")

    account_id: UUID
    balance: Decimal = Field(ge=Decimal("0"))
    equity: Decimal = Field(ge=Decimal("0"))
    margin: Decimal = Field(default=Decimal("0"), ge=Decimal("0"))
    free_margin: Decimal = Field(default=Decimal("0"), ge=Decimal("0"))
    margin_level: Decimal | None = Field(default=None, ge=Decimal("0"))
    daily_pnl: Decimal = Decimal("0")
    peak_equity: Decimal | None = Field(default=None, ge=Decimal("0"))

    @property
    def drawdown_amount(self) -> Decimal:
        """Return the current monetary drawdown."""
        if self.peak_equity is None:
            return Decimal("0")

        return max(
            Decimal("0"),
            self.peak_equity - self.equity,
        )

    @property
    def drawdown_ratio(self) -> Decimal:
        """Return the current drawdown as a fraction of peak equity."""
        if self.peak_equity is None or self.peak_equity <= 0:
            return Decimal("0")

        return self.drawdown_amount / self.peak_equity


class PositionRiskSnapshot(BaseModel):
    """Open-position information required by the Risk Engine."""

    model_config = ConfigDict(extra="forbid")

    position_id: UUID
    account_id: UUID
    symbol: str
    strategy_id: str | None = None
    direction: SignalDirection
    quantity: Decimal = Field(gt=Decimal("0"))
    entry_price: Decimal = Field(gt=Decimal("0"))
    current_price: Decimal = Field(gt=Decimal("0"))
    stop_loss: Decimal | None = Field(default=None, gt=Decimal("0"))
    take_profit: Decimal | None = Field(default=None, gt=Decimal("0"))
    unrealized_pnl: Decimal = Decimal("0")
    risk_amount: Decimal = Field(default=Decimal("0"), ge=Decimal("0"))

    @field_validator("symbol")
    @classmethod
    def normalize_symbol(cls, value: str) -> str:
        """Normalize position symbol."""
        value = value.strip().upper()

        if not value:
            raise ValueError("symbol cannot be empty")

        return value


class SymbolRiskConstraints(BaseModel):
    """Broker/symbol constraints needed to construct a valid order."""

    model_config = ConfigDict(extra="forbid")

    symbol: str
    contract_size: Decimal = Field(gt=Decimal("0"))
    tick_size: Decimal = Field(gt=Decimal("0"))
    tick_value: Decimal = Field(gt=Decimal("0"))
    volume_min: Decimal = Field(gt=Decimal("0"))
    volume_max: Decimal = Field(gt=Decimal("0"))
    volume_step: Decimal = Field(gt=Decimal("0"))
    margin_rate: Decimal = Field(default=Decimal("1"), gt=Decimal("0"))

    @field_validator("symbol")
    @classmethod
    def normalize_symbol(cls, value: str) -> str:
        """Normalize symbol."""
        value = value.strip().upper()

        if not value:
            raise ValueError("symbol cannot be empty")

        return value

    @field_validator("volume_max")
    @classmethod
    def validate_volume_range(
        cls,
        value: Decimal,
        info,
    ) -> Decimal:
        """Ensure maximum volume is not below minimum volume."""

        volume_min = info.data.get("volume_min")

        if volume_min is not None and value < volume_min:
            raise ValueError("volume_max cannot be less than volume_min")

        return value


class MarketPricing(BaseModel):
    """
    Current market pricing used by the Risk Engine.

    Bid is used as the executable reference price for short entries.
    Ask is used as the executable reference price for long entries.
    """

    model_config = ConfigDict(extra="forbid")

    bid: Decimal = Field(gt=Decimal("0"))
    ask: Decimal = Field(gt=Decimal("0"))

    @field_validator("ask")
    @classmethod
    def validate_spread(
        cls,
        value: Decimal,
        info,
    ) -> Decimal:
        """Ensure ask is not below bid."""

        bid = info.data.get("bid")

        if bid is not None and value < bid:
            raise ValueError("ask cannot be less than bid")

        return value

    @property
    def mid(self) -> Decimal:
        """Return the bid/ask midpoint."""
        return (self.bid + self.ask) / Decimal("2")


class RiskContext(BaseModel):
    """Complete snapshot consumed during risk evaluation."""

    model_config = ConfigDict(extra="forbid")

    account: AccountRiskSnapshot
    positions: list[PositionRiskSnapshot] = Field(
        default_factory=list,
    )
    symbol_constraints: SymbolRiskConstraints
    market: MarketPricing
    config: RiskConfig
    signal: TradingSignal

    # Populated by RiskEngine after calculating the proposed order size.
    proposed_position_size: Decimal | None = Field(
        default=None,
        gt=Decimal("0"),
    )

    @property
    def open_position_count(self) -> int:
        """Return the number of currently open positions."""
        return len(self.positions)

    @property
    def symbol_position_count(self) -> int:
        """Return the number of positions currently open for the signal symbol."""

        signal_symbol = self.signal.symbol.strip().upper()

        return sum(position.symbol == signal_symbol for position in self.positions)

    @property
    def portfolio_risk(self) -> Decimal:
        """Return total current monetary risk."""
        return sum(
            (position.risk_amount for position in self.positions),
            Decimal("0"),
        )

    @property
    def strategy_risk(self) -> Decimal:
        """Return current monetary risk for the signal strategy."""
        return sum(
            (
                position.risk_amount
                for position in self.positions
                if position.strategy_id == self.signal.strategy_id
            ),
            Decimal("0"),
        )

    @property
    def entry_price(self) -> Decimal:
        """
        Resolve the price used for the proposed trade.

        An explicitly supplied signal entry price takes precedence.
        Otherwise:

        LONG  -> ASK
        SHORT -> BID
        """

        if self.signal.entry_price is not None:
            if self.signal.entry_price <= Decimal("0"):
                raise ValueError("Signal entry price must be greater than zero.")

            return self.signal.entry_price

        if self.signal.direction == SignalDirection.LONG:
            return self.market.ask

        return self.market.bid


class RiskDecision(BaseModel):
    """Final decision produced by the Risk Engine."""

    model_config = ConfigDict(extra="forbid")

    decision_id: UUID = Field(default_factory=uuid4)
    status: RiskDecisionStatus
    signal_id: UUID
    account_id: UUID
    strategy_id: str
    strategy_name: str
    symbol: str
    direction: SignalDirection
    signal_type: SignalType
    order_type: OrderType
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    risk_amount: Decimal = Field(
        default=Decimal("0"),
        ge=Decimal("0"),
    )
    position_size: Decimal | None = Field(
        default=None,
        ge=Decimal("0"),
    )
    entry_price: Decimal | None = Field(
        default=None,
        gt=Decimal("0"),
    )
    stop_loss: Decimal | None = Field(
        default=None,
        gt=Decimal("0"),
    )
    take_profit: Decimal | None = Field(
        default=None,
        gt=Decimal("0"),
    )
    risk_reward_ratio: Decimal | None = Field(
        default=None,
        ge=Decimal("0"),
    )
    rejection_reason: RiskRejectionReason | None = None
    message: str | None = None
    metadata: dict[str, Any] = Field(
        default_factory=dict,
    )

    @property
    def approved(self) -> bool:
        """Return whether the decision approved the trade."""
        return self.status == RiskDecisionStatus.APPROVED

    @property
    def rejected(self) -> bool:
        """Return whether the decision rejected the trade."""
        return self.status == RiskDecisionStatus.REJECTED
