from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel
from pydantic import ConfigDict
from pydantic import Field
from pydantic import model_validator

from app.core.constants import AssetClass

# ============================================================
# Base
# ============================================================


class AccountSymbolBase(BaseModel):
    """
    Broker/account-specific symbol metadata.

    These values originate from the MT5 bridge.
    """

    broker_symbol: str = Field(
        ...,
        min_length=1,
        max_length=50,
    )

    path: str | None = Field(
        default=None,
        max_length=255,
    )

    currency_base: str | None = Field(
        default=None,
        max_length=10,
    )

    currency_profit: str | None = Field(
        default=None,
        max_length=10,
    )

    currency_margin: str | None = Field(
        default=None,
        max_length=10,
    )

    digits: int = Field(
        ...,
        ge=0,
    )

    point: Decimal = Field(
        ...,
        gt=0,
    )

    tick_size: Decimal = Field(
        ...,
        gt=0,
    )

    contract_size: Decimal | None = Field(
        default=None,
        gt=0,
    )

    min_volume: Decimal | None = Field(
        default=None,
        gt=0,
    )

    max_volume: Decimal | None = Field(
        default=None,
        gt=0,
    )

    volume_step: Decimal | None = Field(
        default=None,
        gt=0,
    )


# ============================================================
# Create
# ============================================================


class AccountSymbolCreate(AccountSymbolBase):
    """
    Internal creation schema.

    AccountSymbols are normally created by MT5 synchronization,
    not manually by the frontend.
    """

    account_id: UUID
    symbol_id: UUID
    enabled: bool = False


# ============================================================
# Update
# ============================================================


class AccountSymbolUpdate(BaseModel):
    """
    User-editable account-symbol settings.

    Only `enabled` is intentionally exposed.
    """

    enabled: bool | None = None


# ============================================================
# Trading Selection
# ============================================================


class AccountSymbolSelection(BaseModel):
    """
    Enable or disable an account symbol for trading.
    """

    enabled: bool


# ============================================================
# Broker Synchronization
# ============================================================


class AccountSymbolSync(BaseModel):
    """
    Symbol metadata received from the MT5 bridge.
    """

    broker_symbol: str = Field(
        ...,
        min_length=1,
        max_length=50,
    )

    path: str | None = Field(
        default=None,
        max_length=255,
    )

    currency_base: str | None = Field(
        default=None,
        max_length=10,
    )

    currency_profit: str | None = Field(
        default=None,
        max_length=10,
    )

    currency_margin: str | None = Field(
        default=None,
        max_length=10,
    )

    digits: int = Field(
        ...,
        ge=0,
    )

    point: Decimal = Field(
        ...,
        gt=0,
    )

    tick_size: Decimal | None = Field(
        default=None,
        gt=0,
    )

    contract_size: Decimal | None = Field(
        default=None,
        gt=0,
    )

    min_volume: Decimal | None = Field(
        default=None,
        gt=0,
    )

    max_volume: Decimal | None = Field(
        default=None,
        gt=0,
    )

    volume_step: Decimal | None = Field(
        default=None,
        gt=0,
    )

    visible: bool = False


# ============================================================
# Response
# ============================================================


class AccountSymbolResponse(AccountSymbolBase):
    """
    Complete account-specific symbol returned to the frontend.

    `name` and `asset_class` belong to the canonical Symbol
    record and are resolved from the AccountSymbol.symbol
    relationship during serialization.
    """

    model_config = ConfigDict(
        from_attributes=True,
    )

    id: UUID

    account_id: UUID

    symbol_id: UUID

    # --------------------------------------------------------
    # Canonical symbol information
    # --------------------------------------------------------

    name: str

    asset_class: AssetClass

    # --------------------------------------------------------
    # Account selection
    # --------------------------------------------------------

    visible: bool

    enabled: bool

    # --------------------------------------------------------
    # Timestamps
    # --------------------------------------------------------

    created_at: datetime

    updated_at: datetime

    # --------------------------------------------------------
    # ORM -> API transformation
    # --------------------------------------------------------

    @model_validator(mode="before")
    @classmethod
    def resolve_canonical_symbol_fields(cls, value):
        """
        Resolve canonical symbol fields from the related
        Symbol ORM object.

        AccountSymbol stores `symbol_id`, while the canonical
        name and asset class live on `Symbol`.
        """

        if isinstance(value, dict):
            return value

        symbol = getattr(value, "symbol", None)

        if symbol is None:
            return value

        return {
            "id": value.id,
            "account_id": value.account_id,
            "symbol_id": value.symbol_id,
            "broker_symbol": value.broker_symbol,
            "path": value.path,
            "currency_base": value.currency_base,
            "currency_profit": value.currency_profit,
            "currency_margin": value.currency_margin,
            "digits": value.digits,
            "point": value.point,
            "tick_size": value.tick_size,
            "contract_size": value.contract_size,
            "min_volume": value.min_volume,
            "max_volume": value.max_volume,
            "volume_step": value.volume_step,
            "name": symbol.name,
            "asset_class": symbol.asset_class,
            "visible": value.visible,
            "enabled": value.enabled,
            "created_at": value.created_at,
            "updated_at": value.updated_at,
        }


# ============================================================
# List Response
# ============================================================


class AccountSymbolListResponse(BaseModel):
    """
    Account symbols returned to the frontend.
    """

    items: list[AccountSymbolResponse]

    total: int
