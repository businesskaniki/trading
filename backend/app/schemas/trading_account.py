from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.core.constants import AccountStatus, BrokerType


class TradingAccountBase(BaseModel):
    """
    Shared TradingAccount fields.
    """

    broker: BrokerType

    account_number: int

    server: str

    account_name: str

    currency: str = "USD"

    leverage: int = 100

    balance: Decimal = Decimal("0")

    equity: Decimal = Decimal("0")

    margin: Decimal = Decimal("0")

    free_margin: Decimal = Decimal("0")

    margin_level: Decimal = Decimal("0")

    is_demo: bool = True

    status: AccountStatus = AccountStatus.DISCONNECTED

    active: bool = True



class TradingAccountCreate(TradingAccountBase):
    """
    Schema for creating a trading account.
    """

    pass



class TradingAccountUpdate(BaseModel):
    """
    Fields that can change after account creation.
    """

    account_name: str | None = None

    currency: str | None = None

    leverage: int | None = None

    status: AccountStatus | None = None

    active: bool | None = None

    balance: Decimal | None = None

    equity: Decimal | None = None

    margin: Decimal | None = None

    free_margin: Decimal | None = None

    margin_level: Decimal | None = None



class TradingAccountResponse(TradingAccountBase):
    """
    API response schema.
    """

    id: UUID

    created_at: object
    updated_at: object

    model_config = ConfigDict(
        from_attributes=True
    )



class TradingAccountListResponse(BaseModel):
    """
    Paginated response.
    """

    total: int

    items: list[TradingAccountResponse]