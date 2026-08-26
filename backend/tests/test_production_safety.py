import os

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

os.environ.setdefault("SECRET_KEY", "test-secret")
os.environ.setdefault("POSTGRES_HOST", "localhost")
os.environ.setdefault("POSTGRES_DB", "test")
os.environ.setdefault("POSTGRES_USER", "test")
os.environ.setdefault("POSTGRES_PASSWORD", "test")
os.environ.setdefault("REDIS_HOST", "localhost")
os.environ.setdefault("SMTP_HOST", "localhost")
os.environ.setdefault("SMTP_USERNAME", "test")
os.environ.setdefault("SMTP_PASSWORD", "test")
os.environ.setdefault("SMTP_FROM_EMAIL", "test@example.com")

from app.broker.factory import get_broker_adapter
from app.broker.paper.adapter import PaperBroker
from app.core.config import Settings
from app.main import app


def test_production_rejects_implicit_paper_broker():
    with pytest.raises(ValidationError):
        Settings(APP_ENV="production", BROKER="paper")


def test_production_requires_debug_to_be_disabled():
    with pytest.raises(ValidationError):
        Settings(APP_ENV="production", BROKER="mt5", DEBUG=True)


def test_factory_selects_paper_broker():
    assert isinstance(get_broker_adapter("paper"), PaperBroker)


def test_execution_routes_require_authentication():
    client = TestClient(app)
    response = client.get("/api/v1/execution/positions")
    assert response.status_code == 401


def test_broker_routes_require_authentication():
    client = TestClient(app)
    response = client.get("/api/v1/broker/account")
    assert response.status_code == 401