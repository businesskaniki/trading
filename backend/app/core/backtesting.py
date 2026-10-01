"""Application-level dependency composition for AQE backtesting."""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any

from backtesting.composition import (
    BacktestComposition,
    BacktestSymbolSpecification,
)
from backtesting.engine import BacktestConfig
from backtesting.factory import BacktestFactory
from backtesting.market_data_loader import (
    HistoricalMarketDataLoadError,
    HistoricalMarketDataLoader,
)
from backtesting.service import BacktestService
from risk.config import RiskConfig
from strategies.core.base import StrategyConfig
from strategies.core.enums import StrategyMode

from app.database.models.symbol import Symbol
from app.database.session import SessionLocal
from app.repositories.account_symbol_repository import (
    AccountSymbolRepository,
)
from app.repositories.strategy_run_repository import StrategyRunRepository
from app.services.historical_data_service import HistoricalDataService
from app.services.mt5_bridge_service import MT5BridgeService

logger = logging.getLogger(__name__)


# ======================================================================
# HISTORICAL MARKET DATA
# ======================================================================


def create_historical_market_data_loader() -> HistoricalMarketDataLoader:
    """
    Create the read-only historical market-data loader used by
    backtests.

    The loader reads candles that have already been persisted into
    AQE's market-data tables.

    It does not communicate with MT5 and does not perform historical
    backfills.
    """

    return HistoricalMarketDataLoader(
        session_factory=SessionLocal,
    )


def create_historical_data_service() -> HistoricalDataService:
    """
    Create the application-level historical data service.

    HistoricalDataService is responsible for fetching historical
    candles from the MT5 bridge and persisting them into AQE's
    market-data database.

    This service is only invoked when persisted historical coverage
    is missing or incomplete.
    """

    bridge_service = MT5BridgeService()

    return HistoricalDataService(
        session_factory=SessionLocal,
        bridge_service=bridge_service,
    )


async def _historical_market_data_is_available(
    config: BacktestConfig,
) -> bool:
    """
    Verify that PostgreSQL contains complete historical coverage for
    the requested backtest.

    The same HistoricalMarketDataLoader used by the actual backtest
    is used here so that coverage validation has a single source of
    truth.

    Raises
    ------
    HistoricalMarketDataLoadError
        When one or more requested symbol/timeframe pairs are missing
        or do not completely cover the requested range.
    """

    loader = create_historical_market_data_loader()

    await loader.load(config)

    return True


async def prepare_historical_market_data(
    config: BacktestConfig,
) -> dict[str, Any]:
    """
    Prepare the historical market data required by a backtest.

    The process is database-first:

        1. Check persisted PostgreSQL coverage.
        2. If coverage is complete, do not contact MT5.
        3. If coverage is incomplete, perform MT5 backfill.
        4. Verify persisted coverage again.
        5. Return only after the complete range is available.

    PostgreSQL is the historical source consumed by the backtest.

    MT5 is only the historical acquisition/backfill source.
    """

    account_id = config.account_id

    if account_id is None:
        raise ValueError(
            "BacktestConfig.account_id is required for historical "
            "market-data preparation.",
        )

    start = config.start
    end = config.end

    if start is None:
        raise ValueError(
            "BacktestConfig.start is required for historical "
            "market-data preparation.",
        )

    if end is None:
        raise ValueError(
            "BacktestConfig.end is required for historical " "market-data preparation.",
        )

    if start >= end:
        raise ValueError(
            "BacktestConfig.start must be earlier than " "BacktestConfig.end.",
        )

    timeframe = "M15"

    # ------------------------------------------------------------------
    # STEP 1: PostgreSQL coverage check.
    # ------------------------------------------------------------------

    try:
        await _historical_market_data_is_available(config)

    except HistoricalMarketDataLoadError as coverage_error:
        logger.info(
            "Persisted historical coverage is incomplete; "
            "starting MT5 historical backfill. "
            "account_id=%s start=%s end=%s timeframe=%s reason=%s",
            account_id,
            start.isoformat(),
            end.isoformat(),
            timeframe,
            coverage_error,
        )

    else:
        logger.info(
            "Persisted historical coverage is complete; "
            "skipping MT5 historical backfill. "
            "account_id=%s start=%s end=%s timeframe=%s",
            account_id,
            start.isoformat(),
            end.isoformat(),
            timeframe,
        )

        return {
            "account_id": str(account_id),
            "start": start.isoformat(),
            "end": end.isoformat(),
            "timeframe": timeframe,
            "source": "postgresql",
            "backfill_required": False,
            "coverage_verified": True,
        }

    # ------------------------------------------------------------------
    # STEP 2: MT5 historical acquisition.
    # ------------------------------------------------------------------

    service = create_historical_data_service()

    result = await service.backfill_selected_symbols(
        account_id=account_id,
        start=start,
        end=end,
        timeframe=timeframe,
    )

    # ------------------------------------------------------------------
    # STEP 3: Verify the persisted result.
    # ------------------------------------------------------------------

    try:
        await _historical_market_data_is_available(config)

    except HistoricalMarketDataLoadError as coverage_error:
        logger.error(
            "Historical backfill completed but persisted coverage "
            "is still incomplete. "
            "account_id=%s start=%s end=%s timeframe=%s error=%s",
            account_id,
            start.isoformat(),
            end.isoformat(),
            timeframe,
            coverage_error,
        )

        raise RuntimeError(
            "Historical backfill completed, but the requested "
            "backtest range is still not fully covered by persisted "
            "market data.",
        ) from coverage_error

    logger.info(
        "Historical market-data preparation completed successfully. "
        "account_id=%s start=%s end=%s timeframe=%s source=mt5_backfill",
        account_id,
        start.isoformat(),
        end.isoformat(),
        timeframe,
    )

    if result is None:
        return {
            "account_id": str(account_id),
            "start": start.isoformat(),
            "end": end.isoformat(),
            "timeframe": timeframe,
            "source": "mt5_backfill",
            "backfill_required": True,
            "coverage_verified": True,
        }

    if isinstance(result, dict):
        return {
            **result,
            "source": "mt5_backfill",
            "backfill_required": True,
            "coverage_verified": True,
        }

    return {
        "account_id": str(account_id),
        "start": start.isoformat(),
        "end": end.isoformat(),
        "timeframe": timeframe,
        "source": "mt5_backfill",
        "backfill_required": True,
        "coverage_verified": True,
        "result": result,
    }


