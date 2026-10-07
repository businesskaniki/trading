from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Awaitable, Callable
from uuid import UUID

from risk.config import RiskConfig
from risk.models import (
    AccountRiskSnapshot,
    MarketPricing,
    PositionRiskSnapshot,
    RiskContext,
    SymbolRiskConstraints,
)
from strategies.core.signal import TradingSignal

# ============================================================================
# Live broker/account state contracts
# ============================================================================


@dataclass(frozen=True, slots=True)
class LiveAccountState:
    """Current account state required by the Risk Engine."""

    account_id: UUID
    balance: Decimal
    equity: Decimal
    margin: Decimal
    free_margin: Decimal
    margin_level: Decimal | None = None
    daily_pnl: Decimal = Decimal("0")
    peak_equity: Decimal | None = None


@dataclass(frozen=True, slots=True)
class LivePositionState:
    """Current open-position state required by the Risk Engine."""

    position_id: UUID
    account_id: UUID
    symbol: str
    direction: object
    quantity: Decimal
    entry_price: Decimal
    current_price: Decimal
    stop_loss: Decimal | None = None
    take_profit: Decimal | None = None
    unrealized_pnl: Decimal = Decimal("0")
    risk_amount: Decimal = Decimal("0")
    strategy_id: str | None = None


@dataclass(frozen=True, slots=True)
class LiveSymbolState:
    """
    Broker-specific symbol specification.

    The symbol here is the broker symbol, for example:

        XAUUSD.s
    """

    symbol: str
    contract_size: Decimal
    tick_size: Decimal
    tick_value: Decimal
    volume_min: Decimal
    volume_max: Decimal
    volume_step: Decimal

    # Margin rate is intentionally supplied by the caller.
    #
    # MT5's current bridge SymbolResponse does not expose a margin_rate.
    # Do not derive it from account leverage because leverage does not
    # necessarily represent the instrument's actual margin requirement.
    margin_rate: Decimal = Decimal("0")


@dataclass(frozen=True, slots=True)
class LiveMarketState:
    """Current bid/ask for a broker symbol."""

    bid: Decimal
    ask: Decimal

    @property
    def mid(self) -> Decimal:
        return (self.bid + self.ask) / Decimal("2")


# ============================================================================
# Provider contracts
# ============================================================================


AccountIdResolver = Callable[
    [TradingSignal],
    Awaitable[UUID] | UUID,
]

AccountStateProvider = Callable[
    [UUID],
    Awaitable[LiveAccountState] | LiveAccountState,
]

PositionStateProvider = Callable[
    [UUID],
    Awaitable[list[LivePositionState]] | list[LivePositionState],
]

SymbolStateProvider = Callable[
    [UUID, str],
    Awaitable[LiveSymbolState] | LiveSymbolState,
]

MarketStateProvider = Callable[
    [UUID, str],
    Awaitable[LiveMarketState] | LiveMarketState,
]

RiskConfigProvider = Callable[
    [UUID, TradingSignal],
    Awaitable[RiskConfig] | RiskConfig,
]


# ============================================================================
# Live Risk Context Provider
# ============================================================================


