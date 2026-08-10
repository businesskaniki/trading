from pydantic import BaseModel


class AccountResponse(BaseModel):

    login: int

    name: str

    server: str

    company: str

    currency: str

    leverage: int

    balance: float

    equity: float

    margin: float

    margin_free: float

    margin_level: float

    profit: float