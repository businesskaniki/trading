"""Composition root for account-level multi-strategy backtesting."""

from __future__ import annotations

import inspect
import logging

from collections.abc import Awaitable
from collections.abc import Callable
from collections.abc import Iterable
from dataclasses import dataclass
from dataclasses import fields
from dataclasses import replace
from decimal import Decimal
from typing import Any

from risk.config import RiskConfig
from risk.engine import RiskEngine

from strategies.bootstrap import strategy_bootstrap
from strategies.core import StrategyConfig
from strategies.core.enums import StrategyMode
from strategies.runtime.manager import StrategyManager

from .engine import BacktestConfig
from .engine import BacktestEngine
from .factory import BacktestFactory
from .market import BacktestMarketData
from .market_data_view import BacktestMarketDataView
from .orchestration import BacktestOrchestrator
from .orchestration import BacktestRiskConfiguration

logger = logging.getLogger(__name__)


# ======================================================================
# FACTORY CONTRACTS
# ======================================================================


BacktestMarketDataLoader = Callable[
    [BacktestConfig],
    BacktestMarketData | Awaitable[BacktestMarketData],
]


RiskConfigFactory = Callable[
    [BacktestConfig],
    RiskConfig | Awaitable[RiskConfig],
]


StrategyConfigFactory = Callable[
    [BacktestConfig],
    Iterable[StrategyConfig] | Awaitable[Iterable[StrategyConfig]],
]


@dataclass(frozen=True, slots=True)
class BacktestSymbolSpecification:
    """
    Account-specific symbol metadata required by the backtest.

    The composition root intentionally uses a small domain object rather
    than an ORM model. This keeps the backtesting package independent
    from PostgreSQL and application persistence details.
    """

    symbol: str
    contract_size: Decimal | None = None


SelectedSymbol = str | BacktestSymbolSpecification


SelectedSymbolsFactory = Callable[
    [BacktestConfig],
    Iterable[SelectedSymbol] | Awaitable[Iterable[SelectedSymbol]],
]


HistoricalDataBackfill = Callable[
    [BacktestConfig],
    Any | Awaitable[Any],
]


# ======================================================================
# ERRORS
# ======================================================================


class BacktestCompositionError(Exception):
    """Raised when the backtest dependency graph cannot be composed."""


# ======================================================================
# COMPOSITION ROOT
# ======================================================================


