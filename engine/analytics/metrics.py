"""Trading performance metrics."""

from decimal import Decimal


def win_rate(results: list[Decimal]) -> Decimal:
    if not results:
        return Decimal("0")
    wins = sum(1 for value in results if value > 0)
    return Decimal(wins) / Decimal(len(results)) * Decimal("100")


def profit_factor(results: list[Decimal]) -> Decimal | None:
    gross_profit = sum((value for value in results if value > 0), Decimal("0"))
    gross_loss = abs(sum((value for value in results if value < 0), Decimal("0")))
    if gross_loss == 0:
        return None
    return gross_profit / gross_loss
