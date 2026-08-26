from decimal import Decimal

import pytest

from app.risk.exceptions import RiskCalculationError
from app.risk.calculator import RiskCalculator


def test_zero_equity_is_rejected():
    with pytest.raises(RiskCalculationError):
        RiskCalculator.risk_amount(
            equity=Decimal("0"),
            risk_percent=Decimal("1.0000"),
        )


def test_negative_equity_is_rejected():
    with pytest.raises(RiskCalculationError):
        RiskCalculator.risk_amount(
            equity=Decimal("-1000"),
            risk_percent=Decimal("1.0000"),
        )


def test_zero_risk_percent_is_rejected():
    with pytest.raises(RiskCalculationError):
        RiskCalculator.risk_amount(
            equity=Decimal("100000"),
            risk_percent=Decimal("0"),
        )


def test_invalid_stop_loss_is_rejected():
    with pytest.raises(RiskCalculationError):
        RiskCalculator.stop_distance(
            entry_price=Decimal("100"),
            stop_loss_price=Decimal("100"),
        )


def test_negative_entry_price_is_rejected():
    with pytest.raises(RiskCalculationError):
        RiskCalculator.stop_distance(
            entry_price=Decimal("-100"),
            stop_loss_price=Decimal("90"),
        )


def test_invalid_tick_size_is_rejected():
    with pytest.raises(RiskCalculationError):
        RiskCalculator.risk_per_unit(
            stop_distance=Decimal("10"),
            tick_size=Decimal("0"),
            tick_value=Decimal("1"),
        )


def test_invalid_tick_value_is_rejected():
    with pytest.raises(RiskCalculationError):
        RiskCalculator.risk_per_unit(
            stop_distance=Decimal("10"),
            tick_size=Decimal("1"),
            tick_value=Decimal("0"),
        )


def test_position_size_below_volume_step_is_rejected():
    with pytest.raises(RiskCalculationError):
        RiskCalculator.position_size(
            risk_amount=Decimal("1"),
            risk_per_unit=Decimal("1000"),
            volume_step=Decimal("0.01"),
        )