@dataclass(slots=True)
class BacktestComposition:
    """
    Composition root for one complete account-level multi-strategy
    backtest.

    The composition layer resolves:

        BacktestConfig
              |
              +-------------------------+
              |                         |
              v                         v
       strategy configs        account symbol specs
              |                         |
              +------------+------------+
                           |
                           v
                  resolved strategy configs
                           |
                           v
                    timeframe union
                           |
                           v
                resolved BacktestConfig
                           |
                           v
              historical data preparation
                           |
                           v
                persisted market data
                           |
          +----------------+----------------+
          |                |                |
          v                v                v
     market data       RiskEngine     StrategyManager
                                         |
                              +----------+----------+
                              |          |          |
                              v          v          v
                           strategy   strategy   strategy
                              A          B          C
                                         |
                                         v
                                  BacktestEngine
                                         |
                                         v
                                  BacktestOrchestrator

    This layer wires dependencies only.

    It does not:
        - implement strategy logic
        - calculate risk
        - execute trades
        - start or stop the strategy runtime
        - start or stop the simulation
        - persist backtest results
        - communicate with Redis
        - directly query PostgreSQL
        - communicate directly with MT5

    Historical data preparation is injected through
    ``historical_data_backfill``. The actual application service behind
    that dependency is responsible for communicating with persistence
    and the MT5 bridge.

    Runtime lifecycle ownership belongs to BacktestOrchestrator.
    """

    market_data_loader: BacktestMarketDataLoader
    risk_config_factory: RiskConfigFactory
    strategy_config_factory: StrategyConfigFactory
    selected_symbols_factory: SelectedSymbolsFactory
    historical_data_backfill: HistoricalDataBackfill | None = None

    # ==================================================================
    # BUILD
    # ==================================================================

    async def build(
        self,
        config: BacktestConfig,
    ) -> BacktestOrchestrator:
        """
        Build a fully isolated account-level multi-strategy backtest.

        The supplied BacktestConfig defines the account and historical
        period. Strategy configuration and account symbols are resolved
        through the injected factories.

        Historical data preparation occurs after the complete symbol and
        timeframe universe has been resolved, but before the read-only
        HistoricalMarketDataLoader is invoked.

        This method only constructs the runtime graph. It does not start
        the StrategyManager or the BacktestEngine.

        BacktestOrchestrator owns runtime startup and shutdown.
        """

        if not isinstance(
            config,
            BacktestConfig,
        ):
            raise TypeError(
                "config must be an instance of BacktestConfig.",
            )

        if config.account_id is None:
            raise BacktestCompositionError(
                "BacktestConfig.account_id is required.",
            )

        # Determine which fields actually exist on BacktestConfig.
        #
        # This keeps the composition layer compatible with the current
        # configuration model while still supporting optional
        # contract-size metadata when that field exists.
        config_field_names = {
            field_info.name
            for field_info in fields(config)
        }

        existing_contract_sizes = getattr(
            config,
            "contract_sizes",
            {},
        )

        # ==============================================================
        # 1. Resolve enabled strategies
        # ==============================================================

        try:
            strategy_configs = await self._resolve(
                self.strategy_config_factory,
                config,
            )

            resolved_strategy_configs = self._normalize_strategy_configs(
                strategy_configs,
                config,
            )

        except Exception as exc:
            logger.exception(
                "Backtest composition failed while resolving strategy "
                "configurations. account_id=%s",
                config.account_id,
            )

            raise BacktestCompositionError(
                "Failed to resolve enabled strategy configurations "
                f"for account '{config.account_id}': "
                f"{type(exc).__name__}: {exc}",
            ) from exc

        if not resolved_strategy_configs:
            raise BacktestCompositionError(
                "No enabled strategies are configured for account "
                f"{config.account_id}.",
            )

        # ==============================================================
        # 2. Resolve account trading universe and symbol metadata
        # ==============================================================

        try:
            selected_symbols = await self._resolve(
                self.selected_symbols_factory,
                config,
            )

            (
                resolved_symbols,
                resolved_contract_sizes,
            ) = self._normalize_symbol_specifications(
                selected_symbols,
                existing_contract_sizes=existing_contract_sizes,
            )

        except Exception as exc:
            logger.exception(
                "Backtest composition failed while resolving account "
                "symbols. account_id=%s",
                config.account_id,
            )

            raise BacktestCompositionError(
                "Failed to resolve enabled trading symbols "
                f"for account '{config.account_id}': "
                f"{type(exc).__name__}: {exc}",
            ) from exc

        if not resolved_symbols:
            raise BacktestCompositionError(
                "No enabled trading symbols are configured for account "
                f"{config.account_id}.",
            )

        # ==============================================================
        # 3. Apply account symbol universe to every strategy
        #
        # Strategy-specific timeframe/parameter/metadata configuration
        # remains intact.
        # ==============================================================

        try:
            resolved_strategy_configs = tuple(
                self._prepare_strategy_config(
                    strategy_config=strategy_config,
                    account_config=config,
                    symbols=resolved_symbols,
                )
                for strategy_config in resolved_strategy_configs
            )

        except Exception as exc:
            logger.exception(
                "Backtest composition failed while preparing strategy "
                "configurations. account_id=%s",
                config.account_id,
            )

            raise BacktestCompositionError(
                "Failed to prepare strategy configurations "
                f"for account '{config.account_id}': "
                f"{type(exc).__name__}: {exc}",
            ) from exc

        # ==============================================================
        # 4. Resolve union of strategy timeframes
        # ==============================================================

        resolved_timeframes = self._collect_timeframes(
            resolved_strategy_configs,
        )

        if not resolved_timeframes:
            raise BacktestCompositionError(
                "Active strategies do not define any required timeframes.",
            )

        # ==============================================================
        # 5. Build resolved account-level BacktestConfig
        #
        # BacktestConfig enforces:
        #
        #     period
        #
        # XOR
        #
        #     start + end
        #
        # Therefore a relative period that has already been resolved
        # into concrete dates must clear period before reconstruction.
        # ==============================================================

        resolved_config_values: dict[str, Any] = {
            "period": None,
            "start": config.start,
            "end": config.end,
            "symbols": resolved_symbols,
            "timeframes": resolved_timeframes,
        }

        # Only pass contract_sizes to replace() when the actual
        # BacktestConfig model defines that field.
        if "contract_sizes" in config_field_names:
            resolved_config_values["contract_sizes"] = (
                resolved_contract_sizes
            )

        try:
            resolved_config = replace(
                config,
                **resolved_config_values,
            )

        except Exception as exc:
            logger.exception(
                "Backtest composition failed while constructing the "
                "resolved BacktestConfig. account_id=%s",
                config.account_id,
            )

            raise BacktestCompositionError(
                "Failed to construct the resolved BacktestConfig "
                f"for account '{config.account_id}': "
                f"{type(exc).__name__}: {exc}",
            ) from exc

        # ==============================================================
        # 6. Ensure historical market data is available
        #
        # IMPORTANT:
        #
        # The historical loader is deliberately read-only.
        #
        # Historical data preparation happens before the loader and is
        # injected into this composition root. The injected application
        # service is responsible for determining whether a backfill is
        # required and, when necessary, obtaining the data from the
        # configured broker/MT5 bridge and persisting it.
        #
        # If no backfill dependency is configured, composition retains
        # the previous read-only behavior and the loader becomes the
        # final historical coverage validator.
        # ==============================================================

        await self._prepare_historical_data(
            resolved_config,
            resolved_symbols=resolved_symbols,
            resolved_timeframes=resolved_timeframes,
        )

        # ==============================================================
        # 7. Load persisted historical market data
        # ==============================================================

        try:
            market_data = await self._resolve(
                self.market_data_loader,
                resolved_config,
            )

            if not isinstance(
                market_data,
                BacktestMarketData,
            ):
                raise TypeError(
                    "market_data_loader must return BacktestMarketData.",
                )

            market_data.finalize()

        except Exception as exc:
            logger.exception(
                "Backtest composition failed while loading historical "
                "market data. account_id=%s symbols=%s timeframes=%s",
                config.account_id,
                resolved_symbols,
                resolved_timeframes,
            )

            raise BacktestCompositionError(
                "Failed to load historical market data "
                f"for account '{config.account_id}': "
                f"{type(exc).__name__}: {exc}",
            ) from exc

        # ==============================================================
        # 8. Create isolated StrategyManager
        #
        # IMPORTANT:
        #
        # StrategyManager is constructed here but NOT started here.
        #
        # BacktestOrchestrator.run() owns the runtime lifecycle and
        # starts the manager immediately before the simulation begins.
        #
        # This prevents:
        #
        #     composition -> start()
        #     orchestrator -> start()
        #
        # which would result in a double-start lifecycle.
        # ==============================================================

        strategy_manager = StrategyManager()

        # ==============================================================
        # 9. Create simulation-aware market-data view
        #
        # No current simulation timestamp is exposed initially.
        # Strategies only see candles after BacktestEngine advances
        # the clock to that candle.
        # ==============================================================

        market_data_view = BacktestMarketDataView(
            market_data,
            current_time=None,
        )

        created_strategy_ids: list[str] = []

        try:
            # ==========================================================
            # 10. Bootstrap the strategy registry
            #
            # BACKTEST does not start through AQEEngine.start(), so it
            # cannot rely on the normal LIVE/PAPER engine startup path
            # to discover strategy implementations.
            #
            # StrategyBootstrap performs discovery/import only. It does
            # not instantiate strategies, start them, subscribe to
            # market data, publish signals, or place orders.
            #
            # This guarantees that StrategyManager.create() below can
            # resolve registered strategy names.
            # ==========================================================

            bootstrap_result = await strategy_bootstrap.start()

            logger.info(
                "Backtest strategy registry bootstrapped. "
                "account_id=%s imported_modules=%d "
                "registered_strategies=%s",
                config.account_id,
                len(bootstrap_result.imported_modules),
                bootstrap_result.registered_strategies,
            )

            # ==========================================================
            # 11. Create one runtime instance per active strategy
            # ==========================================================

            for strategy_config in resolved_strategy_configs:
                instance = await strategy_manager.create(
                    strategy_config,
                    market_data=market_data_view,
                    auto_start=False,
                )

                created_strategy_ids.append(
                    instance.strategy_id,
                )

            # ==========================================================
            # 12. Resolve RiskConfig
            # ==============================================================

            risk_config = await self._resolve(
                self.risk_config_factory,
                resolved_config,
            )

            if not isinstance(
                risk_config,
                RiskConfig,
            ):
                raise TypeError(
                    "risk_config_factory must return RiskConfig.",
                )

            risk_configuration = BacktestRiskConfiguration(
                config=risk_config,
            )

            # ==========================================================
            # 13. Create isolated real RiskEngine
            # ==========================================================

            risk_engine = RiskEngine()

            # ==========================================================
            # 14. Create account-level BacktestEngine
            # ==========================================================

            engine = BacktestEngine(
                market_data=market_data,
                config=resolved_config,
            )

            # ==========================================================
            # 15. Create multi-strategy orchestrator
            # ==============================================================

            orchestrator = BacktestOrchestrator(
                engine=engine,
                strategy_manager=strategy_manager,
                risk_engine=risk_engine,
                risk_configuration=risk_configuration,
                strategy_ids=tuple(
                    created_strategy_ids,
                ),
            )

            # ==========================================================
            # 16. Attach shared historical market-data view
            # ==============================================================

            orchestrator.set_market_data_view(
                market_data_view,
            )

            logger.info(
                "Backtest composition completed successfully. "
                "account_id=%s strategies=%d strategy_names=%s "
                "symbols=%d timeframes=%s",
                config.account_id,
                len(created_strategy_ids),
                tuple(
                    strategy_config.strategy_name
                    for strategy_config in resolved_strategy_configs
                ),
                len(resolved_symbols),
                resolved_timeframes,
            )

            return orchestrator

        except Exception as exc:
            logger.exception(
                "Backtest composition failed while constructing the "
                "simulation runtime. account_id=%s strategies=%s",
                config.account_id,
                created_strategy_ids,
            )

            # ==========================================================
            # Composition failed after strategy instances were created.
            #
            # StrategyManager has not been started by this composition
            # root, so cleanup must not assume a running manager.
            # ==========================================================

            for strategy_id in reversed(
                created_strategy_ids,
            ):
                try:
                    await strategy_manager.remove(
                        strategy_id,
                        stop=True,
                    )

                except Exception:
                    logger.exception(
                        "Failed to clean up backtest strategy instance "
                        "during composition failure. strategy_id=%s "
                        "account_id=%s",
                        strategy_id,
                        config.account_id,
                    )

            try:
                await strategy_manager.stop()

            except Exception:
                logger.exception(
                    "Failed to stop isolated StrategyManager during "
                    "composition cleanup. account_id=%s",
                    config.account_id,
                )

            raise BacktestCompositionError(
                "Failed to construct the backtest orchestrator "
                f"for account '{config.account_id}': "
                f"{type(exc).__name__}: {exc}",
            ) from exc

    # ==================================================================
    # HISTORICAL DATA PREPARATION
    # ==================================================================

    async def _prepare_historical_data(
        self,
        config: BacktestConfig,
        *,
        resolved_symbols: tuple[str, ...],
        resolved_timeframes: tuple[str, ...],
    ) -> None:
        """
        Prepare historical data before the read-only market-data loader.

        The injected backfill dependency receives the complete resolved
        BacktestConfig. This means it has access to:

            - account_id
            - user_id
            - start
            - end
            - symbols
            - timeframes

        The composition root does not know how historical data is
        retrieved or persisted.

        That responsibility belongs to the application-level historical
        data service.

        If no backfill dependency is configured, this method intentionally
        does nothing. The HistoricalMarketDataLoader then performs its
        normal persisted-data coverage validation.
        """

        if self.historical_data_backfill is None:
            logger.debug(
                "No historical-data backfill dependency configured. "
                "Using persisted historical data only. "
                "account_id=%s symbols=%s timeframes=%s",
                config.account_id,
                resolved_symbols,
                resolved_timeframes,
            )
            return

        if config.start is None or config.end is None:
            raise BacktestCompositionError(
                "Historical backfill requires concrete backtest "
                "start and end timestamps.",
            )

        try:
            result = await self._resolve(
                self.historical_data_backfill,
                config,
            )

        except Exception as exc:
            logger.exception(
                "Historical data preparation failed. "
                "account_id=%s symbols=%s timeframes=%s "
                "start=%s end=%s",
                config.account_id,
                resolved_symbols,
                resolved_timeframes,
                config.start,
                config.end,
            )

            raise BacktestCompositionError(
                "Failed to prepare historical market data "
                f"for account '{config.account_id}': "
                f"{type(exc).__name__}: {exc}",
            ) from exc

        logger.info(
            "Historical data preparation completed. "
            "account_id=%s symbols=%d timeframes=%d "
            "start=%s end=%s result=%s",
            config.account_id,
            len(resolved_symbols),
            len(resolved_timeframes),
            config.start,
            config.end,
            self._summarize_backfill_result(result),
        )

    @staticmethod
    def _summarize_backfill_result(
        result: Any,
    ) -> str:
        """
        Produce a compact log-safe representation of a backfill result.

        The composition layer deliberately does not depend on a concrete
        historical-service result type. This allows the application
        service to evolve independently.
        """

        if result is None:
            return "none"

        if isinstance(result, dict):
            return f"mapping(keys={len(result)})"

        if isinstance(
            result,
            (list, tuple, set, frozenset),
        ):
            return f"collection(items={len(result)})"

        return type(result).__name__

    # ==================================================================
    # STRATEGY CONFIGURATION
    # ==================================================================

    @staticmethod
    def _normalize_strategy_configs(
        values: Iterable[StrategyConfig],
        account_config: BacktestConfig,
    ) -> tuple[StrategyConfig, ...]:
        """
        Validate and normalize strategy configurations.

        The injected factory is responsible for returning only enabled
        strategies applicable to the requested account.

        Every resulting configuration is forced into BACKTEST mode and
        assigned to the simulated account.

        StrategyConfig is reconstructed explicitly rather than using
        Pydantic's model_copy() API. This keeps the composition layer
        independent of that copy helper while preserving the complete
        strategy configuration.
        """

        if values is None:
            return ()

        configs: list[StrategyConfig] = []
        strategy_ids: set[str] = set()

        for value in values:
            if not isinstance(
                value,
                StrategyConfig,
            ):
                raise TypeError(
                    "strategy_config_factory must return an iterable "
                    "of StrategyConfig objects.",
                )

            strategy_id = value.strategy_id.strip()

            if not strategy_id:
                raise BacktestCompositionError(
                    "Strategy configuration contains an empty "
                    "strategy_id.",
                )

            if strategy_id in strategy_ids:
                raise BacktestCompositionError(
                    "Duplicate strategy_id detected in backtest: "
                    f"{strategy_id!r}.",
                )

            strategy_ids.add(strategy_id)

            strategy_name = value.strategy_name.strip()

            if not strategy_name:
                raise BacktestCompositionError(
                    f"Strategy {strategy_id!r} contains an empty "
                    "strategy_name.",
                )

            normalized = StrategyConfig(
                strategy_id=strategy_id,
                strategy_name=strategy_name,
                mode=StrategyMode.BACKTEST,
                enabled=True,
                account_id=account_config.account_id,
                symbols=list(value.symbols),
                timeframes=list(value.timeframes),
                parameters=dict(value.parameters),
                metadata=dict(value.metadata),
            )

            configs.append(
                normalized,
            )

        return tuple(
            configs,
        )

    @staticmethod
    def _prepare_strategy_config(
        *,
        strategy_config: StrategyConfig,
        account_config: BacktestConfig,
        symbols: tuple[str, ...],
    ) -> StrategyConfig:
        """
        Prepare one strategy for the account-level backtest.

        Every active strategy receives the full account trading universe.

        Preserved from the persisted strategy configuration:

            - strategy_id
            - strategy_name
            - timeframes
            - parameters
            - metadata
        """

        return StrategyConfig(
            strategy_id=strategy_config.strategy_id,
            strategy_name=strategy_config.strategy_name,
            mode=StrategyMode.BACKTEST,
            enabled=True,
            account_id=account_config.account_id,
            symbols=list(symbols),
            timeframes=list(strategy_config.timeframes),
            parameters=dict(strategy_config.parameters),
            metadata=dict(strategy_config.metadata),
        )

    # ==================================================================
    # SYMBOL RESOLUTION
    # ==================================================================

    @classmethod
    def _normalize_symbol_specifications(
        cls,
        values: Iterable[SelectedSymbol],
        *,
        existing_contract_sizes: dict[str, Decimal] | None,
    ) -> tuple[tuple[str, ...], dict[str, Decimal]]:
        """
        Normalize account-selected symbols and their simulation metadata.

        Accepted inputs are:

            "XAUUSD.s"

        or:

            BacktestSymbolSpecification(
                symbol="XAUUSD.s",
                contract_size=Decimal("100"),
            )

        Existing BacktestConfig contract sizes remain valid and are
        overridden by account-specific symbol specifications.

        Rules:
            - symbols must be strings or BacktestSymbolSpecification
            - surrounding whitespace is removed
            - symbols are uppercased
            - empty symbols are ignored
            - duplicates are rejected when conflicting specifications
              are supplied
            - first-seen symbol order is preserved
            - contract sizes must be finite and positive
        """

        contract_sizes = cls._normalize_contract_sizes(
            existing_contract_sizes,
        )

        if values is None:
            return (
                (),
                contract_sizes,
            )

        symbols: list[str] = []
        seen: set[str] = set()

        for value in values:
            if isinstance(
                value,
                BacktestSymbolSpecification,
            ):
                raw_symbol = value.symbol
                contract_size = value.contract_size

            elif isinstance(
                value,
                str,
            ):
                raw_symbol = value
                contract_size = None

            else:
                raise TypeError(
                    "Selected symbols must contain strings or "
                    "BacktestSymbolSpecification objects.",
                )

            if not isinstance(
                raw_symbol,
                str,
            ):
                raise TypeError(
                    "Selected symbol values must be strings.",
                )

            symbol = raw_symbol.strip().upper()

            if not symbol:
                continue

            if symbol in seen:
                if contract_size is None:
                    continue

                normalized_contract_size = cls._validate_contract_size(
                    symbol,
                    contract_size,
                )

                existing = contract_sizes.get(symbol)

                if (
                    existing is not None
                    and existing != normalized_contract_size
                ):
                    raise BacktestCompositionError(
                        "Conflicting contract_size specifications for "
                        f"symbol {symbol!r}: "
                        f"{existing} vs {normalized_contract_size}.",
                    )

                contract_sizes[symbol] = normalized_contract_size
                continue

            seen.add(symbol)
            symbols.append(symbol)

            if contract_size is not None:
                contract_sizes[symbol] = cls._validate_contract_size(
                    symbol,
                    contract_size,
                )

        return (
            tuple(symbols),
            contract_sizes,
        )

    @staticmethod
    def _normalize_symbols(
        values: Iterable[str],
    ) -> tuple[str, ...]:
        """
        Normalize a plain iterable of account symbols.

        This helper remains for compatibility with callers that already
        resolve symbols separately from symbol metadata.
        """

        if values is None:
            return ()

        symbols: list[str] = []
        seen: set[str] = set()

        for value in values:
            if not isinstance(
                value,
                str,
            ):
                raise TypeError(
                    "Selected symbols must be strings.",
                )

            symbol = value.strip().upper()

            if not symbol:
                continue

            if symbol in seen:
                continue

            seen.add(symbol)
            symbols.append(symbol)

        return tuple(symbols)

    @classmethod
    def _normalize_contract_sizes(
        cls,
        values: dict[str, Decimal] | None,
    ) -> dict[str, Decimal]:
        """
        Normalize an existing contract-size mapping.

        This also protects BacktestConfig reconstruction from mixed-case
        symbol keys.
        """

        if not values:
            return {}

        normalized: dict[str, Decimal] = {}

        for raw_symbol, raw_contract_size in values.items():
            if not isinstance(
                raw_symbol,
                str,
            ):
                raise TypeError(
                    "Contract-size mapping keys must be strings.",
                )

            symbol = raw_symbol.strip().upper()

            if not symbol:
                continue

            normalized[symbol] = cls._validate_contract_size(
                symbol,
                raw_contract_size,
            )

        return normalized

    @staticmethod
    def _validate_contract_size(
        symbol: str,
        value: Decimal,
    ) -> Decimal:
        """
        Validate and normalize one contract size.
        """

        try:
            contract_size = Decimal(
                str(value),
            )

        except Exception as exc:
            raise BacktestCompositionError(
                f"Invalid contract_size for symbol {symbol!r}: "
                f"{value!r}.",
            ) from exc

        if not contract_size.is_finite():
            raise BacktestCompositionError(
                f"contract_size for symbol {symbol!r} "
                "must be finite.",
            )

        if contract_size <= 0:
            raise BacktestCompositionError(
                f"contract_size for symbol {symbol!r} "
                "must be positive.",
            )

        return contract_size

    # ==================================================================
    # TIMEFRAME RESOLUTION
    # ==================================================================

    @staticmethod
    def _collect_timeframes(
        strategy_configs: Iterable[StrategyConfig],
    ) -> tuple[str, ...]:
        """
        Build the union of all strategy timeframes.

        Example:

            Strategy A -> M15, H1
            Strategy B -> M15
            Strategy C -> H4

            Result -> M15, H1, H4
        """

        timeframes: list[str] = []
        seen: set[str] = set()

        for strategy_config in strategy_configs:
            for value in strategy_config.timeframes:
                timeframe = str(value).strip().upper()

                if not timeframe:
                    continue

                if timeframe in seen:
                    continue

                seen.add(timeframe)
                timeframes.append(timeframe)

        return tuple(timeframes)

    # ==================================================================
    # GENERIC DEPENDENCY RESOLUTION
    # ==================================================================

    @staticmethod
    async def _resolve(
        factory: Callable[..., object],
        *args: object,
    ) -> Any:
        """
        Resolve a synchronous or asynchronous composition dependency.
        """

        if not callable(factory):
            raise TypeError(
                "Backtest composition dependency must be callable.",
            )

        value = factory(
            *args,
        )

        if inspect.isawaitable(value):
            value = await value

        return value

    # ==================================================================
    # FACTORY
    # ==================================================================

    def create_factory(
        self,
    ) -> BacktestFactory:
        """
        Create the BacktestFactory used by BacktestService.
        """

        async def build(
            config: BacktestConfig,
        ) -> BacktestOrchestrator:
            return await self.build(
                config,
            )

        return BacktestFactory(
            orchestrator_builder=build,
        )


__all__ = [
    "BacktestComposition",
    "BacktestCompositionError",
    "BacktestMarketDataLoader",
    "BacktestSymbolSpecification",
    "HistoricalDataBackfill",
    "RiskConfigFactory",
    "SelectedSymbol",
    "SelectedSymbolsFactory",
    "StrategyConfigFactory",
]