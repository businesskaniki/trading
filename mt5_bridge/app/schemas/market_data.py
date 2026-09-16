import math

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

    def validation_errors(self) -> list[str]:
        """
        Return domain-level validation errors for live market data.

        Pydantic validates the data type and basic field constraints.
        This method validates whether the tick actually represents
        usable market data.
        """

        errors: list[str] = []

        if not self.symbol.strip():
            errors.append("symbol is empty")

        if self.timestamp <= 0:
            errors.append(f"timestamp must be > 0, got {self.timestamp}")

        if not math.isfinite(self.bid):
            errors.append(f"bid must be finite, got {self.bid}")
        elif self.bid <= 0:
            errors.append(f"bid must be > 0, got {self.bid}")

        if not math.isfinite(self.ask):
            errors.append(f"ask must be finite, got {self.ask}")
        elif self.ask <= 0:
            errors.append(f"ask must be > 0, got {self.ask}")

        if self.bid > 0 and self.ask > 0:
            if self.ask < self.bid:
                errors.append(
                    f"ask must be >= bid, got ask={self.ask}, " f"bid={self.bid}"
                )

        if not math.isfinite(self.last):
            errors.append(f"last must be finite, got {self.last}")

        if not math.isfinite(self.volume_real):
            errors.append(f"volume_real must be finite, got {self.volume_real}")

        if self.volume < 0:
            errors.append(f"volume must be >= 0, got {self.volume}")

        return errors

    def is_valid(self) -> bool:
        """
        Return True only when the tick represents usable
        live market data.
        """

        return not self.validation_errors()
