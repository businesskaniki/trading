from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class BrokerType(str, Enum):
    MT5 = "mt5"


class BrokerConnectionStatus(str, Enum):
    CONNECTED = "connected"
    DISCONNECTED = "disconnected"
    ERROR = "error"


class BrokerConnection(BaseModel):
    """
    Normalized broker connection information.
    """

    model_config = ConfigDict(extra="ignore")

    broker: BrokerType
    status: BrokerConnectionStatus
    message: str | None = None


class BrokerAccount(BaseModel):
    """
    Normalized account information returned by a broker.
    """

    model_config = ConfigDict(extra="ignore")

    login: int | str
    name: str | None = None
    server: str | None = None
    currency: str | None = None

    balance: Decimal = Decimal("0")
    equity: Decimal = Decimal("0")
    margin: Decimal = Decimal("0")
    free_margin: Decimal = Decimal("0")
    margin_level: Decimal | None = None

    leverage: int | None = None

    is_demo: bool | None = None
    is_trade_allowed: bool | None = None


class BrokerSymbol(BaseModel):
    """
    Normalized market symbol information.
    """

    model_config = ConfigDict(extra="ignore")

    name: str
    description: str | None = None

    digits: int | None = None

    point: Decimal | None = None
    tick_size: Decimal | None = None
    tick_value: Decimal | None = None

    contract_size: Decimal | None = None

    volume_min: Decimal | None = None
    volume_max: Decimal | None = None
    volume_step: Decimal | None = None

    bid: Decimal | None = None
    ask: Decimal | None = None

    spread: Decimal | None = None

    trade_allowed: bool | None = None


class BrokerTick(BaseModel):
    """
    Normalized market tick.
    """

    model_config = ConfigDict(extra="ignore")

    symbol: str

    bid: Decimal
    ask: Decimal

    time: datetime | None = None

    last: Decimal | None = None
    volume: Decimal | None = None


class BrokerOrder(BaseModel):
    """
    Normalized pending/order information.
    """

    model_config = ConfigDict(extra="ignore")

    ticket: int | str
    symbol: str

    order_type: str | None = None
    state: str | None = None

    volume: Decimal = Decimal("0")
    price_open: Decimal | None = None
    price_current: Decimal | None = None

    stop_loss: Decimal | None = None
    take_profit: Decimal | None = None

    magic: int | None = None

    comment: str | None = None

    time_setup: datetime | None = None
    time_done: datetime | None = None


class BrokerPosition(BaseModel):
    """
    Normalized open-position information.
    """

    model_config = ConfigDict(extra="ignore")

    ticket: int | str
    symbol: str

    position_type: str | None = None

    volume: Decimal = Decimal("0")

    price_open: Decimal | None = None
    price_current: Decimal | None = None

    stop_loss: Decimal | None = None
    take_profit: Decimal | None = None

    profit: Decimal = Decimal("0")
    swap: Decimal = Decimal("0")

    magic: int | None = None
    comment: str | None = None

    time_open: datetime | None = None


class BrokerDeal(BaseModel):
    """
    Normalized executed deal/trade information.
    """

    model_config = ConfigDict(extra="ignore")

    ticket: int | str
    order_ticket: int | str | None = None
    position_ticket: int | str | None = None

    symbol: str

    deal_type: str | None = None
    entry: str | None = None

    volume: Decimal = Decimal("0")
    price: Decimal = Decimal("0")

    profit: Decimal = Decimal("0")
    commission: Decimal = Decimal("0")
    swap: Decimal = Decimal("0")

    magic: int | None = None
    comment: str | None = None

    time: datetime | None = None


class BrokerOrderRequest(BaseModel):
    """
    Engine-level request for submitting an order.

    This is deliberately broker-neutral. MT5-specific request
    structures should be created by the MT5 adapter.
    """

    symbol: str
    side: str

    volume: Decimal = Field(gt=0)

    order_type: str | None = None

    price: Decimal | None = None
    stop_loss: Decimal | None = None
    take_profit: Decimal | None = None

    deviation: int | None = None
    magic: int | None = None
    comment: str | None = None

    model_config = ConfigDict(extra="ignore")


class BrokerOrderResult(BaseModel):
    """
    Normalized result returned after an order submission.
    """

    success: bool

    order_ticket: int | str | None = None
    deal_ticket: int | str | None = None

    symbol: str | None = None
    volume: Decimal | None = None
    price: Decimal | None = None

    retcode: int | None = None
    message: str | None = None

    raw: dict[str, Any] | None = None
