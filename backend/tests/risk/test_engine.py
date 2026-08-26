```python
from decimal import Decimal

import pytest

from app.risk.calculator import RiskCalculator
from app.risk.engine import RiskEngine


def test_effective_risk_is_calculated_from_profile():
    result = RiskCalculator.effective_risk_percent(
        base_risk_percent=Decimal("1.0000"),
        risk_multiplier=Decimal("0.5000"),
        min_risk_percent=Decimal("0.2500"),
        max_risk_percent=Decimal("2.0000"),
    )

    assert result == Decimal("0.5000")


def test_risk_multiplier_cannot_exceed_maximum():
    result = RiskCalculator.effective_risk_percent(
        base_risk_percent=Decimal("1.0000"),
        risk_multiplier=Decimal("5.0000"),
        min_risk_percent=Decimal("0.2500"),
        max_risk_percent=Decimal("2.0000"),
    )

    assert result == Decimal("2.0000")


def test_risk_multiplier_cannot_go_below_minimum():
    result = RiskCalculator.effective_risk_percent(
        base_risk_percent=Decimal("1.0000"),
        risk_multiplier=Decimal("0.1000"),
        min_risk_percent=Decimal("0.2500"),
        max_risk_percent=Decimal("2.0000"),
    )

    assert result == Decimal("0.2500")


def test_risk_amount_is_calculated_from_equity():
    result = RiskCalculator.risk_amount(
        equity=Decimal("100000.00"),
        risk_percent=Decimal("1.0000"),
    )

    assert result == Decimal("1000.00")


def test_position_size_is_calculated_correctly():
    result = RiskCalculator.position_size(
        risk_amount=Decimal("1000.00"),
        risk_per_unit=Decimal("100.00"),
        volume_step=Decimal("0.01"),
    )

    assert result == Decimal("10.00")


def test_engine_exists():
    assert RiskEngine is not None
```
