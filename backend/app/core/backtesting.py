"""Application-level dependency composition for AQE backtesting."""

from __future__ import annotations

import logging
from datetime import timedelta
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
from app.repositories.trading_account_repository import (
    TradingAccountRepository,
)
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
        3. If coverage is incomplete, perform MT5 backfill in
           bounded seven-day chunks for every requested timeframe.
        4. Verify persisted coverage across the entire requested
           range again.
        5. Return only after the complete requested range is
           available.

    PostgreSQL is the historical source consumed by the backtest.

    MT5 is only the historical acquisition/backfill source.

    Chunked acquisition prevents long-duration requests, including
    one-year backtests, from being sent to the MT5 bridge as one
    very large historical request.
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

    # ------------------------------------------------------------------
    # Resolve requested timeframes.
    #
    # BacktestComposition resolves the timeframe universe from all
    # enabled strategy configurations before this function is called.
    #
    # Do not hard-code M15 here. A backtest may contain strategies
    # operating on different timeframes.
    # ------------------------------------------------------------------

    timeframes = tuple(
        dict.fromkeys(
            timeframe.strip().upper()
            for timeframe in config.timeframes
            if isinstance(timeframe, str) and timeframe.strip()
        ),
    )

    if not timeframes:
        raise ValueError(
            "BacktestConfig.timeframes must contain at least one "
            "resolved timeframe for historical market-data preparation.",
        )

    # ------------------------------------------------------------------
    # STEP 1: PostgreSQL coverage check.
    # ------------------------------------------------------------------

    try:
        await _historical_market_data_is_available(config)

    except HistoricalMarketDataLoadError as coverage_error:
        logger.info(
            "Persisted historical coverage is incomplete; "
            "starting MT5 historical backfill. "
            "account_id=%s start=%s end=%s timeframes=%s reason=%s",
            account_id,
            start.isoformat(),
            end.isoformat(),
            timeframes,
            coverage_error,
        )

    else:
        logger.info(
            "Persisted historical coverage is complete; "
            "skipping MT5 historical backfill. "
            "account_id=%s start=%s end=%s timeframes=%s",
            account_id,
            start.isoformat(),
            end.isoformat(),
            timeframes,
        )

        return {
            "account_id": str(account_id),
            "start": start.isoformat(),
            "end": end.isoformat(),
            "timeframes": list(timeframes),
            "source": "postgresql",
            "backfill_required": False,
            "coverage_verified": True,
        }

    # ------------------------------------------------------------------
    # STEP 2: MT5 historical acquisition.
    #
    # Historical requests are deliberately bounded.
    #
    # One year therefore becomes approximately 53 seven-day windows
    # instead of one large MT5 request.
    # ------------------------------------------------------------------

    service = create_historical_data_service()

    chunk_size = timedelta(days=7)

    backfill_results: list[dict[str, Any]] = []

    for timeframe in timeframes:
        chunk_start = start

        while chunk_start < end:
            chunk_end = min(
                chunk_start + chunk_size,
                end,
            )

            logger.info(
                "Starting MT5 historical backfill chunk. "
                "account_id=%s start=%s end=%s timeframe=%s",
                account_id,
                chunk_start.isoformat(),
                chunk_end.isoformat(),
                timeframe,
            )

            result = await service.backfill_selected_symbols(
                account_id=account_id,
                start=chunk_start,
                end=chunk_end,
                timeframe=timeframe,
            )

            backfill_results.append(
                {
                    "timeframe": timeframe,
                    "start": chunk_start.isoformat(),
                    "end": chunk_end.isoformat(),
                    "result": result,
                },
            )

            logger.info(
                "MT5 historical backfill chunk completed. "
                "account_id=%s start=%s end=%s timeframe=%s",
                account_id,
                chunk_start.isoformat(),
                chunk_end.isoformat(),
                timeframe,
            )

            chunk_start = chunk_end

    # ------------------------------------------------------------------
    # STEP 3: Verify the persisted result.
    #
    # The same loader used by the actual backtest is used again so
    # there remains one authoritative coverage check.
    #
    # Importantly, this validates the ENTIRE requested range, not
    # merely the final chunk.
    # ------------------------------------------------------------------

    try:
        await _historical_market_data_is_available(config)

    except HistoricalMarketDataLoadError as coverage_error:
        logger.error(
            "Historical backfill completed but persisted coverage "
            "is still incomplete. "
            "account_id=%s start=%s end=%s timeframes=%s error=%s",
            account_id,
            start.isoformat(),
            end.isoformat(),
            timeframes,
            coverage_error,
        )

        raise RuntimeError(
            "Historical backfill completed, but the requested "
            "backtest range is still not fully covered by persisted "
            "market data.",
        ) from coverage_error

    logger.info(
        "Historical market-data preparation completed successfully. "
        "account_id=%s start=%s end=%s timeframes=%s "
        "chunks=%s source=mt5_backfill",
        account_id,
        start.isoformat(),
        end.isoformat(),
        timeframes,
        len(backfill_results),
    )

    # ------------------------------------------------------------------
    # Normalize the backfill response.
    # ------------------------------------------------------------------

    if len(timeframes) == 1 and len(backfill_results) == 1:
        single_result = backfill_results[0]["result"]
        timeframe = timeframes[0]

        if isinstance(single_result, dict):
            return {
                **single_result,
                "account_id": str(account_id),
                "start": start.isoformat(),
                "end": end.isoformat(),
                "timeframe": timeframe,
                "timeframes": list(timeframes),
                "source": "mt5_backfill",
                "backfill_required": True,
                "coverage_verified": True,
                "backfill_chunks": 1,
            }

        if single_result is None:
            return {
                "account_id": str(account_id),
                "start": start.isoformat(),
                "end": end.isoformat(),
                "timeframe": timeframe,
                "timeframes": list(timeframes),
                "source": "mt5_backfill",
                "backfill_required": True,
                "coverage_verified": True,
                "backfill_chunks": 1,
            }

        return {
            "account_id": str(account_id),
            "start": start.isoformat(),
            "end": end.isoformat(),
            "timeframe": timeframe,
            "timeframes": list(timeframes),
            "source": "mt5_backfill",
            "backfill_required": True,
            "coverage_verified": True,
            "backfill_chunks": 1,
            "result": single_result,
        }

    return {
        "account_id": str(account_id),
        "start": start.isoformat(),
        "end": end.isoformat(),
        "timeframes": list(timeframes),
        "source": "mt5_backfill",
        "backfill_required": True,
        "coverage_verified": True,
        "backfill_chunks": len(backfill_results),
        "results": backfill_results,
    }


