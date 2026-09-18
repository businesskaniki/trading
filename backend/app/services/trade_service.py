from uuid import UUID

from app.core.constants import PositionStatus, TradeResult
from app.repositories.trade_repository import TradeRepository
from app.repositories.position_repository import PositionRepository
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

        # ------------------------------------------------------
        # Verify Position exists
        # ------------------------------------------------------

        position = await self.position_repository.get_by_id(data.position_id)

        if not position:
            raise ValueError("Position not found")

        # ------------------------------------------------------
        # Position must be closed
        # ------------------------------------------------------

        if position.status != PositionStatus.CLOSED:
            raise ValueError("Trade can only be created from a closed position")

        # ------------------------------------------------------
        # Prevent duplicate trade for position
        # ------------------------------------------------------

        existing_trade = await self.repository.get_by_position(data.position_id)

        if existing_trade:
            raise ValueError("Trade already exists for this position")

        # ------------------------------------------------------
        # Prevent duplicate broker ticket
        # ------------------------------------------------------

        existing_ticket = await self.repository.get_by_ticket(data.ticket)

        if existing_ticket:
            raise ValueError("Trade with this broker ticket already exists")

        # ------------------------------------------------------
        # Validate close time
        # ------------------------------------------------------

        if data.closed_at < data.opened_at:
            raise ValueError("closed_at cannot be earlier than opened_at")

        # ------------------------------------------------------
        # Validate duration
        # ------------------------------------------------------

        if data.duration_seconds < 0:
            raise ValueError("duration_seconds cannot be negative")

        # ------------------------------------------------------
        # Create immutable trade
        # ------------------------------------------------------

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
        trade = await self.repository.get_by_id(trade_id)

        if not trade:
            raise ValueError("Trade not found")

        if user_id is not None and trade.account.user_id != user_id:
            raise ValueError("Trade not found")

        return trade

    # ----------------------------------------------------------
    # ALL TRADES
    # ----------------------------------------------------------

    async def get_trades(self, user_id: UUID | None = None):

        trades = await self.repository.get_all()
        if user_id is not None:
            return [trade for trade in trades if trade.account.user_id == user_id]
        return trades

    # ----------------------------------------------------------
    # ACCOUNT
    # ----------------------------------------------------------

    async def get_account_trades(
        self,
        account_id: UUID,
        user_id: UUID | None = None,
    ):

        trades = await self.repository.get_by_account(account_id)
        return [trade for trade in trades if user_id is None or trade.account.user_id == user_id]

    # ----------------------------------------------------------
    # SYMBOL
    # ----------------------------------------------------------

    async def get_symbol_trades(
        self,
        symbol_id: UUID,
        user_id: UUID | None = None,
    ):

        trades = await self.repository.get_by_symbol(symbol_id)
        return [trade for trade in trades if user_id is None or trade.account.user_id == user_id]

    # ----------------------------------------------------------
    # STRATEGY
    # ----------------------------------------------------------

    async def get_strategy_trades(
        self,
        strategy: str,
        user_id: UUID | None = None,
    ):

        trades = await self.repository.get_by_strategy(strategy)
        return [trade for trade in trades if user_id is None or trade.account.user_id == user_id]

    # ----------------------------------------------------------
    # RESULT
    # ----------------------------------------------------------

    async def get_result_trades(
        self,
        result_type: TradeResult,
        user_id: UUID | None = None,
    ):

        trades = await self.repository.get_by_result(result_type)
        return [trade for trade in trades if user_id is None or trade.account.user_id == user_id]

    # ----------------------------------------------------------
    # LATEST
    # ----------------------------------------------------------

    async def get_latest_trade(self):

        return await self.repository.get_latest()

    # ----------------------------------------------------------
    # BY POSITION
    # ----------------------------------------------------------

    async def get_trade_by_position(
        self,
        position_id: UUID,
        user_id: UUID | None = None,
    ):

        trade = await self.repository.get_by_position(position_id)

        if not trade:
            raise ValueError("Trade not found")

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
