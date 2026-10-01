from __future__ import annotations

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
from app.repositories.account_symbol_repository import AccountSymbolRepository
from app.repositories.strategy_run_repository import StrategyRunRepository
from app.services.historical_data_service import HistoricalDataService
from app.services.mt5_bridge_service import MT5BridgeService


# ---------------------------------------------------------------------------
# Historical market-data dependencies
# ---------------------------------------------------------------------------


def create_historical_market_data_loader() -> HistoricalMarketDataLoader:
    """
    Create the read-only historical market-data loader used by backtests.

    The loader reads persisted market data from PostgreSQL. It does not
    perform broker communication or mutate historical data.
    """
    return HistoricalMarketDataLoader(
        session_factory=SessionLocal,
    )


async def load_historical_market_data(
    config: BacktestConfig,
):
    """
    Load persisted historical market data for a backtest.

    BacktestComposition expects its market-data dependency to be callable
    with BacktestConfig. The concrete HistoricalMarketDataLoader owns the
    actual PostgreSQL loading implementation.
    """
    loader = create_historical_market_data_loader()

    return await loader.load(config)


def create_historical_data_service() -> HistoricalDataService:
    """
    Create the historical-data service used when PostgreSQL coverage is
    incomplete and a backfill from the MT5 bridge is required.
    """
    return HistoricalDataService(
        session_factory=SessionLocal,
        mt5_bridge_service=MT5BridgeService(),
    )


async def _historical_market_data_is_available(
    config: BacktestConfig,
) -> bool:
    """
    Check whether persisted historical data fully covers the requested
    backtest period and symbols/timeframes.

    HistoricalMarketDataLoader.load() accepts the complete BacktestConfig.
    The loader is responsible for interpreting:

    - config.symbols
    - config.timeframes
    - config.start
    - config.end

    This check is intentionally read-only. If the loader cannot satisfy
    the requested historical-data requirements, HistoricalMarketDataLoadError
    is translated into False so the caller can initiate a backfill.
    """
    loader = create_historical_market_data_loader()

    try:
        await loader.load(config)
    except HistoricalMarketDataLoadError:
        return False

    return True


async def prepare_historical_market_data(
    config: BacktestConfig,
) -> dict[str, Any]:
    """
    Ensure that all historical market data required by the backtest exists.

    The workflow is:

    1. Check persisted PostgreSQL historical coverage.
    2. If coverage is incomplete, backfill every required timeframe.
    3. Verify the coverage again.
    4. Return normalized preparation information.

    The backtest itself still consumes persisted historical data through the
    HistoricalMarketDataLoader.
    """
    initial_available = await _historical_market_data_is_available(
        config,
    )

    if initial_available:
        return {
            "available": True,
            "backfilled": False,
            "symbols": list(config.symbols),
            "timeframes": list(config.timeframes),
            "start": config.start,
            "end": config.end,
        }

    historical_data_service = create_historical_data_service()

    backfilled_timeframes: list[str] = []

    for timeframe in config.timeframes:
        await historical_data_service.backfill_selected_symbols(
            account_id=config.account_id,
            start=config.start,
            end=config.end,
            timeframe=timeframe,
        )

        backfilled_timeframes.append(timeframe)

    final_available = await _historical_market_data_is_available(
        config,
    )

    if not final_available:
        raise HistoricalMarketDataLoadError(
            "Historical market data is still incomplete after backfill. "
            f"account_id={config.account_id}, "
            f"symbols={list(config.symbols)}, "
            f"timeframes={list(config.timeframes)}, "
            f"start={config.start}, "
            f"end={config.end}"
        )

    return {
        "available": True,
        "backfilled": True,
        "backfilled_timeframes": backfilled_timeframes,
        "symbols": list(config.symbols),
        "timeframes": list(config.timeframes),
        "start": config.start,
        "end": config.end,
    }


# ---------------------------------------------------------------------------
# Strategy configuration
# ---------------------------------------------------------------------------


