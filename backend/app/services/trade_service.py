from uuid import UUID

from app.core.constants import TradeResult
from app.repositories.trade_repository import TradeRepository
from app.schemas.trade import TradeCreate, TradeUpdate


class TradeService:
    def __init__(self, repository: TradeRepository):
        self.repository = repository

    async def create_trade(self, data: TradeCreate):
        existing = await self.repository.get_by_ticket(data.ticket)
        if existing:
            raise ValueError("Trade with this ticket already exists")

        return await self.repository.create(**data.model_dump())

    async def get_trade(self, trade_id: UUID):
        trade = await self.repository.get_by_id(trade_id)
        if not trade:
            raise ValueError("Trade not found")
        return trade

    async def get_trades(self):
        return await self.repository.get_all()

    async def get_account_trades(self, account_id: UUID):
        return await self.repository.get_by_account(account_id)

    async def get_symbol_trades(self, symbol_id: UUID):
        return await self.repository.get_by_symbol(symbol_id)

    async def get_strategy_trades(self, strategy: str):
        return await self.repository.get_by_strategy(strategy)

    async def get_result_trades(self, result_type: TradeResult):
        return await self.repository.get_by_result(result_type)

    async def get_latest_trade(self):
        return await self.repository.get_latest()

    async def update_trade(self, trade_id: UUID, data: TradeUpdate):
        trade = await self.get_trade(trade_id)
        return await self.repository.update(
            trade,
            **data.model_dump(exclude_unset=True),
        )

    async def delete_trade(self, trade_id: UUID):
        trade = await self.get_trade(trade_id)
        raise ValueError("Trades are immutable and cannot be deleted")
