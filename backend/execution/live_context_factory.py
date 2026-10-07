from __future__ import annotations

from decimal import Decimal
from typing import Any, Awaitable, Callable
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

    Current broker trading state is authoritative for LIVE risk evaluation:

        MT5
        ├── account_info()
        ├── positions_get()
        ├── symbol_info()
        └── tick

    AQE persistence remains authoritative for AQE-specific metadata:

        PostgreSQL
        ├── TradingAccount identity/configuration
        ├── Position.id
        ├── Position.ticket
        ├── Position.broker_position_id
        ├── Position.strategy
        ├── Position.initial_risk
        ├── AccountSymbol
        └── canonical symbol mapping

    Responsibilities:
        - create database sessions per operation;
        - retrieve current broker account state;
        - retrieve current broker positions;
        - correlate broker positions with AQE positions;
        - resolve AccountSymbol mappings;
        - retrieve live broker symbol metadata;
        - retrieve live broker market prices;
        - convert state into Risk Engine models;
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

        account_id = await result if hasattr(result, "__await__") else result

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
        Load the current account financial state directly from the broker.

        MT5 account_info() is authoritative for:

            balance
            equity
            margin
            margin_free
            margin_level

        PostgreSQL TradingAccount remains useful for AQE account metadata,
        but its synchronized financial snapshot must not be treated as the
        authoritative source for a LIVE risk decision.

        A fresh broker request is performed for every risk-context build.
        """

        data = await self._broker_manager.get_account()

        if not isinstance(data, dict):
            raise ValueError("Broker returned invalid account state.")

        balance = self._required_decimal(
            data,
            "balance",
            "account",
        )

        equity = self._required_decimal(
            data,
            "equity",
            "account",
        )

        margin = self._required_decimal(
            data,
            "margin",
            "account",
        )

        free_margin = self._required_decimal(
            data,
            "margin_free",
            "account",
        )

        margin_level = self._optional_decimal(
            data,
            "margin_level",
            "account",
        )

        if balance < Decimal("0"):
            raise ValueError(f"Broker returned invalid account balance: {balance}")

        if equity < Decimal("0"):
            raise ValueError(f"Broker returned invalid account equity: {equity}")

        if margin < Decimal("0"):
            raise ValueError(f"Broker returned invalid account margin: {margin}")

        if free_margin < Decimal("0"):
            raise ValueError(f"Broker returned invalid free margin: {free_margin}")

        if margin_level is not None and margin_level < Decimal("0"):
            raise ValueError(f"Broker returned invalid margin level: {margin_level}")

        return LiveAccountState(
            account_id=account_id,
            balance=balance,
            equity=equity,
            margin=margin,
            free_margin=free_margin,
            margin_level=margin_level,
            # These are intentionally not fabricated from the current
            # broker snapshot. Daily P/L and peak equity require a defined
            # session/history policy and are handled separately.
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
        Load the broker's current open positions and correlate them with AQE.

        Broker state is authoritative for current:

            volume
            entry price
            current price
            stop loss
            take profit
            floating profit
            direction

        AQE persistence supplies:

            Position.id
            canonical symbol
            strategy
            initial risk
            broker correlation metadata

        An open broker position that cannot be correlated to an AQE Position
        is treated as a reconciliation failure rather than silently ignored.

        Silently ignoring an externally-created or otherwise-unreconciled
        live position could cause RiskEngine to underestimate exposure.
        """

        broker_positions = await self._broker_manager.get_positions()

        if broker_positions is None:
            broker_positions = []

        if not isinstance(broker_positions, list):
            broker_positions = list(broker_positions)

        async with self._session_factory() as db:
            position_repository = PositionRepository(db)

            aqe_positions = await position_repository.get_open_positions_by_account(
                account_id,
            )

        by_ticket: dict[int, Position] = {}
        by_broker_position_id: dict[str, Position] = {}

        for position in aqe_positions:
            if position.account_id != account_id:
                continue

            if position.ticket in by_ticket:
                raise ValueError(
                    f"Duplicate AQE position ticket detected for account "
                    f"{account_id}: ticket={position.ticket}"
                )

            by_ticket[int(position.ticket)] = position

            if position.broker_position_id is not None:
                broker_position_id = str(position.broker_position_id).strip()

                if broker_position_id:
                    existing = by_broker_position_id.get(
                        broker_position_id,
                    )

                    if existing is not None and existing.id != position.id:
                        raise ValueError(
                            "Duplicate AQE broker position ID detected for "
                            f"account {account_id}: "
                            f"broker_position_id={broker_position_id!r}"
                        )

                    by_broker_position_id[broker_position_id] = position

        live_positions: list[LivePositionState] = []
        matched_aqe_ids: set[UUID] = set()

        for broker_position in broker_positions:
            if not isinstance(broker_position, dict):
                raise ValueError("Broker returned an invalid position object.")

            aqe_position = self._correlate_broker_position(
                broker_position=broker_position,
                by_ticket=by_ticket,
                by_broker_position_id=by_broker_position_id,
                account_id=account_id,
            )

            if aqe_position.id in matched_aqe_ids:
                raise ValueError(
                    "Multiple broker positions resolved to the same AQE "
                    f"position: position_id={aqe_position.id}"
                )

            matched_aqe_ids.add(aqe_position.id)

            live_positions.append(
                self._broker_position_to_live_state(
                    broker_position=broker_position,
                    aqe_position=aqe_position,
                    account_id=account_id,
                )
            )

        return live_positions

    @staticmethod
    def _correlate_broker_position(
        *,
        broker_position: dict[str, Any],
        by_ticket: dict[int, Position],
        by_broker_position_id: dict[str, Position],
        account_id: UUID,
    ) -> Position:
        """
        Correlate one current broker position with an AQE Position.

        MT5 provides both:

            ticket
            identifier

        AQE persists them separately as:

            Position.ticket
            Position.broker_position_id

        The identifier is preferred when available. Ticket is retained as
        a fallback because older AQE records may not yet have a
        broker_position_id populated.
        """

        ticket = broker_position.get("ticket")
        identifier = broker_position.get("identifier")

        position_by_identifier: Position | None = None
        position_by_ticket: Position | None = None

        if identifier is not None:
            identifier_key = str(identifier).strip()

            if identifier_key:
                position_by_identifier = by_broker_position_id.get(
                    identifier_key,
                )

        if ticket is not None:
            try:
                ticket_value = int(ticket)
            except (TypeError, ValueError) as exc:
                raise ValueError("Broker returned an invalid position ticket.") from exc

            position_by_ticket = by_ticket.get(
                ticket_value,
            )

        if (
            position_by_identifier is not None
            and position_by_ticket is not None
            and position_by_identifier.id != position_by_ticket.id
        ):
            raise ValueError(
                "Broker position correlation is inconsistent: "
                f"ticket={ticket!r} and identifier={identifier!r} "
                "resolve to different AQE positions."
            )

        position = position_by_identifier or position_by_ticket

        if position is None:
            raise ValueError(
                "Current broker position is not correlated with an AQE "
                f"open position. account_id={account_id} "
                f"ticket={ticket!r} identifier={identifier!r} "
                f"symbol={broker_position.get('symbol')!r}."
            )

        return position

    @staticmethod
    def _broker_position_to_live_state(
        *,
        broker_position: dict[str, Any],
        aqe_position: Position,
        account_id: UUID,
    ) -> LivePositionState:
        """
        Convert current MT5 position state plus AQE metadata into
        LivePositionState.
        """

        broker_account_id = aqe_position.account_id

        if broker_account_id != account_id:
            raise ValueError("Correlated AQE position belongs to a different account.")

        symbol = aqe_position.symbol

        if symbol is None:
            raise ValueError(
                f"AQE position {aqe_position.id} has no associated symbol."
            )

        canonical_symbol = getattr(
            symbol,
            "name",
            None,
        )

        if canonical_symbol is None or not str(canonical_symbol).strip():
            raise ValueError(
                f"AQE position {aqe_position.id} has an invalid canonical symbol."
            )

        position_type = broker_position.get("type")

        try:
            direction = LiveContextFactory._resolve_position_direction(
                position_type,
            )
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f"Unable to resolve MT5 position direction for "
                f"AQE position {aqe_position.id}: type={position_type!r}"
            ) from exc

        quantity = LiveContextFactory._required_decimal(
            broker_position,
            "volume",
            f"position[{aqe_position.id}]",
        )

        entry_price = LiveContextFactory._required_decimal(
            broker_position,
            "price_open",
            f"position[{aqe_position.id}]",
        )

        current_price = LiveContextFactory._required_decimal(
            broker_position,
            "price_current",
            f"position[{aqe_position.id}]",
        )

        floating_pnl = LiveContextFactory._required_decimal(
            broker_position,
            "profit",
            f"position[{aqe_position.id}]",
        )

        stop_loss = LiveContextFactory._optional_price(
            broker_position.get("sl"),
        )

        take_profit = LiveContextFactory._optional_price(
            broker_position.get("tp"),
        )

        initial_risk = (
            LiveContextFactory._decimal(
                aqe_position.initial_risk,
                field=f"position[{aqe_position.id}].initial_risk",
            )
            if aqe_position.initial_risk is not None
            else Decimal("0")
        )

        strategy_id = str(aqe_position.strategy).strip()

        if not strategy_id:
            strategy_id = None

        return LivePositionState(
            position_id=aqe_position.id,
            account_id=account_id,
            symbol=str(canonical_symbol).strip().upper(),
            direction=direction,
            quantity=quantity,
            entry_price=entry_price,
            current_price=current_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            unrealized_pnl=floating_pnl,
            risk_amount=initial_risk,
            strategy_id=strategy_id,
        )

    @staticmethod
    def _resolve_position_direction(
        position_type: Any,
    ):
        """
        Convert MT5 position type into AQE PositionDirection.

        MT5:
            0 = BUY
            1 = SELL
        """

        from app.core.constants import PositionDirection

        try:
            value = int(position_type)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Invalid MT5 position type: {position_type!r}") from exc

        if value == 0:
            return PositionDirection.BUY

        if value == 1:
            return PositionDirection.SELL

        raise ValueError(f"Unsupported MT5 position type: {value!r}")

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

        data = await self._broker_manager.get_symbol(
            broker_symbol,
        )

        if not isinstance(data, dict):
            raise ValueError(
                f"Broker returned invalid symbol metadata for " f"{broker_symbol!r}."
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

        account_symbols = await repository.list_by_account(
            account_id,
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
                and str(symbol_name).strip().upper() == canonical_symbol
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

        The BrokerManager instance is already account-scoped by runtime
        composition. account_id is therefore validated by the higher-level
        runtime routing contract and is not passed into BrokerManager itself.
        """

        del account_id

        data = await self._broker_manager.get_tick(
            broker_symbol,
        )

        if not isinstance(data, dict):
            raise ValueError(
                f"Broker returned invalid tick data for {broker_symbol!r}."
            )

        bid = self._required_decimal(
            data,
            "bid",
            f"tick[{broker_symbol}]",
        )

        ask = self._required_decimal(
            data,
            "ask",
            f"tick[{broker_symbol}]",
        )

        if bid <= Decimal("0"):
            raise ValueError(
                f"Broker returned an invalid bid for " f"{broker_symbol!r}: {bid}"
            )

        if ask <= Decimal("0"):
            raise ValueError(
                f"Broker returned an invalid ask for " f"{broker_symbol!r}: {ask}"
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

            config = await result if hasattr(result, "__await__") else result

            if not isinstance(config, RiskConfig):
                raise TypeError("risk_config_provider must return RiskConfig.")

            return config

        return self._risk_config

    # ======================================================================
    # VALUE CONVERSION
    # ======================================================================

    @staticmethod
    def _required_decimal(
        data: dict[str, Any],
        key: str,
        source: str,
    ) -> Decimal:
        """
        Extract a required numeric value from a broker payload.
        """

        if key not in data or data[key] is None:
            raise ValueError(f"{source} is missing required field {key!r}.")

        try:
            return Decimal(str(data[key]))
        except Exception as exc:
            raise ValueError(
                f"{source} returned an invalid numeric value for "
                f"{key!r}: {data[key]!r}"
            ) from exc

    @staticmethod
    def _optional_decimal(
        data: dict[str, Any],
        key: str,
        source: str,
    ) -> Decimal | None:
        """
        Extract an optional numeric value from a broker payload.
        """

        value = data.get(key)

        if value is None:
            return None

        try:
            return Decimal(str(value))
        except Exception as exc:
            raise ValueError(
                f"{source} returned an invalid numeric value for " f"{key!r}: {value!r}"
            ) from exc

    @staticmethod
    def _optional_price(
        value: Any,
    ) -> Decimal | None:
        """
        Convert an MT5 price field to Decimal.

        MT5 commonly represents an unset SL/TP as 0.0, which should become
        None in the AQE risk model.
        """

        if value is None:
            return None

        try:
            price = Decimal(str(value))
        except Exception as exc:
            raise ValueError(f"Invalid broker position price: {value!r}") from exc

        if price <= Decimal("0"):
            return None

        return price

    @staticmethod
    def _decimal(
        value: Any,
        *,
        field: str,
    ) -> Decimal:
        """
        Convert a numeric value to Decimal.
        """

        if value is None:
            raise ValueError(f"{field} cannot be None.")

        try:
            return Decimal(str(value))
        except Exception as exc:
            raise ValueError(
                f"{field} contains an invalid numeric value: {value!r}"
            ) from exc

    @staticmethod
    def _symbol_decimal(
        data: dict[str, Any],
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
                    f"Broker symbol {symbol!r} is missing required " f"field {key!r}."
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
    Create the application's concrete Live Risk Context Provider.
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


__all__ = [
    "LiveContextFactory",
    "create_live_context_provider",
]
