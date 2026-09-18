from typing import Optional

from pydantic import BaseModel, Field, field_validator, model_validator


class OrderRequest(BaseModel):

    symbol: str = Field(..., min_length=1, max_length=32)

    volume: float = Field(..., gt=0)

    order_type: int = Field(..., ge=0)

    price: float = Field(..., gt=0)

    sl: Optional[float] = None

    tp: Optional[float] = None

    deviation: int = Field(20, ge=0, le=10000)

    magic: int = Field(0, ge=0)

    comment: str = ""

    @field_validator("symbol")
    @classmethod
    def normalize_symbol(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("symbol cannot be empty")
        return value

    @field_validator("comment")
    @classmethod
    def normalize_comment(cls, value: str) -> str:
        return " ".join(value.split())[:31]

    @model_validator(mode="after")
    def validate_stops(self):
        if self.sl is not None and self.sl <= 0:
            raise ValueError("sl must be greater than zero")
        if self.tp is not None and self.tp <= 0:
            raise ValueError("tp must be greater than zero")
        return self


class OrderResponse(BaseModel):

    ticket: int

    symbol: str

    volume: float

    price_open: float

    sl: float

    tp: float

    order_type: int

    state: int

    comment: str