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
from .engine import BacktestSymbolSpecification
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


AccountLeverageFactory = Callable[
    [BacktestConfig],
    Decimal | Awaitable[Decimal],
]


StrategyConfigFactory = Callable[
    [BacktestConfig],
    Iterable[StrategyConfig] | Awaitable[Iterable[StrategyConfig]],
]


# ======================================================================
# SYMBOL SPECIFICATION
# ======================================================================


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
              +------> account leverage
              |
              v
       account symbol specs
              |
              v
       resolved symbol universe
              |
              v
       strategy configs
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
          +---+--------------------+
          |                        |
          v                        v
     RiskEngine             StrategyManager
                                   |
                         +---------+---------+
                         |         |         |
                         v         v         v
                      strategy  strategy  strategy
                         A         B         C
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

    Account leverage is injected through ``account_leverage_factory``.
    The application-level dependency behind that factory is responsible
    for resolving the authenticated TradingAccount and reading its
    broker-derived leverage.

    Runtime lifecycle ownership belongs to BacktestOrchestrator.
    """

    market_data_loader: BacktestMarketDataLoader

    risk_config_factory: RiskConfigFactory

    account_leverage_factory: AccountLeverageFactory

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
        period. Account leverage and account symbols are resolved before
        strategy configuration because both are account-level runtime
        dependencies.

        The dependency order is therefore:

            1. Resolve account leverage.
            2. Resolve account symbols.
            3. Inject leverage/symbols/metadata into an intermediate config.
            4. Resolve enabled strategies against that config.
            5. Preserve each strategy's own StrategyRun symbol universe.
            6. Resolve the union of strategy timeframes.
            7. Construct the final BacktestConfig.
            8. Prepare/load historical market data.
            9. Construct the isolated runtime graph.

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
        # The current engine exposes ``leverage`` explicitly. Keeping the
        # field check makes the composition boundary fail clearly if the
        # domain configuration is accidentally out of sync.
        config_field_names = {field_info.name for field_info in fields(config)}

        if "leverage" not in config_field_names:
            raise BacktestCompositionError(
                "BacktestConfig does not expose the required " "'leverage' field.",
            )

        existing_contract_sizes = getattr(
            config,
            "contract_sizes",
            {},
        )

        existing_symbol_specifications = getattr(
            config,
            "symbol_specifications",
            {},
        )

        # ==============================================================
        # 1. Resolve account leverage
        # ==============================================================

        #
        # Leverage is an account property and must come from the
        # authenticated TradingAccount rather than from public client
        # input.
        #
        # The application-level factory is responsible for:
        #
        #     account_id + authenticated user
        #                  |
        #                  v
        #          TradingAccount.leverage
        #
        # This value becomes part of the internal BacktestConfig.
        #

        try:
            resolved_leverage = await self._resolve(
                self.account_leverage_factory,
                config,
            )

            resolved_leverage = self._normalize_leverage(
                resolved_leverage,
            )

        except Exception as exc:
            logger.exception(
                "Backtest composition failed while resolving account "
                "leverage. account_id=%s",
                config.account_id,
            )

            raise BacktestCompositionError(
                "Failed to resolve account leverage "
                f"for account '{config.account_id}': "
                f"{type(exc).__name__}: {exc}",
            ) from exc

        # ==============================================================
        # 2. Resolve account trading universe and symbol metadata
        # ==============================================================

        #
        # IMPORTANT:
        #
        # This MUST happen before strategy configuration resolution.
        #
        # StrategyConfig validates that at least one symbol exists.
        # The original incoming BacktestConfig may have an empty
        # ``symbols`` field because symbols are selected from the
        # account's enabled AccountSymbol records.
        #
        # Therefore the selected-symbol dependency is the first
        # account-specific dependency in the composition graph after
        # leverage has been resolved.
        #

        try:
            selected_symbols = await self._resolve(
                self.selected_symbols_factory,
                config,
            )

            (
                resolved_symbols,
                resolved_contract_sizes,
                resolved_symbol_specifications,
            ) = self._normalize_symbol_specifications(
                selected_symbols,
                existing_contract_sizes=existing_contract_sizes,
                existing_symbol_specifications=(existing_symbol_specifications),
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
        # 3. Build an intermediate symbol/leverage-aware configuration
        # ==============================================================

        #
        # StrategyConfigFactory receives this configuration.
        #
        # Strategy configuration now sees:
        #
        #     config.account_id
        #     config.leverage
        #     config.symbols
        #     config.contract_sizes
        #     config.symbol_specifications
        #
        # The public request remains account-centric. These values are
        # resolved internally by the composition layer.
        #

        try:
            strategy_config_input = self._build_symbol_resolved_config(
                config=config,
                resolved_leverage=resolved_leverage,
                resolved_symbols=resolved_symbols,
                resolved_contract_sizes=resolved_contract_sizes,
                resolved_symbol_specifications=(resolved_symbol_specifications),
                config_field_names=config_field_names,
            )

        except Exception as exc:
            logger.exception(
                "Backtest composition failed while constructing the "
                "symbol/leverage-resolved strategy configuration input. "
                "account_id=%s symbols=%s leverage=%s",
                config.account_id,
                resolved_symbols,
                resolved_leverage,
            )

            raise BacktestCompositionError(
                "Failed to construct the symbol/leverage-resolved "
                f"backtest configuration for account "
                f"'{config.account_id}': "
                f"{type(exc).__name__}: {exc}",
            ) from exc

        # ==============================================================
        # 4. Resolve enabled strategies
        # ==============================================================

        try:
            strategy_configs = await self._resolve(
                self.strategy_config_factory,
                strategy_config_input,
            )

            resolved_strategy_configs = self._normalize_strategy_configs(
                strategy_configs,
                strategy_config_input,
            )

        except Exception as exc:
            logger.exception(
                "Backtest composition failed while resolving strategy "
                "configurations. account_id=%s symbols=%s leverage=%s",
                config.account_id,
                resolved_symbols,
                resolved_leverage,
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
        # 5. Preserve strategy-local symbol universes
        # ==============================================================

        #
        # IMPORTANT:
        #
        # ``resolved_symbols`` is the ACCOUNT/BACKTEST MARKET-DATA
        # universe.
        #
        # It is NOT a strategy universe.
        #
        # Each StrategyConfig already contains the symbol universe
        # belonging to its individual StrategyRun.
        #
        # Example:
        #
        #     BacktestConfig.symbols
        #         = [BTCUSD, US100, US30, XAUAUD, XAUUSD]
        #
        #     bollinger_reversion.symbols
        #         = [US30]
        #
        # Historical market data is loaded for the complete account
        # universe, but StrategyManager receives each strategy's own
        # symbol configuration unchanged.
        #
        # _normalize_strategy_configs() already:
        #
        #     - forces BACKTEST mode
        #     - enables the runtime strategy
        #     - assigns account_id
        #     - preserves symbols
        #     - preserves timeframes
        #     - preserves parameters
        #     - preserves metadata
        #
        # Therefore there is deliberately NO second StrategyConfig
        # transformation here.
        #

        logger.debug(
            "Resolved strategy universes for backtest. " "account_id=%s strategies=%s",
            config.account_id,
            tuple(
                (
                    strategy_config.strategy_name,
                    tuple(strategy_config.symbols),
                    tuple(strategy_config.timeframes),
                )
                for strategy_config in resolved_strategy_configs
            ),
        )

        # ==============================================================
        # 6. Resolve union of strategy timeframes
        # ==============================================================

        resolved_timeframes = self._collect_timeframes(
            resolved_strategy_configs,
        )

        if not resolved_timeframes:
            raise BacktestCompositionError(
                "Active strategies do not define any required timeframes.",
            )

        # ==============================================================
        # 7. Build final resolved account-level BacktestConfig
        # ==============================================================

        try:
            resolved_config = self._build_config(
                config=strategy_config_input,
                resolved_leverage=resolved_leverage,
                resolved_symbols=resolved_symbols,
                resolved_timeframes=resolved_timeframes,
                resolved_contract_sizes=resolved_contract_sizes,
                resolved_symbol_specifications=(resolved_symbol_specifications),
                config_field_names=config_field_names,
            )

        except Exception as exc:
            logger.exception(
                "Backtest composition failed while constructing the "
                "resolved BacktestConfig. account_id=%s leverage=%s",
                config.account_id,
                resolved_leverage,
            )

            raise BacktestCompositionError(
                "Failed to construct the resolved BacktestConfig "
                f"for account '{config.account_id}': "
                f"{type(exc).__name__}: {exc}",
            ) from exc

        # ==============================================================
        # 8. Ensure historical market data is available
        # ==============================================================

        await self._prepare_historical_data(
            resolved_config,
            resolved_symbols=resolved_symbols,
            resolved_timeframes=resolved_timeframes,
        )

        # ==============================================================
        # 9. Load persisted historical market data
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
                "market data. account_id=%s symbols=%s timeframes=%s "
                "leverage=%s",
                config.account_id,
                resolved_symbols,
                resolved_timeframes,
                resolved_leverage,
            )

            raise BacktestCompositionError(
                "Failed to load historical market data "
                f"for account '{config.account_id}': "
                f"{type(exc).__name__}: {exc}",
            ) from exc

        # ==============================================================
        # 10. Create isolated StrategyManager
        #
        # StrategyManager is constructed here but NOT started here.
        #
        # BacktestOrchestrator.run() owns the runtime lifecycle.
        # ==============================================================

        strategy_manager = StrategyManager()

        # ==============================================================
        # 11. Create simulation-aware market-data view
        # ==============================================================

        market_data_view = BacktestMarketDataView(
            market_data,
            current_time=None,
        )

        created_strategy_ids: list[str] = []

        try:
            # ==========================================================
            # 12. Bootstrap the strategy registry
            # ==========================================================

            bootstrap_result = await strategy_bootstrap.start()

            logger.info(
                "Backtest strategy registry bootstrapped. "
                "account_id=%s leverage=%s imported_modules=%d "
                "registered_strategies=%s",
                config.account_id,
                resolved_leverage,
                len(bootstrap_result.imported_modules),
                bootstrap_result.registered_strategies,
            )

            # ==========================================================
            # 13. Create one runtime instance per active strategy
            # ==============================================================

            for strategy_config in resolved_strategy_configs:
                instance = await strategy_manager.create(
                    strategy_config,
                    market_data=market_data_view,
                    auto_start=False,
                )

                created_strategy_ids.append(
                    instance.strategy_id,
                )

                logger.info(
                    "Backtest strategy instance created. "
                    "strategy_id=%s strategy_name=%s symbols=%s "
                    "timeframes=%s account_id=%s",
                    instance.strategy_id,
                    instance.strategy_name,
                    instance.symbols,
                    instance.timeframes,
                    config.account_id,
                )

            # ==========================================================
            # 14. Resolve RiskConfig
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
            # 15. Create isolated real RiskEngine
            # ==============================================================

            risk_engine = RiskEngine()

            # ==========================================================
            # 16. Create account-level BacktestEngine
            # ==============================================================

            engine = BacktestEngine(
                market_data=market_data,
                config=resolved_config,
            )

            # ==========================================================
            # 17. Create multi-strategy orchestrator
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
            # 18. Attach shared historical market-data view
            # ==============================================================

            orchestrator.set_market_data_view(
                market_data_view,
            )

            logger.info(
                "Backtest composition completed successfully. "
                "account_id=%s leverage=%s strategies=%d "
                "strategy_names=%s symbols=%d timeframes=%s",
                config.account_id,
                resolved_leverage,
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
                "simulation runtime. account_id=%s leverage=%s "
                "strategies=%s",
                config.account_id,
                resolved_leverage,
                created_strategy_ids,
            )

            # Composition failed after strategy instances were created.
            # StrategyManager has not been started by this composition
            # root, so cleanup must not assume a running manager.

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
    # CONFIGURATION BUILDING
    # ==================================================================

    @staticmethod
    def _build_symbol_resolved_config(
        *,
        config: BacktestConfig,
        resolved_leverage: Decimal,
        resolved_symbols: tuple[str, ...],
        resolved_contract_sizes: dict[str, Decimal],
        resolved_symbol_specifications: dict[
            str,
            BacktestSymbolSpecification,
        ],
        config_field_names: set[str],
    ) -> BacktestConfig:
        """
        Build an intermediate BacktestConfig containing the resolved
        account leverage and symbol universe.

        This configuration is passed to StrategyConfigFactory so that
        strategy configurations are created with the actual account
        context.

        Timeframes are intentionally left unchanged here. The final
        account-level timeframe union is calculated after all strategies
        have been resolved.
        """

        values: dict[str, Any] = {
            "leverage": resolved_leverage,
            "symbols": resolved_symbols,
        }

        if "contract_sizes" in config_field_names:
            values["contract_sizes"] = resolved_contract_sizes

        if "symbol_specifications" in config_field_names:
            values["symbol_specifications"] = resolved_symbol_specifications

        return replace(
            config,
            **values,
        )

    @staticmethod
    def _build_config(
        *,
        config: BacktestConfig,
        resolved_leverage: Decimal,
        resolved_symbols: tuple[str, ...],
        resolved_timeframes: tuple[str, ...],
        resolved_contract_sizes: dict[str, Decimal],
        resolved_symbol_specifications: dict[
            str,
            BacktestSymbolSpecification,
        ],
        config_field_names: set[str],
    ) -> BacktestConfig:
        """
        Construct the immutable account-level BacktestConfig.

        This is the final configuration boundary between:

            persisted/request configuration

        and:

            resolved simulation configuration.

        The resulting configuration contains the complete account-level
        trading universe, resolved account leverage, and the union of
        every timeframe required by the active strategies.

        BacktestConfig enforces:

            period

        XOR

            start + end

        Therefore a relative period that has already been resolved into
        concrete timestamps must clear ``period`` before reconstruction.
        """

        resolved_config_values: dict[str, Any] = {
            "period": None,
            "start": config.start,
            "end": config.end,
            "symbols": resolved_symbols,
            "timeframes": resolved_timeframes,
            "leverage": resolved_leverage,
        }

        if "contract_sizes" in config_field_names:
            resolved_config_values["contract_sizes"] = resolved_contract_sizes

        if "symbol_specifications" in config_field_names:
            resolved_config_values["symbol_specifications"] = (
                resolved_symbol_specifications
            )

        return replace(
            config,
            **resolved_config_values,
        )

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
            - leverage
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
                "account_id=%s symbols=%s timeframes=%s leverage=%s",
                config.account_id,
                resolved_symbols,
                resolved_timeframes,
                config.leverage,
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
                "start=%s end=%s leverage=%s",
                config.account_id,
                resolved_symbols,
                resolved_timeframes,
                config.start,
                config.end,
                config.leverage,
            )

            raise BacktestCompositionError(
                "Failed to prepare historical market data "
                f"for account '{config.account_id}': "
                f"{type(exc).__name__}: {exc}",
            ) from exc

        logger.info(
            "Historical data preparation completed. "
            "account_id=%s symbols=%d timeframes=%d "
            "start=%s end=%s leverage=%s result=%s",
            config.account_id,
            len(resolved_symbols),
            len(resolved_timeframes),
            config.start,
            config.end,
            config.leverage,
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

        Each strategy's own symbols and timeframes are preserved exactly
        as supplied by the strategy configuration factory.

        StrategyConfig is reconstructed explicitly rather than using
        Pydantic's model_copy() API because the runtime StrategyConfig
        contract does not rely on that helper.
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
                    "Strategy configuration contains an empty " "strategy_id.",
                )

            if strategy_id in strategy_ids:
                raise BacktestCompositionError(
                    "Duplicate strategy_id detected in backtest: " f"{strategy_id!r}.",
                )

            strategy_ids.add(
                strategy_id,
            )

            strategy_name = value.strategy_name.strip()

            if not strategy_name:
                raise BacktestCompositionError(
                    f"Strategy {strategy_id!r} contains an empty " "strategy_name.",
                )

            symbols = [
                symbol.strip()
                for symbol in value.symbols
                if isinstance(symbol, str) and symbol.strip()
            ]

            if not symbols:
                raise BacktestCompositionError(
                    f"Strategy {strategy_id!r} must define at least " "one symbol.",
                )

            timeframes = [
                timeframe.strip().upper()
                for timeframe in value.timeframes
                if isinstance(timeframe, str) and timeframe.strip()
            ]

            if not timeframes:
                raise BacktestCompositionError(
                    f"Strategy {strategy_id!r} must define at least " "one timeframe.",
                )

            normalized = StrategyConfig(
                strategy_id=strategy_id,
                strategy_name=strategy_name,
                mode=StrategyMode.BACKTEST,
                enabled=True,
                account_id=account_config.account_id,
                symbols=symbols,
                timeframes=timeframes,
                parameters=dict(value.parameters),
                metadata=dict(value.metadata),
            )

            configs.append(
                normalized,
            )

        return tuple(
            configs,
        )

    # ==================================================================
    # ACCOUNT LEVERAGE
    # ==================================================================

    @staticmethod
    def _normalize_leverage(
        value: Decimal,
    ) -> Decimal:
        """
        Validate and normalize the account leverage used by simulation.

        Leverage is an account-level value and must be strictly positive.

        Examples:

            100   -> Decimal("100")
            50    -> Decimal("50")
            30    -> Decimal("30")

        The resulting value is later consumed by the orchestration layer
        to derive the margin rate:

            margin_rate = 1 / leverage
        """

        if value is None:
            raise BacktestCompositionError(
                "Account leverage is required for backtesting.",
            )

        try:
            leverage = Decimal(
                str(value),
            )

        except Exception as exc:
            raise BacktestCompositionError(
                f"Invalid account leverage value: {value!r}.",
            ) from exc

        if not leverage.is_finite():
            raise BacktestCompositionError(
                "Account leverage must be finite.",
            )

        if leverage <= Decimal("0"):
            raise BacktestCompositionError(
                "Account leverage must be greater than zero.",
            )

        return leverage

    # ==================================================================
    # SYMBOL RESOLUTION
    # ==================================================================

    @classmethod
    def _normalize_symbol_specifications(
        cls,
        values: Iterable[SelectedSymbol],
        *,
        existing_contract_sizes: dict[str, Decimal] | None,
        existing_symbol_specifications: (
            dict[
                str,
                BacktestSymbolSpecification,
            ]
            | None
        ),
    ) -> tuple[
        tuple[str, ...],
        dict[str, Decimal],
        dict[str, BacktestSymbolSpecification],
    ]:
        """
        Normalize account-selected symbols and their simulation metadata.

        Accepted inputs are:

            "XAUUSD"

        or:

            BacktestSymbolSpecification(
                symbol="XAUUSD",
                broker_symbol="XAUUSD.s",
                digits=2,
                point=Decimal("0.01"),
                contract_size=Decimal("100"),
                tick_size=Decimal("0.01"),
                min_volume=Decimal("0.01"),
                max_volume=Decimal("100"),
                volume_step=Decimal("0.01"),
            )

        Existing BacktestConfig contract sizes remain valid and are
        overridden by account-specific symbol specifications.

        Existing complete symbol specifications are also preserved and
        overridden by newly resolved account-specific specifications.

        Rules:

            - symbols must be strings or BacktestSymbolSpecification
            - surrounding whitespace is removed
            - symbols are uppercased
            - empty symbols are ignored
            - duplicate specifications must not conflict
            - first-seen symbol order is preserved
            - numeric metadata must be finite and positive when supplied
            - volume_min/max/step must be positive when supplied
            - max volume cannot be lower than min volume
        """

        contract_sizes = cls._normalize_contract_sizes(
            existing_contract_sizes,
        )

        symbol_specifications = cls._normalize_symbol_specifications_mapping(
            existing_symbol_specifications,
        )

        if values is None:
            return (
                (),
                contract_sizes,
                symbol_specifications,
            )

        symbols: list[str] = []
        seen: set[str] = set()

        for value in values:
            if isinstance(
                value,
                BacktestSymbolSpecification,
            ):
                raw_symbol = value.symbol

                normalized_specification = cls._build_normalized_symbol_specification(
                    symbol=raw_symbol,
                    broker_symbol=value.broker_symbol,
                    digits=value.digits,
                    point=value.point,
                    tick_size=value.tick_size,
                    contract_size=value.contract_size,
                    volume_min=value.min_volume,
                    volume_max=value.max_volume,
                    volume_step=value.volume_step,
                )

            elif isinstance(
                value,
                str,
            ):
                raw_symbol = value
                normalized_specification = None

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

            if normalized_specification is not None:
                normalized_specification = replace(
                    normalized_specification,
                    symbol=symbol,
                )

            if symbol in seen:
                existing_specification = symbol_specifications.get(
                    symbol,
                )

                if normalized_specification is not None:
                    if (
                        existing_specification is not None
                        and existing_specification != normalized_specification
                    ):
                        raise BacktestCompositionError(
                            "Conflicting symbol specifications for "
                            f"{symbol!r}: "
                            f"{existing_specification!r} vs "
                            f"{normalized_specification!r}.",
                        )

                    symbol_specifications[symbol] = normalized_specification

                    if normalized_specification.contract_size is not None:
                        contract_sizes[symbol] = normalized_specification.contract_size

                continue

            seen.add(symbol)
            symbols.append(symbol)

            if normalized_specification is not None:
                symbol_specifications[symbol] = normalized_specification

                if normalized_specification.contract_size is not None:
                    contract_sizes[symbol] = normalized_specification.contract_size

        return (
            tuple(symbols),
            contract_sizes,
            symbol_specifications,
        )

    @classmethod
    def _normalize_symbol_specifications_mapping(
        cls,
        values: (
            dict[
                str,
                BacktestSymbolSpecification,
            ]
            | None
        ),
    ) -> dict[str, BacktestSymbolSpecification]:
        """
        Normalize an existing symbol-specification mapping.

        All metadata is deliberately preserved:

            - broker_symbol
            - digits
            - point
            - tick_size
            - contract_size
            - min_volume
            - max_volume
            - volume_step
        """

        if not values:
            return {}

        normalized: dict[
            str,
            BacktestSymbolSpecification,
        ] = {}

        for raw_symbol, specification in values.items():
            if not isinstance(
                raw_symbol,
                str,
            ):
                raise TypeError(
                    "Symbol-specification mapping keys must be strings.",
                )

            if not isinstance(
                specification,
                BacktestSymbolSpecification,
            ):
                raise TypeError(
                    "Symbol-specification mapping values must be "
                    "BacktestSymbolSpecification objects.",
                )

            symbol = raw_symbol.strip().upper()

            if not symbol:
                continue

            normalized_specification = cls._build_normalized_symbol_specification(
                symbol=symbol,
                broker_symbol=specification.broker_symbol,
                digits=specification.digits,
                point=specification.point,
                tick_size=specification.tick_size,
                contract_size=specification.contract_size,
                volume_min=specification.min_volume,
                volume_max=specification.max_volume,
                volume_step=specification.volume_step,
            )

            if normalized_specification is None:
                raise BacktestCompositionError(
                    f"Symbol specification for {symbol!r} "
                    "contains no usable metadata.",
                )

            normalized[symbol] = normalized_specification

        return normalized

    @classmethod
    def _build_normalized_symbol_specification(
        cls,
        *,
        symbol: str,
        broker_symbol: str | None,
        digits: int | None,
        point: Decimal | None,
        tick_size: Decimal | None,
        contract_size: Decimal | None,
        volume_min: Decimal | None,
        volume_max: Decimal | None,
        volume_step: Decimal | None,
    ) -> BacktestSymbolSpecification | None:
        """
        Validate and normalize one complete symbol specification.

        This is the important metadata-preservation boundary between the
        application account-symbol model and the backtesting domain.

        A specification containing no metadata is represented by ``None``.
        This allows a plain string symbol to remain backwards compatible.
        """

        if (
            broker_symbol is None
            and digits is None
            and point is None
            and tick_size is None
            and contract_size is None
            and volume_min is None
            and volume_max is None
            and volume_step is None
        ):
            return None

        normalized_broker_symbol: str | None = None

        if broker_symbol is not None:
            if not isinstance(
                broker_symbol,
                str,
            ):
                raise BacktestCompositionError(
                    f"broker_symbol for symbol {symbol!r} " "must be a string.",
                )

            normalized_broker_symbol = broker_symbol.strip()

            if not normalized_broker_symbol:
                raise BacktestCompositionError(
                    f"broker_symbol for symbol {symbol!r} "
                    "cannot be empty when supplied.",
                )

        normalized_digits: int | None = None

        if digits is not None:
            try:
                normalized_digits = int(digits)

            except (TypeError, ValueError) as exc:
                raise BacktestCompositionError(
                    f"Invalid digits for symbol {symbol!r}: " f"{digits!r}.",
                ) from exc

            if normalized_digits < 0:
                raise BacktestCompositionError(
                    f"digits for symbol {symbol!r} "
                    "must be greater than or equal to zero.",
                )

        normalized_point = (
            cls._validate_positive_decimal(
                symbol=symbol,
                field_name="point",
                value=point,
            )
            if point is not None
            else None
        )

        normalized_tick_size = (
            cls._validate_positive_decimal(
                symbol=symbol,
                field_name="tick_size",
                value=tick_size,
            )
            if tick_size is not None
            else None
        )

        normalized_contract_size = (
            cls._validate_positive_decimal(
                symbol=symbol,
                field_name="contract_size",
                value=contract_size,
            )
            if contract_size is not None
            else None
        )

        normalized_volume_min = (
            cls._validate_positive_decimal(
                symbol=symbol,
                field_name="volume_min",
                value=volume_min,
            )
            if volume_min is not None
            else None
        )

        normalized_volume_max = (
            cls._validate_positive_decimal(
                symbol=symbol,
                field_name="volume_max",
                value=volume_max,
            )
            if volume_max is not None
            else None
        )

        normalized_volume_step = (
            cls._validate_positive_decimal(
                symbol=symbol,
                field_name="volume_step",
                value=volume_step,
            )
            if volume_step is not None
            else None
        )

        if (
            normalized_volume_min is not None
            and normalized_volume_max is not None
            and normalized_volume_max < normalized_volume_min
        ):
            raise BacktestCompositionError(
                f"volume_max for symbol {symbol!r} "
                f"({normalized_volume_max}) cannot be lower than "
                f"volume_min ({normalized_volume_min}).",
            )

        return BacktestSymbolSpecification(
            symbol=symbol,
            broker_symbol=normalized_broker_symbol,
            digits=normalized_digits,
            point=normalized_point,
            tick_size=normalized_tick_size,
            contract_size=normalized_contract_size,
            min_volume=normalized_volume_min,
            max_volume=normalized_volume_max,
            volume_step=normalized_volume_step,
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
                f"Invalid contract_size for symbol {symbol!r}: " f"{value!r}.",
            ) from exc

        if not contract_size.is_finite():
            raise BacktestCompositionError(
                f"contract_size for symbol {symbol!r} " "must be finite.",
            )

        if contract_size <= 0:
            raise BacktestCompositionError(
                f"contract_size for symbol {symbol!r} " "must be positive.",
            )

        return contract_size

    @staticmethod
    def _validate_positive_decimal(
        *,
        symbol: str,
        field_name: str,
        value: Decimal,
    ) -> Decimal:
        """
        Validate and normalize a positive decimal symbol constraint.
        """

        try:
            normalized = Decimal(
                str(value),
            )

        except Exception as exc:
            raise BacktestCompositionError(
                f"Invalid {field_name} for symbol {symbol!r}: " f"{value!r}.",
            ) from exc

        if not normalized.is_finite():
            raise BacktestCompositionError(
                f"{field_name} for symbol {symbol!r} " "must be finite.",
            )

        if normalized <= 0:
            raise BacktestCompositionError(
                f"{field_name} for symbol {symbol!r} " "must be positive.",
            )

        return normalized

    # ==================================================================
    # TIMEFRAME RESOLUTION
    # ==================================================================

    @staticmethod
    def _collect_timeframes(
        strategy_configs: Iterable[StrategyConfig],
    ) -> tuple[str, ...]:
        """
        Build the ordered union of all strategy timeframes.

        Example:

            Strategy A -> M15, H1
            Strategy B -> M15
            Strategy C -> H4

            Result -> M15, H1, H4

        Timeframe values must be strings. Empty strings are ignored.
        Surrounding whitespace is removed and values are normalized to
        uppercase.

        Invalid non-string timeframe values raise
        BacktestCompositionError rather than being silently converted
        into strings.
        """

        timeframes: list[str] = []
        seen: set[str] = set()

        for strategy_config in strategy_configs:
            for value in strategy_config.timeframes:
                if not isinstance(
                    value,
                    str,
                ):
                    raise BacktestCompositionError(
                        "Strategy timeframe values must be strings. "
                        f"strategy_id={strategy_config.strategy_id!r}, "
                        f"value={value!r}.",
                    )

                timeframe = value.strip().upper()

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
    "AccountLeverageFactory",
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
