from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel
from pydantic import ConfigDict
from pydantic import Field

from app.core.constants import AccountStatus
from app.core.constants import BrokerType

# ============================================================
# Base
# ============================================================


class TradingAccountBase(BaseModel):
    """
    Common fields shared by trading account schemas.
    """

    broker: BrokerType

    login: int = Field(
        ...,
        gt=0,
        description="Broker trading account login.",
    )

    server: str = Field(
        ...,
        min_length=1,
        max_length=100,
    )

    account_name: str = Field(
        ...,
        min_length=1,
        max_length=100,
    )

    is_demo: bool = True


# ============================================================
# Create
# ============================================================


class TradingAccountCreate(TradingAccountBase):
    """
    Data required to create a trading account.

    Credentials are accepted here so the backend can encrypt
    them before storing them.
    """

    password: str | None = Field(
        default=None,
        min_length=1,
        description="Trading account password. Never returned by the API.",
    )

    bridge_url: str | None = Field(
        default=None,
        max_length=255,
        description="MT5 bridge URL used by this account.",
    )


# ============================================================
# Update
# ============================================================


class TradingAccountUpdate(BaseModel):
    """
    Fields that may be modified after account creation.
    """

    account_name: str | None = Field(
        default=None,
        min_length=1,
        max_length=100,
    )

    password: str | None = Field(
        default=None,
        min_length=1,
        description="New trading account password. Never returned by the API.",
    )

    is_demo: bool | None = None

    bridge_url: str | None = Field(
        default=None,
        max_length=255,
    )

    active: bool | None = None


# ============================================================
# Broker State
# ============================================================


class TradingAccountStateUpdate(BaseModel):
    """
    Broker/MT5 synchronized account state.

    These values are produced by the bridge and should not be
    accepted from normal frontend account-edit requests.
    """

    currency: str | None = Field(
        default=None,
        max_length=10,
    )

    leverage: int | None = Field(
        default=None,
        gt=0,
    )

    balance: Decimal | None = None

    equity: Decimal | None = None

    margin: Decimal | None = None

    free_margin: Decimal | None = None

    margin_level: Decimal | None = None

    status: AccountStatus | None = None


# ============================================================
# Response
# ============================================================


class TradingAccountResponse(TradingAccountBase):
    """
    Safe representation of a trading account returned to the
    frontend.

    Credentials are deliberately excluded.
    """

    model_config = ConfigDict(
        from_attributes=True,
    )

    id: UUID

    user_id: UUID

    currency: str

    leverage: int

    status: AccountStatus

    active: bool

    balance: Decimal

    equity: Decimal

    margin: Decimal

    free_margin: Decimal

    margin_level: Decimal

    bridge_url: str | None

    created_at: datetime

    updated_at: datetime


# ============================================================
# List Response
# ============================================================


class TradingAccountListResponse(BaseModel):
    """
    Paginated/list representation of trading accounts.
    """

    items: list[TradingAccountResponse]

    total: int