def _resolve_strategy_timeframes(
    strategy_run: Any,
    config: BacktestConfig,
) -> list[str]:
    """
    Resolve the timeframe(s) applicable to one StrategyRun.

    StrategyRun currently stores a single ``timeframe`` field.

    Resolution order:

    1. StrategyRun.timeframe when explicitly configured.
    2. BacktestConfig.timeframes as the fallback.

    The helper also tolerates a list/tuple/set value defensively in case the
    persistence representation is changed later to support multiple
    timeframes.
    """
    strategy_timeframe = getattr(
        strategy_run,
        "timeframe",
        None,
    )

    if strategy_timeframe is None:
        return list(config.timeframes)

    if isinstance(strategy_timeframe, str):
        normalized = strategy_timeframe.strip()

        if not normalized:
            return list(config.timeframes)

        if "," in normalized:
            resolved = [
                item.strip()
                for item in normalized.split(",")
                if item.strip()
            ]

            if resolved:
                return resolved

            return list(config.timeframes)

        return [normalized]

    if isinstance(
        strategy_timeframe,
        (list, tuple, set, frozenset),
    ):
        resolved = [
            str(item).strip()
            for item in strategy_timeframe
            if item is not None and str(item).strip()
        ]

        if resolved:
            return resolved

    return list(config.timeframes)


def _resolve_strategy_id(
    strategy_run: Any,
) -> str:
    """
    Resolve the strategy definition identifier stored by StrategyRun.

    StrategyRun uses ``strategy_definition_id`` as the persisted foreign-key
    field, while StrategyConfig exposes that value as ``strategy_id``.
    """
    strategy_definition_id = getattr(
        strategy_run,
        "strategy_definition_id",
        None,
    )

    if strategy_definition_id is None:
        raise ValueError(
            "Enabled StrategyRun is missing strategy_definition_id"
        )

    return str(strategy_definition_id)


def _resolve_strategy_metadata(
    strategy_run: Any,
) -> dict[str, Any]:
    """
    Resolve optional strategy metadata.

    StrategyRun's persisted schema currently exposes parameters but does not
    expose a metadata column. If a future model adds metadata, it will be
    preserved automatically.
    """
    metadata = getattr(
        strategy_run,
        "metadata",
        None,
    )

    if metadata is None:
        return {}

    if isinstance(metadata, dict):
        return dict(metadata)

    try:
        return dict(metadata)
    except (TypeError, ValueError):
        return {}


async def create_strategy_configs(
    config: BacktestConfig,
) -> list[StrategyConfig]:
    """
    Resolve the enabled account strategies into isolated BACKTEST strategy
    configurations.

    StrategyRun remains the source of truth for which strategies are enabled
    for the account.

    StrategyRun fields are mapped into the strategy-engine contract as
    follows:

        strategy_definition_id -> StrategyConfig.strategy_id
        strategy_name         -> StrategyConfig.strategy_name
        timeframe             -> StrategyConfig.timeframes
        parameters            -> StrategyConfig.parameters

    StrategyRun stores one timeframe, while StrategyConfig supports a list
    of timeframes. Therefore, each StrategyRun becomes one StrategyConfig
    with its resolved StrategyRun.timeframe represented as a one-element
    ``timeframes`` list.

    If StrategyRun.timeframe is empty, the backtest-level timeframes are
    used as the fallback.
    """
    async with SessionLocal() as db:
        repository = StrategyRunRepository(db)

        strategy_runs = await repository.get_enabled_for_account(
            account_id=config.account_id,
            user_id=config.user_id,
        )

        strategy_configs: list[StrategyConfig] = []

        for strategy_run in strategy_runs:
            strategy_id = _resolve_strategy_id(
                strategy_run,
            )

            strategy_name = str(
                strategy_run.strategy_name,
            ).strip()

            if not strategy_name:
                raise ValueError(
                    "Enabled StrategyRun is missing strategy_name"
                )

            strategy_timeframes = _resolve_strategy_timeframes(
                strategy_run,
                config,
            )

            if not strategy_timeframes:
                raise ValueError(
                    f"Enabled strategy {strategy_name!r} has no "
                    "resolved timeframes"
                )

            parameters = dict(
                strategy_run.parameters or {},
            )

            metadata = _resolve_strategy_metadata(
                strategy_run,
            )

            strategy_configs.append(
                StrategyConfig(
                    strategy_id=strategy_id,
                    strategy_name=strategy_name,
                    mode=StrategyMode.BACKTEST,
                    account_id=config.account_id,
                    symbols=list(config.symbols),
                    timeframes=strategy_timeframes,
                    parameters=parameters,
                    metadata=metadata,
                )
            )

        return strategy_configs


