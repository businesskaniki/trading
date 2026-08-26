from decimal import Decimal, ROUND_DOWN

from app.risk.exceptions import RiskCalculationError


class RiskCalculator:
    """
    Pure mathematical risk calculations.

    This class has no knowledge of:
    - databases
    - repositories
    - trading accounts
    - symbols
    - positions
    - orders
    - brokers
    - FastAPI

    All inputs and outputs use Decimal for financial precision.
    """

    DEFAULT_VOLUME_STEP = Decimal("0.01")

    RISK_PERCENT_QUANTIZE = Decimal("0.0001")
    MONEY_QUANTIZE = Decimal("0.01")
    PRICE_QUANTIZE = Decimal("0.00000001")
    VOLUME_QUANTIZE = Decimal("0.00000001")

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

        Formula:

            effective risk =
                base risk × risk multiplier

        The result is then constrained between the configured
        minimum and maximum risk percentages.
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
                "Minimum risk percent cannot be greater " "than maximum risk percent"
            )

        requested_risk = base_risk_percent * risk_multiplier

        effective_risk = max(
            min_risk_percent,
            min(
                requested_risk,
                max_risk_percent,
            ),
        )

        return effective_risk.quantize(RiskCalculator.RISK_PERCENT_QUANTIZE)

    # ==========================================================
    # RISK AMOUNT
    # ==========================================================

    @staticmethod
    def risk_amount(
        equity: Decimal,
        risk_percent: Decimal,
    ) -> Decimal:
        """
        Calculate the monetary amount that may be risked.

        Formula:

            risk amount =
                equity × risk percent / 100
        """

        if equity <= 0:
            raise RiskCalculationError("Account equity must be greater than zero")

        if risk_percent <= 0:
            raise RiskCalculationError("Risk percent must be greater than zero")

        amount = equity * risk_percent / Decimal("100")

        return amount.quantize(RiskCalculator.MONEY_QUANTIZE)

    # ==========================================================
    # STOP DISTANCE
    # ==========================================================

    @staticmethod
    def stop_distance(
        entry_price: Decimal,
        stop_loss_price: Decimal,
    ) -> Decimal:
        """
        Calculate absolute price distance between entry and stop.

        Direction is intentionally irrelevant here.

        BUY:
            stop < entry

        SELL:
            stop > entry

        Both produce the same positive distance.
        """

        if entry_price <= 0:
            raise RiskCalculationError("Entry price must be greater than zero")

        if stop_loss_price <= 0:
            raise RiskCalculationError("Stop-loss price must be greater than zero")

        distance = abs(entry_price - stop_loss_price)

        if distance <= 0:
            raise RiskCalculationError("Entry and stop-loss prices cannot be equal")

        return distance.quantize(RiskCalculator.PRICE_QUANTIZE)

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

            number of ticks =
                stop distance / tick size

            risk per unit =
                number of ticks × tick value

        This assumes tick_value represents the monetary value
        of one tick for one unit of trading volume.
        """

        if stop_distance <= 0:
            raise RiskCalculationError("Stop distance must be greater than zero")

        if tick_size <= 0:
            raise RiskCalculationError("Tick size must be greater than zero")

        if tick_value <= 0:
            raise RiskCalculationError("Tick value must be greater than zero")

        number_of_ticks = stop_distance / tick_size

        risk = number_of_ticks * tick_value

        if risk <= 0:
            raise RiskCalculationError(
                "Calculated risk per unit must be greater than zero"
            )

        return risk.quantize(RiskCalculator.PRICE_QUANTIZE)

    # ==========================================================
    # POSITION SIZE
    # ==========================================================

    @staticmethod
    def position_size(
        risk_amount: Decimal,
        risk_per_unit: Decimal,
        volume_step: Decimal = DEFAULT_VOLUME_STEP,
        min_volume: Decimal | None = None,
        max_volume: Decimal | None = None,
    ) -> Decimal:
        """
        Calculate the position volume that respects the risk amount.

        The raw volume is always rounded DOWN to the nearest valid
        volume step.

        This is intentional.

        Rounding UP could cause the resulting position to exceed
        the requested monetary risk.
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

        stepped_volume = (raw_volume / volume_step).to_integral_value(
            rounding=ROUND_DOWN
        ) * volume_step

        if stepped_volume <= 0:
            raise RiskCalculationError(
                "Calculated position size is below " "the minimum usable volume step"
            )

        # ------------------------------------------------------
        # Broker minimum volume
        # ------------------------------------------------------

        if min_volume is not None and stepped_volume < min_volume:
            raise RiskCalculationError(
                "Calculated position size is below " "the symbol minimum volume"
            )

        # ------------------------------------------------------
        # Broker maximum volume
        # ------------------------------------------------------

        if max_volume is not None and stepped_volume > max_volume:
            stepped_volume = (max_volume / volume_step).to_integral_value(
                rounding=ROUND_DOWN
            ) * volume_step

        if stepped_volume <= 0:
            raise RiskCalculationError("Calculated position size is not usable")

        return stepped_volume.quantize(RiskCalculator.VOLUME_QUANTIZE)
