import pytest
from pydantic import ValidationError


def test_order_request_rejects_invalid_values():
    from app.schemas.order import OrderRequest

    with pytest.raises(ValidationError):
        OrderRequest(symbol=" ", volume=1, order_type=0, price=1)

    with pytest.raises(ValidationError):
        OrderRequest(symbol="EURUSD", volume=0, order_type=0, price=1)

    with pytest.raises(ValidationError):
        OrderRequest(symbol="EURUSD", volume=1, order_type=0, price=1, sl=0)


def test_order_request_normalizes_symbol_and_comment():
    from app.schemas.order import OrderRequest

    request = OrderRequest(
        symbol=" EURUSD.s ",
        volume=1,
        order_type=0,
        price=1,
        comment="  bridge   order  ",
    )

    assert request.symbol == "EURUSD.s"
    assert request.comment == "bridge order"


def test_bridge_settings_require_token(monkeypatch):
    monkeypatch.setenv("MT5_BRIDGE_TOKEN", "bridge-secret")

    from app.core.config import Settings

    assert Settings(MT5_BRIDGE_TOKEN="bridge-secret").MT5_BRIDGE_TOKEN == "bridge-secret"

    with pytest.raises(ValidationError):
        Settings(MT5_BRIDGE_TOKEN="")
