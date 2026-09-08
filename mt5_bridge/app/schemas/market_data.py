from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict, Field


class MarketTick(BaseModel):
    """
    Normalized live market tick.

    This is the data contract between the MT5 Bridge and AQE.
    It deliberately contains no MT5-specific types.
    """

    model_config = ConfigDict(
        extra="ignore",
    )

    symbol: str = Field(
        ...,
        min_length=1,
        description="Trading symbol, e.g. EURUSD",
    )

    timestamp: int = Field(
        ...,
        description="Unix timestamp in seconds",
    )

    bid: float = Field(
        ...,
        ge=0,
        description="Current bid price",
    )

    ask: float = Field(
        ...,
        ge=0,
        description="Current ask price",
    )

    last: float = Field(
        default=0.0,
        ge=0,
        description="Last traded price",
    )

    volume: int = Field(
        default=0,
        ge=0,
        description="Tick volume",
    )

    volume_real: float = Field(
        default=0.0,
        ge=0,
        description="Real volume when provided by the broker",
    )

    @property
    def datetime(self) -> datetime:
        """
        Return the tick timestamp as a UTC datetime.
        """

        return datetime.fromtimestamp(
            self.timestamp,
            tz=timezone.utc,
        )

    @property
    def spread(self) -> float:
        """
        Return the current bid/ask spread.
        """

        return self.ask - self.bid
