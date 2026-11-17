"""Schemas for non-submitting MT5 margin calculations."""

from __future__ import annotations

from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class MarginCalculationRequest(BaseModel):
    """Describe a proposed BUY/SELL without submitting a trade request."""

    model_config = ConfigDict(extra="forbid")

    symbol: str = Field(min_length=1)
    side: Literal["BUY", "SELL"]
    volume: Decimal = Field(gt=Decimal("0"))
    price: Decimal = Field(gt=Decimal("0"))

    @field_validator("symbol")
    @classmethod
    def validate_symbol(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("symbol cannot be empty")
        return value

    @field_validator("volume", "price")
    @classmethod
    def validate_finite_values(cls, value: Decimal) -> Decimal:
        if not value.is_finite():
            raise ValueError("volume and price must be finite")
        return value


class MarginCalculationResponse(BaseModel):
    """Broker margin result and the exact request values used to obtain it.

    ``required_margin`` is denominated in the MT5 account's deposit currency
    when MT5 returns a valid result. ``currency`` therefore describes the
    account currency, not necessarily the instrument's margin currency.
    """

    model_config = ConfigDict(extra="forbid")

    symbol: str
    side: Literal["BUY", "SELL"]
    volume: Decimal = Field(gt=Decimal("0"))
    price: Decimal = Field(gt=Decimal("0"))
    required_margin: Decimal = Field(ge=Decimal("0"))
    currency: str | None = None
    provider: str = "MT5.order_calc_margin"

    @field_validator("volume", "price", "required_margin")
    @classmethod
    def validate_finite_values(cls, value: Decimal) -> Decimal:
        if not value.is_finite():
            raise ValueError("margin response values must be finite")
        return value

    @field_validator("symbol")
    @classmethod
    def validate_symbol(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("symbol cannot be empty")
        return value

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip().upper()
        return value or None
