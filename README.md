# Athena Quant Engine

Athena Quant Engine is a modular trading-system workspace. The repository now includes the planned engine, service, infrastructure, configuration, strategy, data, test, script, and documentation layout while preserving the existing backend, MT5 bridge, and frontend applications.

## Main Areas

- `backend/` — existing FastAPI dashboard/backend API and persistence layer.
- `mt5_bridge/` — existing MetaTrader 5 bridge service.
- `frontend/` — existing dashboard frontend.
- `engine/` — core trading engine package with broker, market, strategy, execution, risk, portfolio, analytics, backtesting, ML, database, monitoring, and utility modules.
- `services/` — service boundaries for market data, strategy dispatch, execution, dashboard API, notifications, and scheduling.
- `configs/` — YAML configuration defaults for app, broker, database, Redis, logging, execution, risk, symbols, and strategy profiles.
- `infrastructure/` and `docker/` — compose files, nginx configuration, and container scaffolding.
- `strategies/` — strategy-family modules for trend, breakout, liquidity, SMC, mean reversion, scalping, and experiments.
- `tests/` — top-level test-suite layout for unit, integration, backtesting, paper-trading, stress, and fixtures.
- `docs/` — architecture, API, strategy, risk, deployment, and roadmap documentation stubs.

## Backend Checks

```bash
cd backend
pytest -q
```

For import/compile checks that load the FastAPI settings, provide environment variables or copy `.env.example` to `.env` and adjust values.
