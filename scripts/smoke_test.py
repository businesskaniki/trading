"""Local smoke checks for the Athena Quant Engine workspace.

The smoke test intentionally avoids external services. It verifies that the
backend app imports with development environment variables and that the shipped
risk calculator performs a basic calculation.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from decimal import Decimal


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
for path in (ROOT, BACKEND):
    path_text = str(path)
    if path_text not in sys.path:
        sys.path.insert(0, path_text)


def _ensure_backend_env() -> None:
    defaults = {
        "SECRET_KEY": "local-smoke-secret",
        "POSTGRES_HOST": "localhost",
        "POSTGRES_DB": "athena",
        "POSTGRES_USER": "athena",
        "POSTGRES_PASSWORD": "athena",
        "REDIS_HOST": "localhost",
        "SMTP_HOST": "localhost",
        "SMTP_USERNAME": "smoke",
        "SMTP_PASSWORD": "smoke",
        "SMTP_FROM_EMAIL": "smoke@example.com",
    }
    for key, value in defaults.items():
        os.environ.setdefault(key, value)


def check_backend_import() -> None:
    _ensure_backend_env()
    from app.main import app

    assert app.title == "Athena Quant Engine"


def check_engine_flow() -> None:
    from app.risk.calculator import RiskCalculator

    assert RiskCalculator.risk_amount(
        equity=Decimal("100000"),
        risk_percent=Decimal("1"),
    ) == Decimal("1000.00")


def main() -> None:
    check_backend_import()
    check_engine_flow()
    print("smoke checks passed")


if __name__ == "__main__":
    main()
