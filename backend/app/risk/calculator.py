from decimal import Decimal, ROUND_DOWN

from .exceptions import RiskCalculationError


class RiskCalculator:
    """Compatibility facade for the legacy risk-test API."""

    @staticmethod
    def effective_risk_percent(
        base_risk_percent: Decimal,
        risk_multiplier: Decimal,
        min_risk_percent: Decimal,
        max_risk_percent: Decimal,
    ) -> Decimal:
        value = base_risk_percent * risk_multiplier
        return max(min_risk_percent, min(max_risk_percent, value))

    @staticmethod
    def risk_amount(equity: Decimal, risk_percent: Decimal) -> Decimal:
        if equity <= 0 or risk_percent <= 0:
            raise RiskCalculationError("Equity and risk percent must be positive")
        return (equity * risk_percent / Decimal("100")).quantize(
            Decimal("0.01"), rounding=ROUND_DOWN
        )

    @staticmethod
    def position_size(
        risk_amount: Decimal,
        risk_per_unit: Decimal,
        volume_step: Decimal,
    ) -> Decimal:
        if risk_per_unit <= 0 or volume_step <= 0:
            raise RiskCalculationError("Risk per unit and volume step must be positive")
        raw = risk_amount / risk_per_unit
        if raw < volume_step:
            raise RiskCalculationError("Calculated position size is below the volume step")
        return (raw // volume_step * volume_step).quantize(volume_step)

    @staticmethod
    def stop_distance(entry_price: Decimal, stop_loss_price: Decimal) -> Decimal:
        if entry_price <= 0 or stop_loss_price <= 0:
            raise RiskCalculationError("Prices must be positive")
        distance = abs(entry_price - stop_loss_price)
        if distance <= 0:
            raise RiskCalculationError("Stop-loss must differ from entry price")
        return distance

    @staticmethod
    def risk_per_unit(
        stop_distance: Decimal,
        tick_size: Decimal,
        tick_value: Decimal,
    ) -> Decimal:
        if stop_distance <= 0 or tick_size <= 0 or tick_value <= 0:
            raise RiskCalculationError("Risk inputs must be positive")
        return stop_distance / tick_size * tick_value