class LiveRiskContextProvider:
    """
    Build a RiskContext from the current live trading environment.

    This class is deliberately an orchestration boundary.

    It does NOT:
        - evaluate risk;
        - calculate position size;
        - place orders;
        - modify positions;
        - write to PostgreSQL;
        - publish Redis events;
        - contain broker-specific order logic.

    Its only responsibility is to assemble the complete live state required
    by RiskEngine.evaluate().
    """

    def __init__(
        self,
        *,
        account_id_resolver: AccountIdResolver,
        account_provider: AccountStateProvider,
        positions_provider: PositionStateProvider,
        symbol_provider: SymbolStateProvider,
        market_provider: MarketStateProvider,
        risk_config_provider: RiskConfigProvider,
    ) -> None:
        self._account_id_resolver = account_id_resolver
        self._account_provider = account_provider
        self._positions_provider = positions_provider
        self._symbol_provider = symbol_provider
        self._market_provider = market_provider
        self._risk_config_provider = risk_config_provider

    async def build(self, signal: TradingSignal) -> RiskContext:
        """
        Resolve all live state required to evaluate a signal.

        The canonical signal symbol is used to resolve the account-specific
        broker symbol through the supplied symbol provider.

        Constraints are also resolved for every symbol represented by an
        existing position so the Risk Engine can calculate portfolio,
        symbol, and strategy exposure correctly.

        Example:

            signal.symbol = "XAUUSD"
                ↓
            symbol provider
                ↓
            broker symbol = "XAUUSD.s"

        If the account already has positions in:

            XAUUSD.s
            US100
            US30

        then RiskContext.constraints_by_symbol will contain constraints
        for all three symbols.
        """

        if not isinstance(signal, TradingSignal):
            raise TypeError("LiveRiskContextProvider.build() requires a TradingSignal.")

        account_id = await self._resolve_account_id(signal)

        account = await self._resolve_account(account_id)

        if account.account_id != account_id:
            raise ValueError(
                "Resolved account state does not match the requested "
                f"account_id={account_id}."
            )

        positions = await self._resolve_positions(account_id)

        canonical_symbol = self._normalize_symbol(signal.symbol)

        # Resolve the incoming signal symbol first. This remains the
        # dedicated symbol_constraints value used by RiskEngine for the
        # proposed trade.
        signal_symbol = await self._resolve_symbol(
            account_id=account_id,
            canonical_symbol=canonical_symbol,
        )

        market = await self._resolve_market(
            account_id=account_id,
            broker_symbol=signal_symbol.symbol,
        )

        config = await self._resolve_risk_config(
            account_id=account_id,
            signal=signal,
        )

        signal_constraints = self._build_symbol_constraints(
            symbol=signal_symbol,
            canonical_symbol=canonical_symbol,
        )

        constraints_by_symbol = await self._build_constraints_by_symbol(
            account_id=account_id,
            positions=positions,
            signal_symbol=signal_symbol,
            signal_canonical_symbol=canonical_symbol,
        )

        return RiskContext(
            account=self._build_account_snapshot(account),
            positions=self._build_position_snapshots(
                positions=positions,
                account_id=account_id,
            ),
            symbol_constraints=signal_constraints,
            constraints_by_symbol=constraints_by_symbol,
            market=self._build_market_pricing(market),
            config=config,
            signal=signal,
        )

    # ------------------------------------------------------------------
    # Resolution
    # ------------------------------------------------------------------

    async def _resolve_account_id(
        self,
        signal: TradingSignal,
    ) -> UUID:
        result = self._account_id_resolver(signal)

        account_id = await result if hasattr(result, "__await__") else result

        if not isinstance(account_id, UUID):
            try:
                account_id = UUID(str(account_id))
            except (ValueError, TypeError) as exc:
                raise ValueError(
                    "AccountIdResolver returned an invalid account ID."
                ) from exc

        return account_id

    async def _resolve_account(
        self,
        account_id: UUID,
    ) -> LiveAccountState:
        result = self._account_provider(account_id)

        account = await result if hasattr(result, "__await__") else result

        if not isinstance(account, LiveAccountState):
            raise TypeError("AccountStateProvider must return LiveAccountState.")

        return account

    async def _resolve_positions(
        self,
        account_id: UUID,
    ) -> list[LivePositionState]:
        result = self._positions_provider(account_id)

        positions = await result if hasattr(result, "__await__") else result

        if positions is None:
            return []

        if not isinstance(positions, list):
            positions = list(positions)

        for position in positions:
            if not isinstance(position, LivePositionState):
                raise TypeError(
                    "PositionStateProvider must return " "LivePositionState instances."
                )

            if position.account_id != account_id:
                raise ValueError(
                    "PositionStateProvider returned a position belonging "
                    f"to account {position.account_id}, expected {account_id}."
                )

            if not position.symbol.strip():
                raise ValueError(
                    f"Position {position.position_id} has an empty symbol."
                )

        return positions

    async def _resolve_symbol(
        self,
        *,
        account_id: UUID,
        canonical_symbol: str,
    ) -> LiveSymbolState:
        result = self._symbol_provider(
            account_id,
            canonical_symbol,
        )

        symbol = await result if hasattr(result, "__await__") else result

        if not isinstance(symbol, LiveSymbolState):
            raise TypeError("SymbolStateProvider must return LiveSymbolState.")

        if not symbol.symbol.strip():
            raise ValueError("Resolved broker symbol cannot be empty.")

        return symbol

    async def _resolve_market(
        self,
        *,
        account_id: UUID,
        broker_symbol: str,
    ) -> LiveMarketState:
        result = self._market_provider(
            account_id,
            broker_symbol,
        )

        market = await result if hasattr(result, "__await__") else result

        if not isinstance(market, LiveMarketState):
            raise TypeError("MarketStateProvider must return LiveMarketState.")

        if market.bid <= Decimal("0"):
            raise ValueError(f"Invalid market bid for {broker_symbol}: {market.bid}")

        if market.ask <= Decimal("0"):
            raise ValueError(f"Invalid market ask for {broker_symbol}: {market.ask}")

        if market.ask < market.bid:
            raise ValueError(
                f"Invalid market prices for {broker_symbol}: "
                f"ask={market.ask} < bid={market.bid}"
            )

        return market

    async def _resolve_risk_config(
        self,
        *,
        account_id: UUID,
        signal: TradingSignal,
    ) -> RiskConfig:
        result = self._risk_config_provider(
            account_id,
            signal,
        )

        config = await result if hasattr(result, "__await__") else result

        if not isinstance(config, RiskConfig):
            raise TypeError("RiskConfigProvider must return RiskConfig.")

        return config

    async def _build_constraints_by_symbol(
        self,
        *,
        account_id: UUID,
        positions: list[LivePositionState],
        signal_symbol: LiveSymbolState,
        signal_canonical_symbol: str,
    ) -> dict[str, SymbolRiskConstraints]:
        """
        Build symbol constraints for every symbol required by the Risk Engine.

        The resulting mapping is keyed by the canonical uppercase symbol
        used by PositionRiskSnapshot and ExposureRiskRule.

        The signal symbol is inserted first and reused whenever an existing
        position is on the same symbol. This prevents unnecessary duplicate
        symbol-provider calls.

        Existing positions on other symbols are resolved independently so
        their own contract sizes and trading constraints are used when
        calculating portfolio and strategy exposure.
        """

        constraints_by_symbol: dict[str, SymbolRiskConstraints] = {}

        # The incoming signal symbol is always required.
        constraints_by_symbol[signal_canonical_symbol] = self._build_symbol_constraints(
            symbol=signal_symbol,
            canonical_symbol=signal_canonical_symbol,
        )

        # Resolve constraints for every distinct existing-position symbol.
        #
        # Multiple positions can exist on the same symbol, so only perform
        # one symbol-provider lookup per distinct symbol.
        position_symbols: set[str] = set()

        for position in positions:
            position_symbol = self._normalize_symbol(position.symbol)
            position_symbols.add(position_symbol)

        for position_symbol in sorted(position_symbols):
            if position_symbol in constraints_by_symbol:
                continue

            resolved_symbol = await self._resolve_symbol(
                account_id=account_id,
                canonical_symbol=position_symbol,
            )

            constraints_by_symbol[position_symbol] = self._build_symbol_constraints(
                symbol=resolved_symbol,
                canonical_symbol=position_symbol,
            )

        return constraints_by_symbol

    # ------------------------------------------------------------------
    # Model conversion
    # ------------------------------------------------------------------

    @staticmethod
    def _build_account_snapshot(
        account: LiveAccountState,
    ) -> AccountRiskSnapshot:
        return AccountRiskSnapshot(
            account_id=account.account_id,
            balance=account.balance,
            equity=account.equity,
            margin=account.margin,
            free_margin=account.free_margin,
            margin_level=account.margin_level,
            daily_pnl=account.daily_pnl,
            peak_equity=account.peak_equity,
        )

    @staticmethod
    def _build_position_snapshots(
        *,
        positions: list[LivePositionState],
        account_id: UUID,
    ) -> list[PositionRiskSnapshot]:
        snapshots: list[PositionRiskSnapshot] = []

        for position in positions:
            if position.account_id != account_id:
                continue

            snapshots.append(
                PositionRiskSnapshot(
                    position_id=position.position_id,
                    account_id=position.account_id,
                    symbol=position.symbol.strip().upper(),
                    direction=position.direction,
                    quantity=position.quantity,
                    entry_price=position.entry_price,
                    current_price=position.current_price,
                    stop_loss=position.stop_loss,
                    take_profit=position.take_profit,
                    unrealized_pnl=position.unrealized_pnl,
                    risk_amount=position.risk_amount,
                    strategy_id=position.strategy_id,
                )
            )

        return snapshots

    @staticmethod
    def _build_symbol_constraints(
        *,
        symbol: LiveSymbolState,
        canonical_symbol: str,
    ) -> SymbolRiskConstraints:
        """
        Convert broker symbol metadata into Risk Engine constraints.

        Risk Engine calculations require:

            contract_size
            tick_size
            tick_value
            volume_min
            volume_max
            volume_step

        margin_rate is preserved when supplied, but the current Risk Engine
        does not yet use it for position sizing or margin validation.
        """

        if symbol.contract_size <= Decimal("0"):
            raise ValueError(
                f"Invalid contract size for {symbol.symbol}: " f"{symbol.contract_size}"
            )

        if symbol.tick_size <= Decimal("0"):
            raise ValueError(
                f"Invalid tick size for {symbol.symbol}: " f"{symbol.tick_size}"
            )

        if symbol.tick_value <= Decimal("0"):
            raise ValueError(
                f"Invalid tick value for {symbol.symbol}: " f"{symbol.tick_value}"
            )

        if symbol.volume_min <= Decimal("0"):
            raise ValueError(
                f"Invalid minimum volume for {symbol.symbol}: " f"{symbol.volume_min}"
            )

        if symbol.volume_max < symbol.volume_min:
            raise ValueError(
                f"Invalid volume range for {symbol.symbol}: "
                f"min={symbol.volume_min}, max={symbol.volume_max}"
            )

        if symbol.volume_step <= Decimal("0"):
            raise ValueError(
                f"Invalid volume step for {symbol.symbol}: " f"{symbol.volume_step}"
            )

        if symbol.margin_rate < Decimal("0"):
            raise ValueError(
                f"Invalid margin rate for {symbol.symbol}: " f"{symbol.margin_rate}"
            )

        return SymbolRiskConstraints(
            symbol=canonical_symbol,
            contract_size=symbol.contract_size,
            tick_size=symbol.tick_size,
            tick_value=symbol.tick_value,
            volume_min=symbol.volume_min,
            volume_max=symbol.volume_max,
            volume_step=symbol.volume_step,
            margin_rate=symbol.margin_rate,
        )

    @staticmethod
    def _build_market_pricing(
        market: LiveMarketState,
    ) -> MarketPricing:
        return MarketPricing(
            bid=market.bid,
            ask=market.ask,
        )

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------

    @staticmethod
    def _normalize_symbol(symbol: str) -> str:
        if not isinstance(symbol, str):
            raise TypeError("Symbol must be a string.")

        normalized = symbol.strip().upper()

        if not normalized:
            raise ValueError("Symbol cannot be empty.")

        return normalized