# ---------------------------------------------------------------------------
# Risk configuration
# ---------------------------------------------------------------------------


def create_risk_config(
    config: BacktestConfig,
) -> RiskConfig:
    """
    Create the risk configuration used by the real RiskEngine during
    backtesting.

    Backtests intentionally use the same risk engine as live/paper
    execution. The execution side is simulated separately.
    """
    return RiskConfig()


# ---------------------------------------------------------------------------
# Symbol metadata
# ---------------------------------------------------------------------------


def _decimal_or_none(
    value: Any,
    *,
    field_name: str,
) -> Decimal | None:
    """
    Convert a nullable database numeric value to Decimal and validate it.

    Nullable fields remain None. Any supplied numeric value must be finite
    and strictly positive.
    """
    if value is None:
        return None

    try:
        decimal_value = Decimal(
            str(value),
        )
    except Exception as exc:
        raise ValueError(
            f"Invalid {field_name}: {value!r}"
        ) from exc

    if not decimal_value.is_finite():
        raise ValueError(
            f"{field_name} must be finite; got {value!r}"
        )

    if decimal_value <= Decimal("0"):
        raise ValueError(
            f"{field_name} must be greater than zero; got {value!r}"
        )

    return decimal_value


def _validate_account_symbol_metadata(
    *,
    broker_symbol: str,
    digits: int,
    point: Decimal,
    tick_size: Decimal,
    contract_size: Decimal | None,
    min_volume: Decimal | None,
    max_volume: Decimal | None,
    volume_step: Decimal | None,
) -> None:
    """
    Validate the trading metadata persisted on AccountSymbol.

    The database model already defines these fields, but validation here
    keeps invalid instrument metadata from silently entering the backtest
    risk engine.
    """
    if not broker_symbol:
        raise ValueError(
            "broker_symbol must not be empty"
        )

    if digits < 0:
        raise ValueError(
            "digits must be greater than or equal to zero; "
            f"got {digits}"
        )

    if not point.is_finite() or point <= Decimal("0"):
        raise ValueError(
            "point must be finite and greater than zero; "
            f"got {point}"
        )

    if not tick_size.is_finite() or tick_size <= Decimal("0"):
        raise ValueError(
            "tick_size must be finite and greater than zero; "
            f"got {tick_size}"
        )

    if contract_size is not None and contract_size <= Decimal("0"):
        raise ValueError(
            "contract_size must be greater than zero "
            "when supplied"
        )

    if min_volume is not None and min_volume <= Decimal("0"):
        raise ValueError(
            "min_volume must be greater than zero "
            "when supplied"
        )

    if max_volume is not None and max_volume <= Decimal("0"):
        raise ValueError(
            "max_volume must be greater than zero "
            "when supplied"
        )

    if volume_step is not None and volume_step <= Decimal("0"):
        raise ValueError(
            "volume_step must be greater than zero "
            "when supplied"
        )

    if (
        min_volume is not None
        and max_volume is not None
        and max_volume < min_volume
    ):
        raise ValueError(
            "max_volume must be greater than or equal to "
            "min_volume"
        )


