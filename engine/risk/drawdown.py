"""Drawdown calculations."""

from decimal import Decimal


def drawdown_amount(high_water_mark: Decimal, equity: Decimal) -> Decimal:
    return max(Decimal("0"), high_water_mark - equity)


def drawdown_percent(high_water_mark: Decimal, equity: Decimal) -> Decimal:
    if high_water_mark <= 0:
        raise ValueError("high water mark must be positive")
    return drawdown_amount(high_water_mark, equity) / high_water_mark * Decimal("100")
