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

## Implemented Engine Primitives

The scaffold includes working primitives for:

- in-process events (`engine.events.bus.EventBus`), publishers, subscribers, and memory handlers;
- paper-broker execution (`engine.broker.paper.PaperBroker`) and order routing (`engine.execution.engine.ExecutionEngine`);
- market models and helpers for ticks, candles, symbols, SMA, and true range;
- strategy signals, registries, and manager dispatch;
- risk position sizing, exposure, drawdown, and validation;
- portfolio account/position equity calculation;
- analytics helpers for win rate and profit factor;
- service wrappers for strategy running and order execution.


## Step-by-Step Completion Plan

The app will be completed incrementally so each phase can be verified before the next one starts.

1. **Local verification tooling** — provide repeatable commands for tests, compilation, frontend build, Docker config validation, and no-service smoke checks.
2. **Local runtime stack** — make Postgres, Redis, backend, and frontend start reliably from Compose with seeded demo data.
3. **Backend integration tests** — test authenticated API flows against a test database.
4. **Paper trading loop** — wire market data, strategies, risk validation, execution, portfolio, and analytics through the paper broker.
5. **Broker adapters** — add MT5/demo broker connection, order lifecycle, position sync, and guarded live-trading switches.
6. **Production hardening** — add monitoring, alerts, backups, deployment docs, and CI/CD publishing.

For Step 1, run `make check` to execute backend tests, Python compile checks, smoke checks, and the frontend production build.