# ======================================================================
# STRATEGY CONFIGURATION
# ======================================================================


async def create_strategy_configs(
    config: BacktestConfig,
) -> list[StrategyConfig]:
    """
    Resolve enabled persisted StrategyRun records for the requested
    backtest account and convert them into runtime StrategyConfig
    objects.
    """

    account_id = config.account_id

    if account_id is None:
        raise ValueError(
            "BacktestConfig.account_id is required.",
        )

    user_id = getattr(
        config,
        "user_id",
        None,
    )

    if user_id is None:
        raise ValueError(
            "BacktestConfig.user_id is required for account-scoped "
            "strategy resolution.",
        )

    async with SessionLocal() as db:
        repository = StrategyRunRepository(db)

        strategy_runs = await repository.get_enabled_for_account(
            account_id=account_id,
            user_id=user_id,
        )

    if not strategy_runs:
        raise ValueError(
            f"No enabled strategies are configured for account " f"'{account_id}'.",
        )

    configs: list[StrategyConfig] = []

    for strategy_run in strategy_runs:
        strategy_id = str(strategy_run.id)

        strategy_name = (
            strategy_run.strategy_name.strip() if strategy_run.strategy_name else ""
        )

        if not strategy_name:
            continue

        symbols = [
            str(symbol).strip()
            for symbol in (strategy_run.symbols or [])
            if str(symbol).strip()
        ]

        timeframe = (
            strategy_run.timeframe.strip().upper() if strategy_run.timeframe else ""
        )

        if not timeframe:
            raise ValueError(
                f"StrategyRun '{strategy_run.id}' does not define " "a timeframe.",
            )

        if not symbols:
            raise ValueError(
                f"StrategyRun '{strategy_run.id}' does not define " "any symbols.",
            )

        metadata: dict[str, Any] = {
            "strategy_run_id": str(strategy_run.id),
            "strategy_version": strategy_run.strategy_version,
            "run_name": strategy_run.run_name,
        }

        if strategy_run.description:
            metadata["description"] = strategy_run.description

        if strategy_run.notes:
            metadata["notes"] = strategy_run.notes

        configs.append(
            StrategyConfig(
                strategy_id=strategy_id,
                strategy_name=strategy_name,
                mode=StrategyMode.BACKTEST,
                enabled=True,
                account_id=account_id,
                symbols=symbols,
                timeframes=[timeframe],
                parameters=dict(strategy_run.parameters or {}),
                metadata=metadata,
            ),
        )

    if not configs:
        raise ValueError(
            "No valid enabled strategy configurations were found "
            f"for account '{account_id}'.",
        )

    return configs


# ======================================================================
# ACCOUNT TRADING UNIVERSE
# ======================================================================