async def create_selected_symbols(
    config: BacktestConfig,
) -> list[BacktestSymbolSpecification]:
    """
    Resolve the account's enabled symbols into complete backtest symbol
    specifications.

    AccountSymbol is the source of truth for broker-specific trading
    metadata. The canonical Symbol model supplies the AQE symbol name used
    by the strategy and historical-data layers.

    Metadata preserved from AccountSymbol:

    - broker_symbol
    - digits
    - point
    - tick_size
    - contract_size
    - min_volume
    - max_volume
    - volume_step

    This is important because the RiskEngine needs the instrument's actual
    tick/volume constraints when calculating position size.
    """
    account_id = config.account_id
    user_id = config.user_id

    if account_id is None:
        raise ValueError(
            "BacktestConfig.account_id is required to resolve "
            "selected symbols"
        )

    if user_id is None:
        raise ValueError(
            "BacktestConfig.user_id is required to resolve "
            "selected symbols"
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

            symbol_model = await db.get(
                Symbol,
                account_symbol.symbol_id,
            )

            if symbol_model is None:
                continue

            symbol = symbol_model.name.strip().upper()

            if not symbol:
                continue

            if symbol in seen_symbols:
                continue

            try:
                digits = int(
                    account_symbol.digits,
                )
            except (
                TypeError,
                ValueError,
            ) as exc:
                raise ValueError(
                    f"Invalid digits for account symbol "
                    f"{symbol!r}: "
                    f"{account_symbol.digits!r}"
                ) from exc

            point = _decimal_or_none(
                account_symbol.point,
                field_name=f"{symbol}.point",
            )

            tick_size = _decimal_or_none(
                account_symbol.tick_size,
                field_name=f"{symbol}.tick_size",
            )

            contract_size = _decimal_or_none(
                account_symbol.contract_size,
                field_name=f"{symbol}.contract_size",
            )

            min_volume = _decimal_or_none(
                account_symbol.min_volume,
                field_name=f"{symbol}.min_volume",
            )

            max_volume = _decimal_or_none(
                account_symbol.max_volume,
                field_name=f"{symbol}.max_volume",
            )

            volume_step = _decimal_or_none(
                account_symbol.volume_step,
                field_name=f"{symbol}.volume_step",
            )

            if point is None:
                raise ValueError(
                    f"Account symbol {symbol!r} has no valid "
                    "point value"
                )

            if tick_size is None:
                raise ValueError(
                    f"Account symbol {symbol!r} has no valid "
                    "tick_size value"
                )

            _validate_account_symbol_metadata(
                broker_symbol=broker_symbol,
                digits=digits,
                point=point,
                tick_size=tick_size,
                contract_size=contract_size,
                min_volume=min_volume,
                max_volume=max_volume,
                volume_step=volume_step,
            )

            specifications.append(
                BacktestSymbolSpecification(
                    symbol=symbol,
                    broker_symbol=broker_symbol,
                    digits=digits,
                    point=point,
                    tick_size=tick_size,
                    contract_size=contract_size,
                    min_volume=min_volume,
                    max_volume=max_volume,
                    volume_step=volume_step,
                )
            )

            seen_symbols.add(symbol)

        return specifications


# ---------------------------------------------------------------------------
# Backtest composition
# ---------------------------------------------------------------------------


def create_backtest_composition() -> BacktestComposition:
    """
    Create the application-level backtest composition root.

    The composition root injects application concerns into the domain-level
    backtesting components without making the backtesting engine aware of
    SQLAlchemy repositories, FastAPI dependencies, or MT5 services.
    """
    return BacktestComposition(
        market_data_loader=load_historical_market_data,
        historical_data_backfill=prepare_historical_market_data,
        strategy_config_factory=create_strategy_configs,
        risk_config_factory=create_risk_config,
        selected_symbols_factory=create_selected_symbols,
    )


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def create_backtest_factory() -> BacktestFactory:
    """
    Create the application backtest factory.
    """
    return BacktestFactory(
        composition=create_backtest_composition(),
    )


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


def create_backtest_service() -> BacktestService:
    """
    Create the application backtest service.

    BacktestService expects an orchestrator factory callable rather than
    the factory object itself. BacktestFactory.create is therefore injected
    as the lifecycle service's orchestrator factory.
    """
    factory = create_backtest_factory()

    return BacktestService(
        orchestrator_factory=factory.create,
    )


backtest_service = create_backtest_service()


def get_backtest_service() -> BacktestService:
    """
    Return the application-level backtest service.
    """
    return backtest_service