from decimal import Decimal, ROUND_DOWN

from app.risk.exceptions import RiskCalculationError


class RiskCalculator:
    """
    Pure mathematical risk calculations.

    This class does not access:
        - database
        - broker
        - orders
        - positions
        - HTTP

    Symbol-specific trading constraints such as:
        - min_volume
        - max_volume
        - volume_step

    are supplied by the caller.
    """

    # ==========================================================
    # EFFECTIVE RISK
    # ==========================================================

    @staticmethod
    def effective_risk_percent(
        base_risk_percent: Decimal,
        risk_multiplier: Decimal,
        min_risk_percent: Decimal,
        max_risk_percent: Decimal,
    ) -> Decimal:
        """
        Calculate the effective risk percentage.

        effective risk =
            base risk × multiplier

        The result is clamped between:
            min_risk_percent
            max_risk_percent
        """

        if base_risk_percent <= 0:
            raise RiskCalculationError("Base risk percent must be greater than zero")

        if risk_multiplier <= 0:
            raise RiskCalculationError("Risk multiplier must be greater than zero")

        if min_risk_percent <= 0:
            raise RiskCalculationError("Minimum risk percent must be greater than zero")

        if max_risk_percent <= 0:
            raise RiskCalculationError("Maximum risk percent must be greater than zero")

        if min_risk_percent > max_risk_percent:
            raise RiskCalculationError(
                "Minimum risk cannot be greater than maximum risk"
            )

        requested = base_risk_percent * risk_multiplier

        requested = max(
            requested,
            min_risk_percent,
        )

        requested = min(
            requested,
            max_risk_percent,
        )

        return requested.quantize(Decimal("0.0001"))

    # ==========================================================
    # RISK AMOUNT
    # ==========================================================

    @staticmethod
    def risk_amount(
        equity: Decimal,
        risk_percent: Decimal,
    ) -> Decimal:
        """
        Convert account equity and risk percentage
        into a monetary risk amount.
        """

        if equity <= 0:
            raise RiskCalculationError("Account equity must be greater than zero")

        if risk_percent <= 0:
            raise RiskCalculationError("Risk percent must be greater than zero")

        return (equity * risk_percent / Decimal("100")).quantize(Decimal("0.01"))

    # ==========================================================
    # STOP DISTANCE
    # ==========================================================

    @staticmethod
    def stop_distance(
        entry_price: Decimal,
        stop_loss_price: Decimal,
    ) -> Decimal:
        """
        Calculate absolute distance between entry
        and stop-loss.
        """

        if entry_price <= 0:
            raise RiskCalculationError("Entry price must be greater than zero")

        if stop_loss_price <= 0:
            raise RiskCalculationError("Stop-loss price must be greater than zero")

        distance = abs(entry_price - stop_loss_price)

        if distance <= 0:
            raise RiskCalculationError("Entry and stop-loss prices cannot be equal")

        return distance

    # ==========================================================
    # RISK PER UNIT
    # ==========================================================

    @staticmethod
    def risk_per_unit(
        stop_distance: Decimal,
        tick_size: Decimal,
        tick_value: Decimal,
    ) -> Decimal:
        """
        Calculate monetary risk for one unit of volume.

        Formula:

            stop_distance / tick_size × tick_value
        """

        if stop_distance <= 0:
            raise RiskCalculationError("Stop distance must be greater than zero")

        if tick_size <= 0:
            raise RiskCalculationError("Tick size must be greater than zero")

        if tick_value <= 0:
            raise RiskCalculationError("Tick value must be greater than zero")

        result = stop_distance / tick_size * tick_value

        if result <= 0:
            raise RiskCalculationError("Risk per unit must be greater than zero")

        return result.quantize(Decimal("0.00000001"))

    # ==========================================================
    # RAW POSITION SIZE
    # ==========================================================

    @staticmethod
    def raw_position_size(
        risk_amount: Decimal,
        risk_per_unit: Decimal,
    ) -> Decimal:
        """
        Calculate the unrounded position size.
        """

        if risk_amount <= 0:
            raise RiskCalculationError("Risk amount must be greater than zero")

        if risk_per_unit <= 0:
            raise RiskCalculationError("Risk per unit must be greater than zero")

        raw_volume = risk_amount / risk_per_unit

        if raw_volume <= 0:
            raise RiskCalculationError(
                "Calculated raw position size must be " "greater than zero"
            )

        return raw_volume.quantize(Decimal("0.00000001"))

    # ==========================================================
    # POSITION SIZE
    # ==========================================================

    @staticmethod
    def position_size(
        risk_amount: Decimal,
        risk_per_unit: Decimal,
        volume_step: Decimal,
        min_volume: Decimal | None = None,
        max_volume: Decimal | None = None,
    ) -> Decimal:
        """
        Calculate broker-compatible position size.

        The volume is rounded DOWN to the broker's
        volume step.

        Optional:
            min_volume
            max_volume
        """

        if risk_amount <= 0:
            raise RiskCalculationError("Risk amount must be greater than zero")

        if risk_per_unit <= 0:
            raise RiskCalculationError("Risk per unit must be greater than zero")

        if volume_step <= 0:
            raise RiskCalculationError("Volume step must be greater than zero")

        if min_volume is not None and min_volume <= 0:
            raise RiskCalculationError("Minimum volume must be greater than zero")

        if max_volume is not None and max_volume <= 0:
            raise RiskCalculationError("Maximum volume must be greater than zero")

        if (
            min_volume is not None
            and max_volume is not None
            and min_volume > max_volume
        ):
            raise RiskCalculationError(
                "Minimum volume cannot be greater than maximum volume"
            )

        raw_volume = risk_amount / risk_per_unit

        # ------------------------------------------------------
        # Round DOWN to broker volume step
        # ------------------------------------------------------

        recommended_volume = (raw_volume / volume_step).to_integral_value(
            rounding=ROUND_DOWN
        ) * volume_step

        # ------------------------------------------------------
        # Check minimum volume
        # ------------------------------------------------------

        if recommended_volume <= 0:
            raise RiskCalculationError(
                "Calculated position size is below the " "minimum usable volume step"
            )

        if min_volume is not None and recommended_volume < min_volume:
            raise RiskCalculationError(
                "Calculated position size is below the " "symbol minimum volume"
            )

        # ------------------------------------------------------
        # Check maximum volume
        # ------------------------------------------------------

        if max_volume is not None and recommended_volume > max_volume:
            recommended_volume = max_volume

            # Make sure max volume itself respects
            # the broker's volume step.
            recommended_volume = (recommended_volume / volume_step).to_integral_value(
                rounding=ROUND_DOWN
            ) * volume_step

        if recommended_volume <= 0:
            raise RiskCalculationError(
                "Maximum volume is incompatible with " "the symbol volume step"
            )

        return recommended_volume.quantize(volume_step)
