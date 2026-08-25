from decimal import Decimal, ROUND_DOWN

from app.risk.exceptions import RiskCalculationError


class RiskCalculator:
    """
    Pure mathematical risk calculations.

    This class does not access the database, broker, orders,
    positions, or HTTP.
    """

    VOLUME_STEP = Decimal("0.01")

    @staticmethod
    def effective_risk_percent(
        base_risk_percent: Decimal,
        risk_multiplier: Decimal,
        min_risk_percent: Decimal,
        max_risk_percent: Decimal,
    ) -> Decimal:

        requested = (
            base_risk_percent
            * risk_multiplier
        )

        if requested < min_risk_percent:
            requested = min_risk_percent

        if requested > max_risk_percent:
            requested = max_risk_percent

        return requested.quantize(
            Decimal("0.0001")
        )

    @staticmethod
    def risk_amount(
        equity: Decimal,
        risk_percent: Decimal,
    ) -> Decimal:

        if equity <= 0:
            raise RiskCalculationError(
                "Account equity must be greater than zero"
            )

        if risk_percent <= 0:
            raise RiskCalculationError(
                "Risk percent must be greater than zero"
            )

        return (
            equity
            * risk_percent
            / Decimal("100")
        ).quantize(
            Decimal("0.01")
        )

    @staticmethod
    def stop_distance(
        entry_price: Decimal,
        stop_loss_price: Decimal,
    ) -> Decimal:

        if entry_price <= 0:
            raise RiskCalculationError(
                "Entry price must be greater than zero"
            )

        if stop_loss_price <= 0:
            raise RiskCalculationError(
                "Stop-loss price must be greater than zero"
            )

        distance = abs(
            entry_price
            - stop_loss_price
        )

        if distance <= 0:
            raise RiskCalculationError(
                "Entry and stop-loss prices cannot be equal"
            )

        return distance

    @staticmethod
    def risk_per_unit(
        stop_distance: Decimal,
        tick_size: Decimal,
        tick_value: Decimal,
    ) -> Decimal:

        if stop_distance <= 0:
            raise RiskCalculationError(
                "Stop distance must be greater than zero"
            )

        if tick_size <= 0:
            raise RiskCalculationError(
                "Tick size must be greater than zero"
            )

        if tick_value <= 0:
            raise RiskCalculationError(
                "Tick value must be greater than zero"
            )

        return (
            stop_distance
            / tick_size
            * tick_value
        ).quantize(
            Decimal("0.00000001")
        )

    @staticmethod
    def position_size(
        risk_amount: Decimal,
        risk_per_unit: Decimal,
        volume_step: Decimal = VOLUME_STEP,
    ) -> Decimal:

        if risk_amount <= 0:
            raise RiskCalculationError(
                "Risk amount must be greater than zero"
            )

        if risk_per_unit <= 0:
            raise RiskCalculationError(
                "Risk per unit must be greater than zero"
            )

        if volume_step <= 0:
            raise RiskCalculationError(
                "Volume step must be greater than zero"
            )

        raw_volume = (
            risk_amount
            / risk_per_unit
        )

        recommended_volume = (
            raw_volume
            / volume_step
        ).to_integral_value(
            rounding=ROUND_DOWN
        ) * volume_step

        if recommended_volume <= 0:
            raise RiskCalculationError(
                "Calculated position size is below the "
                "minimum usable volume step"
            )

        return recommended_volume