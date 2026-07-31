from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel
from pydantic import ConfigDict
from pydantic import Field

from app.core.constants import AssetClass


# ==========================================================
# Base Schema
# ==========================================================

class SymbolBase(BaseModel):
    """
    Shared Symbol fields.
    """

    name: str = Field(
        ...,
        max_length=30,
        examples=["BTCUSD"],
    )

    description: str | None = Field(
        default=None,
        max_length=255,
    )

    broker_symbol: str = Field(
        ...,
        max_length=30,
        examples=["BTCUSD"],
    )

    asset_class: AssetClass

    digits: int = Field(
        default=5,
        ge=0,
    )

    tick_size: Decimal

    contract_size: Decimal = Decimal("100000")

    min_volume: Decimal = Decimal("0.01")

    max_volume: Decimal = Decimal("100.00")

    volume_step: Decimal = Decimal("0.01")

    active: bool = True


# ==========================================================
# Create Schema
# ==========================================================

class SymbolCreate(SymbolBase):
    """
    Payload used when creating a symbol.
    """

    pass


# ==========================================================
# Update Schema
# ==========================================================

class SymbolUpdate(BaseModel):
    """
    Payload used when updating a symbol.
    """

    name: str | None = Field(
        default=None,
        max_length=30,
    )

    description: str | None = Field(
        default=None,
        max_length=255,
    )

    broker_symbol: str | None = Field(
        default=None,
        max_length=30,
    )

    asset_class: AssetClass | None = None

    digits: int | None = Field(
        default=None,
        ge=0,
    )

    tick_size: Decimal | None = None

    contract_size: Decimal | None = None

    min_volume: Decimal | None = None

    max_volume: Decimal | None = None

    volume_step: Decimal | None = None

    active: bool | None = None


# ==========================================================
# Response Schema
# ==========================================================

class SymbolResponse(SymbolBase):
    """
    Returned to API clients.
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID

    created_at: datetime

    updated_at: datetime