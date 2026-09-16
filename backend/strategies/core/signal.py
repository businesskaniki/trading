
"""Trading signal contract produced by AQE strategies."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .enums import OrderType, SignalDirection, SignalType, Timeframe
from .exceptions import InvalidSignalError


class TradingSignal(BaseModel):
    """
    Normalized trading signal produced by a strategy.

    A TradingSignal expresses trading intent. It does not determine
    position size, account risk, or broker execution details. Those
    responsibilities belong to the Risk and Execution Engines.
    """

    model_config = ConfigDict(
        extra="allow",
        validate_assignment=True,
    )

    signal_id: UUID = Field(default_factory=uuid4)

    strategy_id: str = Field(
        min_length=1,
        max_length=128,
    )

    strategy_name: str = Field(
        min_length=1,
        max_length=128,
    )

    symbol: str = Field(
        min_length=1,
        max_length=64,
    )

    timeframe: Timeframe

    signal_type: SignalType

    direction: SignalDirection

    order_type: OrderType

    timestamp: datetime

    entry_price: float | None = Field(
        default=None,
        gt=0,
    )

    stop_loss: float | None = Field(
        default=None,
        gt=0,
    )

    take_profit: float | None = Field(
        default=None,
        gt=0,
    )

    confidence: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
    )

    reason: str = Field(
        min_length=1,
        max_length=2000,
    )

    metadata: dict[str, Any] = Field(
        default_factory=dict,
    )

    @field_validator("strategy_id", "strategy_name", "symbol")
    @classmethod
    def normalize_identifier(cls, value: str) -> str:
        """Normalize strategy and symbol identifiers."""

        value = value.strip()

        if not value:
            raise InvalidSignalError(
                "Strategy and symbol identifiers cannot be empty."
            )

        return value

    @field_validator("reason")
    @classmethod
    def normalize_reason(cls, value: str) -> str:
        """Normalize the human-readable signal reason."""

        value = value.strip()

        if not value:
            raise InvalidSignalError(
                "Signal reason cannot be empty."
            )

        return value

    @field_validator("timestamp")
    @classmethod
    def normalize_timestamp(cls, value: datetime) -> datetime:
        """Ensure the signal timestamp is timezone-aware UTC."""

        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)

        return value.astimezone(timezone.utc)

    @model_validator(mode="after")
    def validate_price_relationships(self) -> TradingSignal:
        """
        Validate stop-loss and take-profit relationships.

        For LONG signals:
            stop_loss < entry_price < take_profit

        For SHORT signals:
            take_profit < entry_price < stop_loss

        These directional checks are only enforced when all three
        prices are available.
        """

        if (
            self.entry_price is None
            or self.stop_loss is None
            or self.take_profit is None
        ):
            return self

        if self.direction is SignalDirection.LONG:
            if not (
                self.stop_loss
                < self.entry_price
                < self.take_profit
            ):
                raise InvalidSignalError(
                    "LONG signal requires "
                    "stop_loss < entry_price < take_profit."
                )

        elif self.direction is SignalDirection.SHORT:
            if not (
                self.take_profit
                < self.entry_price
                < self.stop_loss
            ):
                raise InvalidSignalError(
                    "SHORT signal requires "
                    "take_profit < entry_price < stop_loss."
                )

        return self

    @model_validator(mode="after")
    def validate_signal_type(self) -> TradingSignal:
        """Validate fields according to the signal type."""

        if self.signal_type is SignalType.EXIT:
            if self.order_type is OrderType.LIMIT and self.entry_price is None:
                raise InvalidSignalError(
                    "LIMIT exit signals require an entry_price."
                )

        return self

    @property
    def is_entry(self) -> bool:
        """Return True when this signal opens a position."""

        return self.signal_type is SignalType.ENTRY

    @property
    def is_exit(self) -> bool:
        """Return True when this signal closes a position."""

        return self.signal_type is SignalType.EXIT

    @property
    def is_long(self) -> bool:
        """Return True when the signal is long."""

        return self.direction is SignalDirection.LONG

    @property
    def is_short(self) -> bool:
        """Return True when the signal is short."""

        return self.direction is SignalDirection.SHORT

    @property
    def risk_distance(self) -> float | None:
        """
        Return the distance between entry and stop-loss.

        Returns None when either price is unavailable.
        """

        if self.entry_price is None or self.stop_loss is None:
            return None

        return abs(self.entry_price - self.stop_loss)

    @property
    def reward_distance(self) -> float | None:
        """
        Return the distance between entry and take-profit.

        Returns None when either price is unavailable.
        """

        if self.entry_price is None or self.take_profit is None:
            return None

        return abs(self.take_profit - self.entry_price)

    @property
    def risk_reward_ratio(self) -> float | None:
        """
        Return the reward-to-risk ratio.

        Returns None when the required prices are unavailable or
        the calculated risk is zero.
        """

        risk = self.risk_distance
        reward = self.reward_distance

        if risk is None or reward is None or risk == 0:
            return None

        return reward / risk
