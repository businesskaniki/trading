from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from app.broker.base import BrokerAdapter
from app.schemas.execution import ExecutionOrder, ExecutionResult

from .execution import (
    BacktestExecution,
    BacktestExecutionContext,
)
from .fill import BacktestMarket
from .portfolio import BacktestPortfolio


class BacktestBrokerAdapter(BrokerAdapter):
    """
    BrokerAdapter implementation for the AQE backtesting environment.

    This adapter deliberately exposes the same high-level broker
    operations used by the execution layer while routing orders into
    the deterministic backtest execution environment.

    No real broker, MT5 connection, Redis connection, or database
    connection is used here.
    """

    broker_name = "BACKTEST"

    def __init__(
        self,
        portfolio: BacktestPortfolio,
        execution: BacktestExecution,
    ) -> None:
        self.portfolio = portfolio
        self.execution = execution

        self._connected = False

        self._current_market: dict[str, BacktestMarket] = {}

    # ------------------------------------------------------------------
    # CONNECTION
    # ------------------------------------------------------------------

    async def connect(self, credentials: dict) -> dict[str, Any]:
        """
        Backtest connection is local and does not require credentials.
        """

        self._connected = True

        return {
            "connected": True,
            "broker": self.broker_name,
            "account_id": str(self.portfolio.account_id),
        }

    async def disconnect(self) -> None:
        self._connected = False

    async def connection_status(self) -> dict[str, Any]:
        return {
            "connected": self._connected,
            "broker": self.broker_name,
            "account_id": str(self.portfolio.account_id),
        }

    # ------------------------------------------------------------------
    # ACCOUNT
    # ------------------------------------------------------------------

    async def get_account(self) -> dict[str, Any]:
        """
        Return the simulated account state.

        Current prices are included when available so equity can be
        marked to market.
        """

        prices = {
            symbol: market.midpoint for symbol, market in self._current_market.items()
        }

        equity = (
            self.portfolio.mark_to_market(
                prices=prices,
                timestamp=self._latest_market_timestamp(),
            )
            if prices
            else self.portfolio.balance
        )

        return {
            "account_id": str(self.portfolio.account_id),
            "broker": self.broker_name,
            "balance": self.portfolio.balance,
            "equity": equity,
            "margin": self.portfolio.margin,
            "free_margin": self.portfolio.free_margin,
            "margin_level": self.portfolio.margin_level,
            "currency": "USD",
        }

    # ------------------------------------------------------------------
    # MARKET DATA
    # ------------------------------------------------------------------

    async def get_symbols(self) -> list[dict[str, Any]]:
        """
        Return symbols currently known to the backtest market.

        Historical data registration is handled by the backtest engine.
        """

        return [
            {
                "symbol": symbol,
                "broker": self.broker_name,
            }
            for symbol in sorted(self._current_market)
        ]

    async def get_symbol(self, symbol: str) -> dict[str, Any]:
        normalized = self._normalize_symbol(symbol)

        market = self._current_market.get(normalized)

        if market is None:
            raise ValueError(f"No backtest market data available for '{symbol}'.")

        return {
            "symbol": normalized,
            "broker": self.broker_name,
            "bid": self._bid(market),
            "ask": self._ask(market),
            "last": market.candle.close,
        }

    async def get_tick(self, symbol: str) -> dict[str, Any]:
        normalized = self._normalize_symbol(symbol)

        market = self._current_market.get(normalized)

        if market is None:
            raise ValueError(f"No backtest market data available for '{symbol}'.")

        return {
            "symbol": normalized,
            "timestamp": market.candle.timestamp,
            "bid": self._bid(market),
            "ask": self._ask(market),
            "last": market.candle.close,
        }

    async def get_candles(
        self,
        symbol: str,
        timeframe: str = "M15",
        count: int = 200,
    ) -> list[dict[str, Any]]:
        """
        Historical candle retrieval belongs to the BacktestDataFeed.

        This adapter only exposes the current candle registered by
        the backtest engine.

        The complete historical dataset will be supplied to the
        BacktestEngine rather than loaded by the broker.
        """

        normalized = self._normalize_symbol(symbol)

        market = self._current_market.get(normalized)

        if market is None:
            return []

        return [
            {
                "symbol": normalized,
                "timeframe": timeframe,
                "timestamp": market.candle.timestamp,
                "open": market.candle.open,
                "high": market.candle.high,
                "low": market.candle.low,
                "close": market.candle.close,
            }
        ]

    # ------------------------------------------------------------------
    # ORDERS
    # ------------------------------------------------------------------

    async def get_orders(self) -> list[dict[str, Any]]:
        """
        Backtest orders are represented by execution results and
        positions.

        Pending-order persistence will be added when the backtest
        broker gains a dedicated pending-order book.
        """

        return []

    async def place_order(
        self,
        order: ExecutionOrder,
    ) -> ExecutionResult:
        self._ensure_connected()

        market = self._get_market(order.symbol)

        context = BacktestExecutionContext(
            strategy_id=None,
            strategy_name=None,
            magic_number=order.magic_number,
        )

        return self.execution.execute(
            order=order,
            market=market,
            context=context,
        )

    async def create_pending_order(
        self,
        order: ExecutionOrder,
    ) -> ExecutionResult:
        """
        Submit a LIMIT/STOP order against the current backtest candle.

        Pending-order lifecycle management will eventually be handled
        by the BacktestEngine so orders can remain active across
        multiple candles.
        """

        self._ensure_connected()

        market = self._get_market(order.symbol)

        context = BacktestExecutionContext(
            strategy_id=None,
            strategy_name=None,
            magic_number=order.magic_number,
        )

        return self.execution.execute(
            order=order,
            market=market,
            context=context,
        )

    # ------------------------------------------------------------------
    # POSITIONS
    # ------------------------------------------------------------------

    async def get_positions(self) -> list[dict[str, Any]]:
        positions: list[dict[str, Any]] = []

        for position in self.portfolio.open_positions:
            market = self._current_market.get(self._normalize_symbol(position.symbol))

            current_price = (
                market.midpoint if market is not None else position.entry_price
            )

            positions.append(
                {
                    "position_id": str(position.position_id),
                    "account_id": str(position.account_id),
                    "symbol": position.symbol,
                    "side": position.side.value,
                    "volume": position.volume,
                    "entry_price": position.entry_price,
                    "current_price": current_price,
                    "stop_loss": position.stop_loss,
                    "take_profit": position.take_profit,
                    "unrealized_pnl": position.unrealized_pnl(
                        current_price=current_price,
                    ),
                    "opened_at": position.opened_at,
                    "strategy_id": position.strategy_id,
                    "strategy_name": position.strategy_name,
                }
            )

        return positions

    async def get_position(
        self,
        position_id: int,
    ) -> dict[str, Any]:
        position = self._find_position_by_broker_id(position_id)

        if position is None:
            raise ValueError(f"Backtest position '{position_id}' was not found.")

        market = self._current_market.get(self._normalize_symbol(position.symbol))

        current_price = market.midpoint if market is not None else position.entry_price

        return {
            "position_id": str(position.position_id),
            "account_id": str(position.account_id),
            "symbol": position.symbol,
            "side": position.side.value,
            "volume": position.volume,
            "entry_price": position.entry_price,
            "current_price": current_price,
            "stop_loss": position.stop_loss,
            "take_profit": position.take_profit,
            "unrealized_pnl": position.unrealized_pnl(
                current_price=current_price,
            ),
            "opened_at": position.opened_at,
            "strategy_id": position.strategy_id,
            "strategy_name": position.strategy_name,
        }

    async def modify_position(
        self,
        position_id: int,
        sl: float | None = None,
        tp: float | None = None,
    ) -> dict[str, Any]:
        position = self._find_position_by_broker_id(position_id)

        if position is None:
            raise ValueError(f"Backtest position '{position_id}' was not found.")

        if sl is not None:
            position.stop_loss = Decimal(str(sl))

        if tp is not None:
            position.take_profit = Decimal(str(tp))

        return {
            "position_id": str(position.position_id),
            "stop_loss": position.stop_loss,
            "take_profit": position.take_profit,
        }

    async def close_position(
        self,
        position_id: int,
    ) -> ExecutionResult:
        position = self._find_position_by_broker_id(position_id)

        if position is None:
            raise ValueError(f"Backtest position '{position_id}' was not found.")

        market = self._get_market(position.symbol)

        return self.execution.close_position(
            position_id=position.position_id,
            market=market,
            exit_reason="MANUAL",
        )

    # ------------------------------------------------------------------
    # HISTORY
    # ------------------------------------------------------------------

    async def get_order_history(
        self,
        start: datetime,
        end: datetime,
    ) -> list[dict[str, Any]]:
        return []

    async def get_deal_history(
        self,
        start: datetime,
        end: datetime,
    ) -> list[dict[str, Any]]:
        return []

    async def get_deals_by_position(
        self,
        position_id: int,
    ) -> list[dict[str, Any]]:
        return []

    # ------------------------------------------------------------------
    # MARKET REGISTRATION
    # ------------------------------------------------------------------

    def update_market(self, market: BacktestMarket) -> None:
        """
        Register the current market candle.

        The BacktestEngine calls this before strategy/risk/execution
        processing for each market event.
        """

        symbol = self._normalize_symbol(market.candle.symbol)

        self._current_market[symbol] = market

    def update_markets(
        self,
        markets: list[BacktestMarket],
    ) -> None:
        for market in markets:
            self.update_market(market)

    def clear_market(self) -> None:
        self._current_market.clear()

    # ------------------------------------------------------------------
    # HELPERS
    # ------------------------------------------------------------------

    def _get_market(self, symbol: str) -> BacktestMarket:
        normalized = self._normalize_symbol(symbol)

        market = self._current_market.get(normalized)

        if market is None:
            raise ValueError(f"No current backtest market for '{symbol}'.")

        return market

    def _find_position_by_broker_id(
        self,
        position_id: int,
    ):
        for position in self.portfolio.positions.values():
            if self._uuid_as_int(position.position_id) == position_id:
                return position

        return None

    def _ensure_connected(self) -> None:
        if not self._connected:
            raise RuntimeError("Backtest broker is not connected.")

    @staticmethod
    def _normalize_symbol(symbol: str) -> str:
        normalized = symbol.strip().upper()

        if not normalized:
            raise ValueError("Symbol cannot be empty.")

        return normalized

    @staticmethod
    def _bid(market: BacktestMarket) -> Decimal:
        if market.bid is not None:
            return market.bid

        return market.candle.close - market.candle.close * Decimal("0")

    @staticmethod
    def _ask(market: BacktestMarket) -> Decimal:
        if market.ask is not None:
            return market.ask

        return market.candle.close

    def _latest_market_timestamp(self) -> datetime | None:
        if not self._current_market:
            return None

        return max(market.candle.timestamp for market in self._current_market.values())

    @staticmethod
    def _uuid_as_int(value: UUID) -> int:
        return value.int % (2**63 - 1)
