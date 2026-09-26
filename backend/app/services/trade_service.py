from uuid import UUID

from app.core.constants import PositionStatus, TradeResult
from app.repositories.position_repository import PositionRepository
from app.repositories.trade_repository import TradeRepository
from app.schemas.trade import TradeCreate


class TradeService:
    """
    Business logic layer for Trades.

    A Trade represents a completed Position and is immutable
    after creation.
    """

    def __init__(
        self,
        repository: TradeRepository,
        position_repository: PositionRepository,
    ):
        self.repository = repository
        self.position_repository = position_repository

    # ==========================================================
    # CREATE
    # ==========================================================

    async def create_trade(
        self,
        data: TradeCreate,
        commit: bool = True,
    ):
        """
        Create a Trade from a completed Position.
        """

        position = await self.position_repository.get_by_id(data.position_id)

        if not position:
            raise ValueError("Position not found")

        if position.status != PositionStatus.CLOSED:
            raise ValueError("Trade can only be created from a closed position")

        existing_trade = await self.repository.get_by_position(data.position_id)

        if existing_trade:
            raise ValueError("Trade already exists for this position")

        existing_ticket = await self.repository.get_by_ticket(data.ticket)

        if existing_ticket:
            raise ValueError("Trade with this broker ticket already exists")

        if data.closed_at < data.opened_at:
            raise ValueError("closed_at cannot be earlier than opened_at")

        if data.duration_seconds < 0:
            raise ValueError("duration_seconds cannot be negative")

        return await self.repository.create(
            commit=commit,
            **data.model_dump(),
        )

    # ==========================================================
    # READ
    # ==========================================================

    async def get_trade(
        self,
        trade_id: UUID,
        user_id: UUID | None = None,
    ):
        """
        Retrieve a required trade.

        Raises ValueError when the trade does not exist.
        """

        trade = await self.repository.get_by_id(trade_id)

        if not trade:
            raise ValueError("Trade not found")

        if user_id is not None and trade.account.user_id != user_id:
            raise ValueError("Trade not found")

        return trade

    async def get_trades(
        self,
        user_id: UUID | None = None,
    ):
        """Retrieve all trades, optionally filtered by user."""

        trades = await self.repository.get_all()

        if user_id is not None:
            return [trade for trade in trades if trade.account.user_id == user_id]

        return trades

    async def get_account_trades(
        self,
        account_id: UUID,
        user_id: UUID | None = None,
    ):
        """Retrieve trades for an account."""

        trades = await self.repository.get_by_account(account_id)

        return [
            trade
            for trade in trades
            if user_id is None or trade.account.user_id == user_id
        ]

    async def get_symbol_trades(
        self,
        symbol_id: UUID,
        user_id: UUID | None = None,
    ):
        """Retrieve trades for a symbol."""

        trades = await self.repository.get_by_symbol(symbol_id)

        return [
            trade
            for trade in trades
            if user_id is None or trade.account.user_id == user_id
        ]

    async def get_strategy_trades(
        self,
        strategy: str,
        user_id: UUID | None = None,
    ):
        """Retrieve trades for a strategy."""

        trades = await self.repository.get_by_strategy(strategy)

        return [
            trade
            for trade in trades
            if user_id is None or trade.account.user_id == user_id
        ]

    async def get_result_trades(
        self,
        result_type: TradeResult,
        user_id: UUID | None = None,
    ):
        """Retrieve trades for a result type."""

        trades = await self.repository.get_by_result(result_type)

        return [
            trade
            for trade in trades
            if user_id is None or trade.account.user_id == user_id
        ]

    async def get_latest_trade(self):
        """Retrieve the latest trade."""

        return await self.repository.get_latest()

    async def get_trade_by_position(
        self,
        position_id: UUID,
        user_id: UUID | None = None,
    ):
        """
        Retrieve a trade associated with a position.

        This is intentionally an optional lookup.

        Returns:
            Trade instance when one exists.
            None when no trade exists.

        Raises:
            ValueError when a trade exists but belongs to
            another user.
        """

        trade = await self.repository.get_by_position(position_id)

        if trade is None:
            return None

        if user_id is not None and trade.account.user_id != user_id:
            raise ValueError("Trade not found")

        return trade

    # ==========================================================
    # IMMUTABILITY
    # ==========================================================

    async def update_trade(
        self,
        trade_id: UUID,
        *args,
        **kwargs,
    ):
        raise ValueError("Trades are immutable and cannot be updated")

    async def delete_trade(
        self,
        trade_id: UUID,
    ):
        raise ValueError("Trades are immutable and cannot be deleted")
