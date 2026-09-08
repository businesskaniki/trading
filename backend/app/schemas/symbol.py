
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel
from pydantic import ConfigDict
from pydantic import Field

from app.core.constants import AssetClass


# ============================================================
# Base
# ============================================================


class SymbolBase(BaseModel):
    """
    Common fields for a canonical AQE symbol.
    """

    name: str = Field(
        ...,
        min_length=1,
        max_length=30,
    )

    description: str | None = Field(
        default=None,
        max_length=255,
    )

    asset_class: AssetClass


# ============================================================
# Create
# ============================================================


class SymbolCreate(SymbolBase):
    """
    Creates a canonical AQE symbol.

    Canonical symbols are not tied to a specific broker.
    """

    active: bool = True


# ============================================================
# Update
# ============================================================


class SymbolUpdate(BaseModel):
    """
    Fields that may be modified on a canonical symbol.
    """

    name: str | None = Field(
        default=None,
        min_length=1,
        max_length=30,
    )

    description: str | None = Field(
        default=None,
        max_length=255,
    )

    asset_class: AssetClass | None = None

    active: bool | None = None


# ============================================================
# Response
# ============================================================


class SymbolResponse(SymbolBase):
    """
    Canonical symbol returned by AQE.
    """

    model_config = ConfigDict(
        from_attributes=True,
    )

    id: UUID

    active: bool

    created_at: datetime

    updated_at: datetime


# ============================================================
# List Response
# ============================================================


class SymbolListResponse(BaseModel):
    """
    List of canonical symbols.
    """

    items: list[SymbolResponse]

    total: int