async def create_selected_symbols(
    config: BacktestConfig,
) -> list[BacktestSymbolSpecification]:
    """
    Resolve the enabled trading universe for the requested account.

    AccountSymbol contains both:

        broker_symbol
            The broker/MT5 symbol, for example ``XAUUSD.s``.

        symbol_id
            The foreign key to AQE's canonical Symbol record, for
            example ``XAUUSD``.

    Backtests operate on canonical AQE symbols.

    Therefore:

        AccountSymbol.broker_symbol
            -> used by MT5 historical acquisition

        Symbol.name
            -> used by PostgreSQL historical data and backtesting

    This separation is intentional and prevents broker-specific
    symbol suffixes from leaking into the persisted backtest domain.
    """

    account_id = config.account_id

    if account_id is None:
        raise ValueError(
            "BacktestConfig.account_id is required.",
        )

    user_id = getattr(
        config,
        "user_id",
        None,
    )

    if user_id is None:
        raise ValueError(
            "BacktestConfig.user_id is required for account-scoped "
            "symbol resolution.",
        )

    async with SessionLocal() as db:
        repository = AccountSymbolRepository(db)

        account_symbols = await repository.list_enabled_by_account(
            account_id=account_id,
        )

        specifications: list[BacktestSymbolSpecification] = []
        seen_symbols: set[str] = set()

        for account_symbol in account_symbols:
            broker_symbol = (
                account_symbol.broker_symbol.strip()
                if account_symbol.broker_symbol
                else ""
            )

            if not broker_symbol:
                continue

            # ----------------------------------------------------------
            # Resolve canonical AQE symbol.
            #
            # Do NOT access account_symbol.symbol here because that
            # relationship may be lazy-loaded and cause MissingGreenlet
            # errors with AsyncSession.
            # ----------------------------------------------------------

            symbol_model = await db.get(
                Symbol,
                account_symbol.symbol_id,
            )

            if symbol_model is None:
                raise ValueError(
                    f"Canonical Symbol '{account_symbol.symbol_id}' "
                    f"referenced by account symbol '{broker_symbol}' "
                    f"was not found.",
                )

            symbol = symbol_model.name.strip() if symbol_model.name else ""

            if not symbol:
                raise ValueError(
                    f"Canonical Symbol '{account_symbol.symbol_id}' "
                    f"has an empty name.",
                )

            symbol = symbol.upper()

            if symbol in seen_symbols:
                continue

            seen_symbols.add(symbol)

            contract_size: Decimal | None = None

            if account_symbol.contract_size is not None:
                try:
                    contract_size = Decimal(
                        str(account_symbol.contract_size),
                    )
                except Exception as exc:
                    raise ValueError(
                        f"Invalid contract_size for account symbol "
                        f"'{broker_symbol}' on account '{account_id}': "
                        f"{account_symbol.contract_size!r}.",
                    ) from exc

                if not contract_size.is_finite():
                    raise ValueError(
                        f"contract_size for account symbol "
                        f"'{broker_symbol}' must be finite.",
                    )

                if contract_size <= 0:
                    raise ValueError(
                        f"contract_size for account symbol "
                        f"'{broker_symbol}' must be positive.",
                    )

            logger.debug(
                "Resolved backtest symbol | "
                "account_id=%s broker_symbol=%s canonical_symbol=%s",
                account_id,
                broker_symbol,
                symbol,
            )

            specifications.append(
                BacktestSymbolSpecification(
                    symbol=symbol,
                    contract_size=contract_size,
                ),
            )

    if not specifications:
        raise ValueError(
            "No enabled trading symbols are configured for account " f"'{account_id}'.",
        )

    logger.info(
        "Resolved backtest trading universe | " "account_id=%s symbols=%s",
        account_id,
        tuple(spec.symbol for spec in specifications),
    )

    return specifications


# ======================================================================
# RISK CONFIGURATION
# ======================================================================


def create_risk_config(
    config: BacktestConfig,
) -> RiskConfig:
    """
    Create the risk configuration used by the real AQE RiskEngine.

    Backtests intentionally use the same RiskConfig contract as the
    production RiskEngine.
    """

    return RiskConfig()


# ======================================================================
# COMPOSITION
# ======================================================================


def create_backtest_composition() -> BacktestComposition:
    """
    Create the complete dependency composition for backtests.

    PostgreSQL is the persisted historical source.

    MT5 is the acquisition/backfill source only when the requested
    historical range is not already available.

    AccountSymbolRepository provides the account universe.

    StrategyRunRepository provides enabled strategy configurations.

    RiskConfig provides the production RiskEngine configuration.
    """

    market_data_loader = create_historical_market_data_loader()

    return BacktestComposition(
        market_data_loader=market_data_loader.load,
        historical_data_backfill=prepare_historical_market_data,
        strategy_config_factory=create_strategy_configs,
        risk_config_factory=create_risk_config,
        selected_symbols_factory=create_selected_symbols,
    )


# ======================================================================
# FACTORY
# ======================================================================


def create_backtest_factory() -> BacktestFactory:
    """
    Create the factory responsible for constructing independent
    BacktestOrchestrator instances.
    """

    composition = create_backtest_composition()

    return composition.create_factory()


# ======================================================================
# SERVICE
# ======================================================================


def create_backtest_service() -> BacktestService:
    """
    Create the application-level BacktestService.

    BacktestService owns lifecycle management while
    BacktestComposition owns simulation dependency construction.
    """

    factory = create_backtest_factory()

    return BacktestService(
        orchestrator_factory=factory.create,
    )


# ======================================================================
# APPLICATION-LEVEL SERVICE
# ======================================================================


backtest_service = create_backtest_service()


def get_backtest_service() -> BacktestService:
    """
    Return the application-level BacktestService.
    """

    return backtest_service
