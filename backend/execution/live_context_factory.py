from __future__ import annotations

from decimal import Decimal
from typing import Awaitable, Callable
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.broker.broker_manager import BrokerManager
from app.database.models.account_symbol import AccountSymbol
from app.database.models.position import Position
from app.database.models.trading_account import TradingAccount
from app.repositories.account_symbol_repository import AccountSymbolRepository
from app.repositories.position_repository import PositionRepository
from app.repositories.trading_account_repository import TradingAccountRepository
from risk.config import RiskConfig
from risk.models import RiskContext
from strategies.core.signal import TradingSignal

from .live_context_provider import (
    LiveAccountState,
    LiveMarketState,
    LivePositionState,
    LiveRiskContextProvider,
    LiveSymbolState,
)


AccountIdResolver = Callable[
    [TradingSignal],
    Awaitable[UUID] | UUID,
]

SessionFactory = async_sessionmaker[AsyncSession]


class LiveContextFactory:
    """
    Construct the concrete live Risk Context provider.

    This is the application wiring layer between AQE persistence,
    the broker abstraction, and the Risk Engine.

    Responsibilities:
        - create database sessions per operation;
        - create repositories using those sessions;
        - resolve trading-account state;
        - resolve AccountSymbol mappings;
        - retrieve live broker symbol metadata;
        - retrieve live broker market prices;
        - convert AQE Position records into Risk Engine state;
        - provide RiskConfig.

    This class does NOT:
        - evaluate risk;
        - calculate position size;
        - execute orders;
        - modify broker positions;
        - publish events.

    Database sessions are intentionally created per provider operation.

    The LiveRiskContextProvider can process multiple signals concurrently,
    so a single AsyncSession must never be shared across those operations.
    """

    def __init__(
        self,
        *,
        session_factory: SessionFactory,
        broker_manager: BrokerManager,
        account_id_resolver: AccountIdResolver,
        risk_config: RiskConfig | None = None,
        risk_config_provider: (
            Callable[
                [UUID, TradingSignal],
                Awaitable[RiskConfig] | RiskConfig,
            ]
            | None
        ) = None,
        margin_rate: Decimal = Decimal("0"),
    ) -> None:
        self._session_factory = session_factory
        self._broker_manager = broker_manager
        self._account_id_resolver = account_id_resolver

        if risk_config is not None and risk_config_provider is not None:
            raise ValueError(
                "Provide either risk_config or risk_config_provider, not both."
            )

        self._risk_config = risk_config or RiskConfig()
        self._risk_config_provider = risk_config_provider

        if margin_rate < Decimal("0"):
            raise ValueError("margin_rate cannot be negative.")

        self._margin_rate = margin_rate

    # ======================================================================
    # PUBLIC FACTORY
    # ======================================================================

    def create(self) -> LiveRiskContextProvider:
        """
        Build the concrete LiveRiskContextProvider.

        The returned provider can be supplied directly to
        SignalRiskExecutionPipeline.
        """

        return LiveRiskContextProvider(
            account_id_resolver=self._resolve_account_id,
            account_provider=self._get_account_state,
            positions_provider=self._get_positions,
            symbol_provider=self._get_symbol_state,
            market_provider=self._get_market_state,
            risk_config_provider=self._get_risk_config,
        )

    # ======================================================================
    # ACCOUNT
    # ======================================================================

    async def _resolve_account_id(
        self,
        signal: TradingSignal,
    ) -> UUID:
        """
        Resolve which trading account owns the signal.

        TradingSignal intentionally does not contain account_id.

        Account routing therefore remains an application/runtime concern,
        rather than becoming part of the strategy signal contract.
        """

        result = self._account_id_resolver(signal)

        account_id = (
            await result
            if hasattr(result, "__await__")
            else result
        )

        if not isinstance(account_id, UUID):
            try:
                account_id = UUID(str(account_id))
            except (TypeError, ValueError) as exc:
                raise ValueError(
                    "Account ID resolver returned an invalid account ID."
                ) from exc

        return account_id

    async def _get_account_state(
        self,
        account_id: UUID,
    ) -> LiveAccountState:
        """
        Load the current AQE account state.

        TradingAccount is the authoritative AQE account-state model used
        by the risk context.

        The account's balance/equity/margin fields are expected to be
        maintained by the broker/account synchronization layer.

        A fresh database session is used for this operation.
        """

        async with self._session_factory() as db:
            repository = TradingAccountRepository(db)

            account: TradingAccount | None = (
                await repository.get_by_id(account_id)
            )

        if account is None:
            raise ValueError(
                f"Trading account {account_id} was not found."
            )

        equity = self._decimal(
            account.equity,
            field="account.equity",
        )

        balance = self._decimal(
            account.balance,
            field="account.balance",
        )

        margin = self._decimal(
            account.margin,
            field="account.margin",
        )

        free_margin = self._decimal(
            account.free_margin,
            field="account.free_margin",
        )

        margin_level = (
            self._decimal(
                account.margin_level,
                field="account.margin_level",
            )
            if account.margin_level is not None
            else None
        )

        return LiveAccountState(
            account_id=account.id,
            balance=balance,
            equity=equity,
            margin=margin,
            free_margin=free_margin,
            margin_level=margin_level,
            daily_pnl=Decimal("0"),
            peak_equity=None,
        )

    # ======================================================================
    # POSITIONS
    # ======================================================================

    async def _get_positions(
        self,
        account_id: UUID,
    ) -> list[LivePositionState]:
        """
        Load open AQE positions for the account.

        Position synchronization remains responsible for keeping these
        records aligned with the broker.

        The Risk Engine receives the normalized AQE representation and
        remains unaware of SQLAlchemy models.

        A fresh database session is used for this operation.
        """

        async with self._session_factory() as db:
            repository = PositionRepository(db)

            positions = (
                await repository.get_open_positions_by_account(
                    account_id
                )
            )

        return [
            self._position_to_live_state(position)
            for position in positions
        ]

    @staticmethod
    def _position_to_live_state(
        position: Position,
    ) -> LivePositionState:
        """
        Convert an AQE Position model into Risk Engine state.
        """

        strategy_id = None

        if position.strategy is not None:
            strategy_id = str(position.strategy)

        return LivePositionState(
            position_id=position.id,
            account_id=position.account_id,
            symbol=LiveContextFactory._position_symbol(position),
            direction=position.direction,
            quantity=LiveContextFactory._decimal(
                position.current_volume,
                field="position.current_volume",
            ),
            entry_price=LiveContextFactory._decimal(
                position.entry_price,
                field="position.entry_price",
            ),
            current_price=LiveContextFactory._decimal(
                position.current_price,
                field="position.current_price",
            ),
            stop_loss=(
                LiveContextFactory._decimal(
                    position.stop_loss,
                    field="position.stop_loss",
                )
                if position.stop_loss is not None
                else None
            ),
            take_profit=(
                LiveContextFactory._decimal(
                    position.take_profit,
                    field="position.take_profit",
                )
                if position.take_profit is not None
                else None
            ),
            unrealized_pnl=LiveContextFactory._decimal(
                position.floating_profit,
                field="position.floating_profit",
            ),
            risk_amount=LiveContextFactory._decimal(
                position.initial_risk,
                field="position.initial_risk",
            ),
            strategy_id=strategy_id,
        )

    @staticmethod
    def _position_symbol(
        position: Position,
    ) -> str:
        """
        Resolve the canonical AQE symbol from the loaded Position.

        PositionRepository loads Position.symbol using selectinload().
        """

        if position.symbol is None:
            raise ValueError(
                f"Position {position.id} has no associated symbol."
            )

        name = getattr(position.symbol, "name", None)

        if not name or not str(name).strip():
            raise ValueError(
                f"Position {position.id} has an invalid symbol."
            )

        return str(name).strip().upper()

    # ======================================================================
    # SYMBOL
    # ======================================================================

    async def _get_symbol_state(
        self,
        account_id: UUID,
        canonical_symbol: str,
    ) -> LiveSymbolState:
        """
        Resolve canonical AQE symbol → account-specific broker symbol.

        Example:

            canonical_symbol = XAUUSD

            AccountSymbol:
                symbol        = XAUUSD
                broker_symbol = XAUUSD.s

        Broker metadata is then retrieved using XAUUSD.s.
        """

        normalized_symbol = canonical_symbol.strip().upper()

        async with self._session_factory() as db:
            repository = AccountSymbolRepository(db)

            account_symbol = await self._find_account_symbol(
                repository=repository,
                account_id=account_id,
                canonical_symbol=normalized_symbol,
            )

        if account_symbol is None:
            raise ValueError(
                f"Symbol {normalized_symbol!r} is not configured "
                f"for trading account {account_id}."
            )

        if not account_symbol.broker_symbol:
            raise ValueError(
                f"Account symbol for {normalized_symbol!r} "
                "does not have a broker symbol."
            )

        broker_symbol = account_symbol.broker_symbol.strip()

        if not broker_symbol:
            raise ValueError(
                f"Account symbol for {normalized_symbol!r} "
                "has an empty broker symbol."
            )

        data = await self._broker_manager.get_symbol(broker_symbol)

        if not isinstance(data, dict):
            raise ValueError(
                f"Broker returned invalid symbol metadata for "
                f"{broker_symbol!r}."
            )

        return LiveSymbolState(
            symbol=broker_symbol,
            contract_size=self._symbol_decimal(
                data,
                "trade_contract_size",
                fallback=account_symbol.contract_size,
                required=True,
                symbol=broker_symbol,
            ),
            tick_size=self._symbol_decimal(
                data,
                "trade_tick_size",
                fallback=account_symbol.tick_size,
                required=True,
                symbol=broker_symbol,
            ),
            tick_value=self._symbol_decimal(
                data,
                "trade_tick_value",
                required=True,
                symbol=broker_symbol,
            ),
            volume_min=self._symbol_decimal(
                data,
                "volume_min",
                fallback=account_symbol.min_volume,
                required=True,
                symbol=broker_symbol,
            ),
            volume_max=self._symbol_decimal(
                data,
                "volume_max",
                fallback=account_symbol.max_volume,
                required=True,
                symbol=broker_symbol,
            ),
            volume_step=self._symbol_decimal(
                data,
                "volume_step",
                fallback=account_symbol.volume_step,
                required=True,
                symbol=broker_symbol,
            ),
            margin_rate=self._margin_rate,
        )

    @staticmethod
    async def _find_account_symbol(
        *,
        repository: AccountSymbolRepository,
        account_id: UUID,
        canonical_symbol: str,
    ) -> AccountSymbol | None:
        """
        Find an AccountSymbol by canonical Symbol.

        AccountSymbolRepository currently exposes lookup by symbol_id and
        broker_symbol, but not directly by canonical symbol name.

        Because the account's symbol list is already scoped to one account,
        resolving the canonical name in memory is deterministic and avoids
        adding broker-specific behavior to the repository.
        """

        account_symbols = (
            await repository.list_by_account(account_id)
        )

        for account_symbol in account_symbols:
            if account_symbol.symbol is None:
                continue

            symbol_name = getattr(
                account_symbol.symbol,
                "name",
                None,
            )

            if (
                symbol_name is not None
                and str(symbol_name).strip().upper()
                == canonical_symbol
            ):
                return account_symbol

        return None

    # ======================================================================
    # MARKET
    # ======================================================================

    async def _get_market_state(
        self,
        account_id: UUID,
        broker_symbol: str,
    ) -> LiveMarketState:
        """
        Retrieve the current broker bid/ask.

        account_id is accepted because the provider contract is
        account-scoped. BrokerManager itself is already expected to be
        connected to the appropriate account adapter.
        """

        del account_id

        data = await self._broker_manager.get_tick(broker_symbol)

        if not isinstance(data, dict):
            raise ValueError(
                f"Broker returned invalid tick data for {broker_symbol!r}."
            )

        bid = self._required_decimal(
            data,
            "bid",
            broker_symbol,
        )

        ask = self._required_decimal(
            data,
            "ask",
            broker_symbol,
        )

        if bid <= Decimal("0"):
            raise ValueError(
                f"Broker returned an invalid bid for "
                f"{broker_symbol!r}: {bid}"
            )

        if ask <= Decimal("0"):
            raise ValueError(
                f"Broker returned an invalid ask for "
                f"{broker_symbol!r}: {ask}"
            )

        if ask < bid:
            raise ValueError(
                f"Broker returned ask below bid for "
                f"{broker_symbol!r}: bid={bid}, ask={ask}"
            )

        return LiveMarketState(
            bid=bid,
            ask=ask,
        )

    # ======================================================================
    # RISK CONFIG
    # ======================================================================

    async def _get_risk_config(
        self,
        account_id: UUID,
        signal: TradingSignal,
    ) -> RiskConfig:
        """
        Resolve the risk configuration for the account/signal.

        A dynamic provider can be supplied later for per-account or
        per-strategy risk configuration.
        """

        if self._risk_config_provider is not None:
            result = self._risk_config_provider(
                account_id,
                signal,
            )

            config = (
                await result
                if hasattr(result, "__await__")
                else result
            )

            if not isinstance(config, RiskConfig):
                raise TypeError(
                    "risk_config_provider must return RiskConfig."
                )

            return config

        return self._risk_config

    # ======================================================================
    # VALUE CONVERSION
    # ======================================================================

    @staticmethod
    def _decimal(
        value,
        *,
        field: str,
    ) -> Decimal:
        """
        Convert a database/broker numeric value to Decimal.
        """

        if value is None:
            raise ValueError(
                f"{field} cannot be None."
            )

        try:
            return Decimal(str(value))
        except Exception as exc:
            raise ValueError(
                f"{field} contains an invalid numeric value: {value!r}"
            ) from exc

    @staticmethod
    def _required_decimal(
        data: dict,
        key: str,
        symbol: str,
    ) -> Decimal:
        """
        Extract a required numeric broker field.
        """

        if key not in data or data[key] is None:
            raise ValueError(
                f"Broker symbol {symbol!r} is missing required "
                f"field {key!r}."
            )

        try:
            return Decimal(str(data[key]))
        except Exception as exc:
            raise ValueError(
                f"Broker symbol {symbol!r} returned an invalid "
                f"value for {key!r}: {data[key]!r}"
            ) from exc

    @staticmethod
    def _symbol_decimal(
        data: dict,
        key: str,
        *,
        fallback: Decimal | None = None,
        required: bool = False,
        symbol: str,
    ) -> Decimal:
        """
        Extract a broker symbol numeric field with optional DB fallback.

        The AccountSymbol database values are used as a fallback for fields
        that may legitimately be absent from an older persisted record.

        For tick_value, no fallback is allowed because AccountSymbol does
        not currently persist it and the position-size calculation requires
        it.
        """

        value = data.get(key)

        if value is None:
            if fallback is not None:
                return LiveContextFactory._decimal(
                    fallback,
                    field=f"AccountSymbol.{key}",
                )

            if required:
                raise ValueError(
                    f"Broker symbol {symbol!r} is missing required "
                    f"field {key!r}."
                )

            return Decimal("0")

        try:
            return Decimal(str(value))
        except Exception as exc:
            raise ValueError(
                f"Broker symbol {symbol!r} returned an invalid "
                f"value for {key!r}: {value!r}"
            ) from exc


# ============================================================================
# Convenience factory function
# ============================================================================


def create_live_context_provider(
    *,
    session_factory: SessionFactory,
    broker_manager: BrokerManager,
    account_id_resolver: AccountIdResolver,
    risk_config: RiskConfig | None = None,
    risk_config_provider: (
        Callable[
            [UUID, TradingSignal],
            Awaitable[RiskConfig] | RiskConfig,
        ]
        | None
    ) = None,
    margin_rate: Decimal = Decimal("0"),
) -> LiveRiskContextProvider:
    """
    Create the application's concrete live Risk Context Provider.

    Example:

        provider = create_live_context_provider(
            session_factory=SessionLocal,
            broker_manager=broker_manager,
            account_id_resolver=resolve_account,
            risk_config=RiskConfig(),
        )
    """

    factory = LiveContextFactory(
        session_factory=session_factory,
        broker_manager=broker_manager,
        account_id_resolver=account_id_resolver,
        risk_config=risk_config,
        risk_config_provider=risk_config_provider,
        margin_rate=margin_rate,
    )

    return factory.create()