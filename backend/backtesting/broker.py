"""Broker adapter used exclusively by the AQE backtesting environment."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from app.broker.base import BrokerAdapter
from app.broker.exceptions import (
    BrokerConnectionError,
    BrokerDataError,
    BrokerOrderError,
    BrokerPositionError,
)
from app.schemas.execution import (
    ExecutionOrder,
    ExecutionResult,
    ExecutionStatus,
    OrderType,
)

from .execution import BacktestExecution
from .market import BacktestMarket
from .portfolio import BacktestPortfolio


class BacktestBrokerAdapter(BrokerAdapter):
    """
    BrokerAdapter implementation for AQE backtesting.

    This adapter provides a broker-compatible interface over the
    simulated backtest portfolio.

    It never:

        - connects to MT5
        - connects to a real broker
        - accesses Redis
        - accesses PostgreSQL
        - loads historical market data
        - generates strategy signals
        - evaluates risk

    ``BacktestEngine`` remains the owner of:

        - historical event sequencing
        - simulation time
        - pending-order lifecycle
        - historical execution records

    ``BacktestExecution`` remains the owner of:

        - fill generation for immediately executable orders
        - fill application
        - position opening
        - position closing
        - SL/TP position exits

    This adapter exists primarily as a broker-interface compatibility
    layer for components that expect a ``BrokerAdapter``.
    """

    broker_name = "BACKTEST"

    def __init__(
        self,
        portfolio: BacktestPortfolio,
        execution: BacktestExecution,
        contract_sizes: dict[str, Decimal] | None = None,
    ) -> None:
        if portfolio is None:
            raise TypeError("portfolio is required.")

        if execution is None:
            raise TypeError("execution is required.")

        self.portfolio = portfolio
        self.execution = execution

        self._contract_sizes: dict[str, Decimal] = {}

        for symbol, contract_size in (
            contract_sizes or {}
        ).items():
            normalized_symbol = self._normalize_symbol(symbol)

            if not isinstance(contract_size, Decimal):
                contract_size = Decimal(str(contract_size))

            if contract_size <= Decimal("0"):
                raise ValueError(
                    f"Contract size for '{normalized_symbol}' "
                    "must be greater than zero."
                )

            self._contract_sizes[
                normalized_symbol
            ] = contract_size

        self._connected = False

        # Current market state is supplied by the backtest runtime.
        self._current_market: dict[
            str,
            BacktestMarket,
        ] = {}

    # ==================================================================
    # CONNECTION
    # ==================================================================

    async def connect(
        self,
        credentials: dict,
    ) -> dict[str, Any]:
        """
        Open the local simulated broker session.

        No real credentials are consumed.
        """
        if credentials is None:
            credentials = {}

        if not isinstance(credentials, dict):
            raise BrokerConnectionError(
                "Backtest broker credentials must be a dictionary."
            )

        self._connected = True

        return {
            "connected": True,
            "broker": self.broker_name,
            "account_id": str(self.portfolio.account_id),
            "simulated": True,
        }

    async def disconnect(self) -> None:
        """Close the local simulated broker session."""
        self._connected = False
        self._current_market.clear()

    async def connection_status(
        self,
    ) -> dict[str, Any]:
        """Return the current simulated broker connection state."""
        return {
            "connected": self._connected,
            "broker": self.broker_name,
            "account_id": str(self.portfolio.account_id),
            "simulated": True,
        }

    # ==================================================================
    # ACCOUNT
    # ==================================================================

    async def get_account(self) -> dict[str, Any]:
        """
        Return the current simulated account state.

        Equity is marked to the latest registered market prices when
        market state is available.
        """
        self._ensure_connected()

        prices = {
            symbol: market.mid
            for symbol, market in self._current_market.items()
        }

        contract_sizes = self._effective_contract_sizes()

        if prices:
            equity = self.portfolio.mark_to_market(
                prices=prices,
                timestamp=self._latest_market_timestamp(),
                contract_sizes=contract_sizes,
            )
        else:
            equity = self.portfolio.balance

        unrealized_pnl = self.portfolio.total_unrealized_pnl(
            prices=prices,
            contract_sizes=contract_sizes,
        )

        return {
            "account_id": str(self.portfolio.account_id),
            "broker": self.broker_name,
            "balance": self.portfolio.balance,
            "equity": equity,
            "margin": self.portfolio.margin,
            "free_margin": self.portfolio.free_margin,
            "margin_level": self.portfolio.margin_level,
            "unrealized_pnl": unrealized_pnl,
            "currency": "USD",
            "simulated": True,
        }

    # ==================================================================
    # MARKET DATA
    # ==================================================================

    async def get_symbols(
        self,
    ) -> list[dict[str, Any]]:
        """
        Return symbols currently registered in the simulated market.

        Historical symbol discovery belongs to the backtest composition
        and market-data loading layers.
        """
        self._ensure_connected()

        return [
            {
                "symbol": symbol,
                "broker": self.broker_name,
                "simulated": True,
            }
            for symbol in sorted(self._current_market)
        ]

    async def get_symbol(
        self,
        symbol: str,
    ) -> dict[str, Any]:
        """Return the current simulated quote for a symbol."""
        self._ensure_connected()

        normalized = self._normalize_symbol(symbol)
        market = self._get_market(normalized)

        return {
            "symbol": normalized,
            "broker": self.broker_name,
            "bid": self._bid(market),
            "ask": self._ask(market),
            "last": market.candle.close,
            "timestamp": market.candle.timestamp,
            "simulated": True,
        }

    async def get_tick(
        self,
        symbol: str,
    ) -> dict[str, Any]:
        """Return the current simulated tick for a symbol."""
        self._ensure_connected()

        normalized = self._normalize_symbol(symbol)
        market = self._get_market(normalized)

        return {
            "symbol": normalized,
            "timestamp": market.candle.timestamp,
            "bid": self._bid(market),
            "ask": self._ask(market),
            "last": market.candle.close,
            "simulated": True,
        }

    async def get_candles(
        self,
        symbol: str,
        timeframe: str = "M15",
        count: int = 200,
    ) -> list[dict[str, Any]]:
        """
        Return the currently visible simulated candle.

        This compatibility method deliberately does not perform
        historical lookback. Historical data is supplied by the
        backtest market-data layer and replayed by ``BacktestEngine``.
        """
        self._ensure_connected()

        if count <= 0:
            raise BrokerDataError(
                "Candle count must be greater than zero."
            )

        normalized_symbol = self._normalize_symbol(symbol)
        normalized_timeframe = self._normalize_timeframe(
            timeframe
        )

        market = self._get_market(normalized_symbol)
        candle = market.candle

        if (
            self._normalize_timeframe(candle.timeframe)
            != normalized_timeframe
        ):
            return []

        return [
            {
                "symbol": normalized_symbol,
                "timeframe": normalized_timeframe,
                "timestamp": candle.timestamp,
                "open": candle.open,
                "high": candle.high,
                "low": candle.low,
                "close": candle.close,
                "volume": candle.volume,
                "spread": candle.spread,
            }
        ]

    # ==================================================================
    # ORDERS
    # ==================================================================

    async def get_orders(
        self,
    ) -> list[dict[str, Any]]:
        """
        Return active simulated orders.

        Pending-order state belongs to the backtest pending-order
        subsystem, so this compatibility adapter does not maintain
        a second order store.
        """
        self._ensure_connected()

        return []

    async def place_order(
        self,
        order: ExecutionOrder,
    ) -> ExecutionResult:
        """
        Execute an immediately executable MARKET order.

        The account-level backtest pipeline normally invokes
        ``BacktestExecution`` through ``BacktestEngine`` directly.

        This method exists for broker-interface compatibility.
        """
        self._ensure_connected()

        if order is None:
            raise BrokerOrderError(
                "ExecutionOrder is required."
            )

        if order.order_type != OrderType.MARKET:
            raise BrokerOrderError(
                "place_order() only supports MARKET orders. "
                "LIMIT and STOP orders are managed by the "
                "backtest pending-order subsystem."
            )

        market = self._get_market(order.symbol)

        try:
            return self.execution.execute(
                order=order,
                market=market,
            )

        except BrokerOrderError:
            raise

        except Exception as exc:
            raise BrokerOrderError(
                "Backtest market-order execution failed: "
                f"{type(exc).__name__}: {exc}"
            ) from exc

    async def create_pending_order(
        self,
        order: ExecutionOrder,
    ) -> ExecutionResult:
        """
        Reject direct broker execution of a LIMIT/STOP order.

        Pending orders require historical lifecycle management across
        multiple candles. ``BacktestEngine`` owns that lifecycle.

        This method intentionally does not call
        ``BacktestExecution.execute()`` because that method is
        restricted to MARKET orders.
        """
        self._ensure_connected()

        if order is None:
            raise BrokerOrderError(
                "ExecutionOrder is required."
            )

        if order.order_type not in {
            OrderType.LIMIT,
            OrderType.STOP,
        }:
            raise BrokerOrderError(
                "create_pending_order() requires a LIMIT or STOP order."
            )

        if (
            order.price is None
            or order.price <= Decimal("0")
        ):
            raise BrokerOrderError(
                "Pending orders require a positive entry price."
            )

        return ExecutionResult(
            status=ExecutionStatus.REJECTED,
            broker=self.broker_name,
            symbol=self._normalize_symbol(order.symbol),
            volume=order.volume,
            price=None,
            message=(
                "Pending orders must be registered by "
                "BacktestEngine. They cannot be created directly "
                "through BacktestBrokerAdapter."
            ),
            raw_response={
                "order_type": order.order_type.value,
                "pending": True,
                "managed_by": "BacktestEngine",
            },
        )

    # ==================================================================
    # POSITIONS
    # ==================================================================

    async def get_positions(
        self,
    ) -> list[dict[str, Any]]:
        """Return all currently open simulated positions."""
        self._ensure_connected()

        contract_sizes = self._effective_contract_sizes()
        positions: list[dict[str, Any]] = []

        for position in self.portfolio.open_positions:
            normalized_symbol = self._normalize_symbol(
                position.symbol
            )

            market = self._current_market.get(
                normalized_symbol
            )

            current_price = (
                market.mid
                if market is not None
                else position.entry_price
            )

            contract_size = contract_sizes.get(
                normalized_symbol,
                Decimal("1"),
            )

            positions.append(
                {
                    "position_id": str(position.position_id),
                    "broker_position_id": self._uuid_as_int(
                        position.position_id
                    ),
                    "account_id": str(position.account_id),
                    "symbol": normalized_symbol,
                    "side": position.side.value,
                    "volume": position.volume,
                    "entry_price": position.entry_price,
                    "current_price": current_price,
                    "stop_loss": position.stop_loss,
                    "take_profit": position.take_profit,
                    "unrealized_pnl": position.unrealized_pnl(
                        current_price=current_price,
                        contract_size=contract_size,
                    ),
                    "opened_at": position.opened_at,
                    "strategy_id": position.strategy_id,
                    "strategy_name": position.strategy_name,
                    "simulated": True,
                }
            )

        return positions

    async def get_position(
        self,
        position_id: int,
    ) -> dict[str, Any]:
        """Return one simulated position by broker-compatible ID."""
        self._ensure_connected()

        if position_id <= 0:
            raise BrokerPositionError(
                "Position ID must be greater than zero."
            )

        position = self._find_position_by_broker_id(
            position_id
        )

        if position is None:
            raise BrokerPositionError(
                f"Backtest position '{position_id}' was not found."
            )

        normalized_symbol = self._normalize_symbol(
            position.symbol
        )

        market = self._current_market.get(
            normalized_symbol
        )

        current_price = (
            market.mid
            if market is not None
            else position.entry_price
        )

        contract_size = self._effective_contract_sizes().get(
            normalized_symbol,
            Decimal("1"),
        )

        return {
            "position_id": str(position.position_id),
            "broker_position_id": self._uuid_as_int(
                position.position_id
            ),
            "account_id": str(position.account_id),
            "symbol": normalized_symbol,
            "side": position.side.value,
            "volume": position.volume,
            "entry_price": position.entry_price,
            "current_price": current_price,
            "stop_loss": position.stop_loss,
            "take_profit": position.take_profit,
            "unrealized_pnl": position.unrealized_pnl(
                current_price=current_price,
                contract_size=contract_size,
            ),
            "opened_at": position.opened_at,
            "strategy_id": position.strategy_id,
            "strategy_name": position.strategy_name,
            "simulated": True,
        }

    async def modify_position(
        self,
        position_id: int,
        sl: float | None = None,
        tp: float | None = None,
    ) -> dict[str, Any]:
        """Modify the simulated position's protective levels."""
        self._ensure_connected()

        if position_id <= 0:
            raise BrokerPositionError(
                "Position ID must be greater than zero."
            )

        if sl is None and tp is None:
            raise BrokerPositionError(
                "At least one of sl or tp must be provided."
            )

        position = self._find_position_by_broker_id(
            position_id
        )

        if position is None:
            raise BrokerPositionError(
                f"Backtest position '{position_id}' was not found."
            )

        if sl is not None:
            stop_loss = Decimal(str(sl))

            if stop_loss <= Decimal("0"):
                raise BrokerPositionError(
                    "Stop loss must be greater than zero."
                )

            position.stop_loss = stop_loss

        if tp is not None:
            take_profit = Decimal(str(tp))

            if take_profit <= Decimal("0"):
                raise BrokerPositionError(
                    "Take profit must be greater than zero."
                )

            position.take_profit = take_profit

        return {
            "position_id": str(position.position_id),
            "broker_position_id": self._uuid_as_int(
                position.position_id
            ),
            "stop_loss": position.stop_loss,
            "take_profit": position.take_profit,
            "simulated": True,
        }

    async def close_position(
        self,
        position_id: int,
    ) -> ExecutionResult:
        """Close a simulated open position at the current market."""
        self._ensure_connected()

        if position_id <= 0:
            raise BrokerPositionError(
                "Position ID must be greater than zero."
            )

        position = self._find_position_by_broker_id(
            position_id
        )

        if position is None:
            raise BrokerPositionError(
                f"Backtest position '{position_id}' was not found."
            )

        market = self._get_market(position.symbol)

        contract_size = self._effective_contract_sizes().get(
            self._normalize_symbol(position.symbol),
            Decimal("1"),
        )

        try:
            return self.execution.close_position(
                position_id=position.position_id,
                market=market,
                exit_reason="MANUAL",
                contract_size=contract_size,
            )

        except Exception as exc:
            raise BrokerPositionError(
                "Backtest position close failed: "
                f"{type(exc).__name__}: {exc}"
            ) from exc

    # ==================================================================
    # HISTORY
    # ==================================================================

    async def get_order_history(
        self,
        start: datetime,
        end: datetime,
    ) -> list[dict[str, Any]]:
        """
        Return simulated order history.

        ``BacktestEngine`` is the authoritative execution-history
        owner, so this broker compatibility adapter does not maintain
        a duplicate history store.
        """
        self._ensure_connected()

        self._validate_history_range(
            start,
            end,
        )

        return []

    async def get_deal_history(
        self,
        start: datetime,
        end: datetime,
    ) -> list[dict[str, Any]]:
        """
        Return simulated deal history.

        Detailed results belong to the backtest result layer.
        """
        self._ensure_connected()

        self._validate_history_range(
            start,
            end,
        )

        return []

    async def get_deals_by_position(
        self,
        position_id: int,
    ) -> list[dict[str, Any]]:
        """
        Return simulated deals associated with a position.

        Detailed deal reporting belongs to the backtest result layer.
        """
        self._ensure_connected()

        if position_id <= 0:
            raise BrokerOrderError(
                "Position ID must be greater than zero."
            )

        return []

    # ==================================================================
    # MARKET REGISTRATION
    # ==================================================================

    def update_market(
        self,
        market: BacktestMarket,
    ) -> None:
        """
        Register the latest simulated market state for one symbol.

        ``BacktestEngine`` should call this before broker-style
        operations that require current market state.
        """
        if market is None:
            raise ValueError("market is required.")

        if not isinstance(market, BacktestMarket):
            raise TypeError(
                "market must be a BacktestMarket instance."
            )

        symbol = self._normalize_symbol(market.symbol)

        self._current_market[symbol] = market

    def update_markets(
        self,
        markets: list[BacktestMarket],
    ) -> None:
        """Register multiple current simulated markets."""
        if markets is None:
            raise ValueError("markets is required.")

        for market in markets:
            self.update_market(market)

    def clear_market(self) -> None:
        """Clear all currently registered simulated market state."""
        self._current_market.clear()

    # ==================================================================
    # CONTRACT SIZES
    # ==================================================================

    def set_contract_size(
        self,
        symbol: str,
        contract_size: Decimal,
    ) -> None:
        """Set the simulated contract size for a symbol."""
        normalized_symbol = self._normalize_symbol(symbol)

        if not isinstance(contract_size, Decimal):
            contract_size = Decimal(str(contract_size))

        if contract_size <= Decimal("0"):
            raise ValueError(
                "Contract size must be greater than zero."
            )

        self._contract_sizes[
            normalized_symbol
        ] = contract_size

    def set_contract_sizes(
        self,
        contract_sizes: dict[str, Decimal],
    ) -> None:
        """Add or replace simulated contract-size mappings."""
        if contract_sizes is None:
            raise ValueError(
                "contract_sizes is required."
            )

        for symbol, contract_size in contract_sizes.items():
            self.set_contract_size(
                symbol,
                contract_size,
            )

    # ==================================================================
    # HELPERS
    # ==================================================================

    def _effective_contract_sizes(
        self,
    ) -> dict[str, Decimal]:
        """
        Return configured contract sizes supplemented by the
        portfolio's currently open symbols.

        Unconfigured symbols intentionally fall back to one.
        """
        contract_sizes = dict(
            self._contract_sizes
        )

        for position in self.portfolio.open_positions:
            symbol = self._normalize_symbol(
                position.symbol
            )

            contract_sizes.setdefault(
                symbol,
                Decimal("1"),
            )

        return contract_sizes

    def _get_market(
        self,
        symbol: str,
    ) -> BacktestMarket:
        """Return the current simulated market for a symbol."""
        normalized = self._normalize_symbol(symbol)

        market = self._current_market.get(
            normalized
        )

        if market is None:
            raise BrokerDataError(
                f"No current backtest market for '{normalized}'."
            )

        return market

    def _find_position_by_broker_id(
        self,
        position_id: int,
    ):
        """Find a simulated position using its broker-compatible ID."""
        for position in self.portfolio.positions.values():
            if (
                self._uuid_as_int(position.position_id)
                == position_id
            ):
                return position

        return None

    def _ensure_connected(self) -> None:
        """Ensure broker operations occur inside an active session."""
        if not self._connected:
            raise BrokerConnectionError(
                "Backtest broker is not connected."
            )

    @staticmethod
    def _normalize_symbol(
        symbol: str,
    ) -> str:
        """Normalize a trading symbol."""
        if not isinstance(symbol, str):
            raise BrokerDataError(
                "Symbol must be a string."
            )

        normalized = symbol.strip().upper()

        if not normalized:
            raise BrokerDataError(
                "Symbol cannot be empty."
            )

        return normalized

    @staticmethod
    def _normalize_timeframe(
        timeframe: str,
    ) -> str:
        """Normalize a timeframe identifier."""
        if not isinstance(timeframe, str):
            raise BrokerDataError(
                "Timeframe must be a string."
            )

        normalized = timeframe.strip().upper()

        if not normalized:
            raise BrokerDataError(
                "Timeframe cannot be empty."
            )

        return normalized

    @staticmethod
    def _bid(
        market: BacktestMarket,
    ) -> Decimal:
        """Return the current simulated bid."""
        if market.bid is not None:
            return market.bid

        return market.candle.close

    @staticmethod
    def _ask(
        market: BacktestMarket,
    ) -> Decimal:
        """Return the current simulated ask."""
        if market.ask is not None:
            return market.ask

        return market.candle.close

    def _latest_market_timestamp(
        self,
    ) -> datetime | None:
        """Return the latest timestamp among registered markets."""
        if not self._current_market:
            return None

        return max(
            market.candle.timestamp
            for market in self._current_market.values()
        )

    @staticmethod
    def _validate_history_range(
        start: datetime,
        end: datetime,
    ) -> None:
        """Validate a historical query range."""
        if not isinstance(start, datetime):
            raise BrokerDataError(
                "History start must be a datetime."
            )

        if not isinstance(end, datetime):
            raise BrokerDataError(
                "History end must be a datetime."
            )

        if start >= end:
            raise BrokerDataError(
                "History start must be before history end."
            )

    @staticmethod
    def _uuid_as_int(
        value: UUID,
    ) -> int:
        """
        Convert an AQE UUID into a positive broker-compatible integer.
        """
        if not isinstance(value, UUID):
            raise BrokerDataError(
                "Broker identifier source must be a UUID."
            )

        return value.int % (2**63 - 1) or 1