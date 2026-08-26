from decimal import Decimal

import pytest

from app.risk.calculator import RiskCalculator
from app.risk.exceptions import RiskCalculationError


class TestRiskCalculator:

    def test_effective_risk_percent_default(self):
        result = RiskCalculator.effective_risk_percent(
            base_risk_percent=Decimal("1.0000"),
            risk_multiplier=Decimal("1.0000"),
            min_risk_percent=Decimal("0.2500"),
            max_risk_percent=Decimal("2.0000"),
        )

        assert result == Decimal("1.0000")

    def test_risk_multiplier_increases_risk(self):
        result = RiskCalculator.effective_risk_percent(
            base_risk_percent=Decimal("1.0000"),
            risk_multiplier=Decimal("1.5000"),
            min_risk_percent=Decimal("0.2500"),
            max_risk_percent=Decimal("2.0000"),
        )

        assert result == Decimal("1.5000")

    def test_risk_multiplier_cannot_exceed_maximum(self):
        result = RiskCalculator.effective_risk_percent(
            base_risk_percent=Decimal("1.0000"),
            risk_multiplier=Decimal("5.0000"),
            min_risk_percent=Decimal("0.2500"),
            max_risk_percent=Decimal("2.0000"),
        )

        assert result == Decimal("2.0000")

    def test_risk_multiplier_cannot_go_below_minimum(self):
        result = RiskCalculator.effective_risk_percent(
            base_risk_percent=Decimal("1.0000"),
            risk_multiplier=Decimal("0.1000"),
            min_risk_percent=Decimal("0.2500"),
            max_risk_percent=Decimal("2.0000"),
        )

        assert result == Decimal("0.2500")

    def test_risk_amount(self):
        result = RiskCalculator.risk_amount(
            equity=Decimal("100170.14"),
            risk_percent=Decimal("1.0000"),
        )

        assert result == Decimal("1001.70")

    def test_risk_amount_at_two_percent(self):
        result = RiskCalculator.risk_amount(
            equity=Decimal("100170.14"),
            risk_percent=Decimal("2.0000"),
        )

        assert result == Decimal("2003.40")

    def test_stop_distance(self):
        result = RiskCalculator.stop_distance(
            entry_price=Decimal("110000.00"),
            stop_loss_price=Decimal("109000.00"),
        )

        assert result == Decimal("1000.00")

    def test_stop_distance_works_for_short_trade(self):
        result = RiskCalculator.stop_distance(
            entry_price=Decimal("109000.00"),
            stop_loss_price=Decimal("110000.00"),
        )

        assert result == Decimal("1000.00")

    def test_equal_entry_and_stop_is_rejected(self):
        with pytest.raises(RiskCalculationError):
            RiskCalculator.stop_distance(
                entry_price=Decimal("110000.00"),
                stop_loss_price=Decimal("110000.00"),
            )

    def test_risk_per_unit(self):
        result = RiskCalculator.risk_per_unit(
            stop_distance=Decimal("1000.00"),
            tick_size=Decimal("0.01"),
            tick_value=Decimal("0.01"),
        )

        assert result == Decimal("1000.00000000")

    def test_position_size(self):
        result = RiskCalculator.position_size(
            risk_amount=Decimal("1001.70"),
            risk_per_unit=Decimal("1000.00000000"),
            volume_step=Decimal("0.01"),
        )

        assert result == Decimal("1.00")

    def test_position_size_rounds_down(self):
        result = RiskCalculator.position_size(
            risk_amount=Decimal("1502.55"),
            risk_per_unit=Decimal("1000.00000000"),
            volume_step=Decimal("0.01"),
        )

        assert result == Decimal("1.50")
