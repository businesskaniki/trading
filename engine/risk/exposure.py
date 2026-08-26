"""Exposure calculations."""

from decimal import Decimal


def notional(volume: Decimal, price: Decimal, contract_size: Decimal = Decimal("1")) -> Decimal:
    if volume < 0 or price < 0 or contract_size <= 0:
        raise ValueError("invalid exposure inputs")
    return volume * price * contract_size


def exposure_percent(exposure: Decimal, equity: Decimal) -> Decimal:
    if equity <= 0:
        raise ValueError("equity must be positive")
    return exposure / equity * Decimal("100")