# ======================================================================
# ACCOUNT LEVERAGE
# ======================================================================


async def resolve_account_leverage(
    config: BacktestConfig,
) -> Decimal:
    """
    Resolve the trading-account leverage used by the backtest.

    Leverage is account configuration and therefore comes from the
    persisted TradingAccount record rather than from the public
    backtest request.

    The resolved leverage is later converted by the backtest execution
    layer into:

        margin_rate = 1 / leverage
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
            "leverage resolution.",
        )

    async with SessionLocal() as db:
        repository = TradingAccountRepository(db)

        account = await repository.get_by_id_and_user(
            account_id=account_id,
            user_id=user_id,
        )

    if account is None:
        raise ValueError(
            f"Trading account '{account_id}' was not found.",
        )

    if account.leverage is None:
        raise ValueError(
            f"Trading account '{account_id}' does not have a resolved "
            "leverage value.",
        )

    try:
        leverage = Decimal(
            str(account.leverage),
        )
    except Exception as exc:
        raise ValueError(
            f"Invalid leverage configured for trading account "
            f"'{account_id}': {account.leverage!r}.",
        ) from exc

    if not leverage.is_finite():
        raise ValueError(
            f"Leverage for trading account '{account_id}' must be finite.",
        )

    if leverage <= Decimal("0"):
        raise ValueError(
            f"Leverage for trading account '{account_id}' must be "
            "greater than zero.",
        )

    logger.debug(
        "Resolved backtest account leverage | " "account_id=%s leverage=%s",
        account_id,
        leverage,
    )

    return leverage


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
                f"StrategyRun '{strategy_run.id}' does not define " f"a timeframe.",
            )

        if not symbols:
            raise ValueError(
                f"StrategyRun '{strategy_run.id}' does not define " f"any symbols.",
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

    Daily-loss protection remains enabled.

    Persistent high-water-mark drawdown protection is disabled for
    research backtests so a long-running historical simulation is not
    permanently halted merely because its equity previously crossed
    the live-style drawdown threshold.

    Drawdown is still calculated by the RiskEngine for reporting and
    diagnostics.
    """

    return RiskConfig(
        enforce_daily_loss_limit=True,
        enforce_drawdown_limit=False,
    )


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

    TradingAccountRepository provides account leverage.

    RiskConfig provides the production RiskEngine configuration.
    """

    market_data_loader = create_historical_market_data_loader()

    return BacktestComposition(
        market_data_loader=market_data_loader.load,
        historical_data_backfill=prepare_historical_market_data,
        strategy_config_factory=create_strategy_configs,
        risk_config_factory=create_risk_config,
        selected_symbols_factory=create_selected_symbols,
        account_leverage_factory=resolve_account_leverage,
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
