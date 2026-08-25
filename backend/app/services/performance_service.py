from datetime import datetime
from decimal import Decimal
from uuid import UUID

from app.core.constants import PerformancePeriod, TradeResult
from app.repositories.performance_repository import PerformanceRepository
from app.repositories.trade_repository import TradeRepository
from app.schemas.performance import (
    PerformanceCreate,
    PerformanceUpdate,
)


class PerformanceService:
    """
    Calculates and manages performance snapshots derived from
    completed Trade records.
    """

    def __init__(
        self,
        repository: PerformanceRepository,
        trade_repository: TradeRepository,
    ):
        self.repository = repository
        self.trade_repository = trade_repository

    # ==========================================================
    # CALCULATE PERFORMANCE
    # ==========================================================

    async def calculate_from_trades(
        self,
        trades,
        strategy_run_id: UUID,
        period: PerformancePeriod,
        generated_at: datetime,
        starting_balance: Decimal,
        ending_balance: Decimal,
    ):
        """
        Calculate a Performance snapshot from completed trades.
        """

        total_trades = len(trades)

        winning_trades = sum(1 for trade in trades if trade.result == TradeResult.WIN)

        losing_trades = sum(1 for trade in trades if trade.result == TradeResult.LOSS)

        breakeven_trades = sum(
            1 for trade in trades if trade.result == TradeResult.BREAKEVEN
        )

        # ------------------------------------------------------
        # Profit
        # ------------------------------------------------------

        gross_profit = sum(
            (trade.gross_profit for trade in trades if trade.gross_profit > 0),
            Decimal("0"),
        )

        gross_loss = sum(
            (abs(trade.gross_profit) for trade in trades if trade.gross_profit < 0),
            Decimal("0"),
        )

        net_profit = sum(
            (trade.net_profit for trade in trades),
            Decimal("0"),
        )

        total_commission = sum(
            (trade.commission for trade in trades),
            Decimal("0"),
        )

        total_swap = sum(
            (trade.swap for trade in trades),
            Decimal("0"),
        )

        total_fees = sum(
            (trade.fees for trade in trades),
            Decimal("0"),
        )

        # ------------------------------------------------------
        # Win rate
        # ------------------------------------------------------

        win_rate = Decimal("0")

        if total_trades > 0:
            win_rate = (Decimal(winning_trades) / Decimal(total_trades)) * Decimal(
                "100"
            )

        # ------------------------------------------------------
        # Profit factor
        # ------------------------------------------------------
        profit_factor: Decimal | None = None

        if gross_loss > 0:
            profit_factor = self._calculate_profit_factor(
                gross_profit,
                gross_loss,
            )
        elif gross_profit == 0:
            profit_factor = None

        # ------------------------------------------------------
        # Average win
        # ------------------------------------------------------

        winning_profits = [trade.net_profit for trade in trades if trade.net_profit > 0]

        average_win = Decimal("0")

        if winning_profits:
            average_win = sum(
                winning_profits,
                Decimal("0"),
            ) / Decimal(len(winning_profits))

        # ------------------------------------------------------
        # Average loss
        # ------------------------------------------------------

        losing_profits = [
            abs(trade.net_profit) for trade in trades if trade.net_profit < 0
        ]

        average_loss = Decimal("0")

        if losing_profits:
            average_loss = sum(
                losing_profits,
                Decimal("0"),
            ) / Decimal(len(losing_profits))

        # ------------------------------------------------------
        # Payoff ratio
        # ------------------------------------------------------

        payoff_ratio = None

        if average_loss > 0:
            payoff_ratio = average_win / average_loss

        # ------------------------------------------------------
        # Expectancy
        # ------------------------------------------------------

        expectancy = Decimal("0")

        if total_trades > 0:

            win_probability = Decimal(winning_trades) / Decimal(total_trades)

            loss_probability = Decimal(losing_trades) / Decimal(total_trades)

            expectancy = (win_probability * average_win) - (
                loss_probability * average_loss
            )

        # ------------------------------------------------------
        # Largest win / loss
        # ------------------------------------------------------

        largest_win = max(
            (trade.net_profit for trade in trades if trade.net_profit > 0),
            default=Decimal("0"),
        )

        largest_loss = max(
            (abs(trade.net_profit) for trade in trades if trade.net_profit < 0),
            default=Decimal("0"),
        )

        # ------------------------------------------------------
        # Average duration
        # ------------------------------------------------------

        average_duration = 0

        if trades:
            average_duration = int(
                sum(trade.duration_seconds for trade in trades) / len(trades)
            )

        # ------------------------------------------------------
        # Drawdown
        # ------------------------------------------------------

        max_drawdown = Decimal("0")
        peak_equity = starting_balance
        current_equity = starting_balance
        lowest_equity = starting_balance

        for trade in trades:

            current_equity += trade.net_profit

            if current_equity > peak_equity:
                peak_equity = current_equity

            if current_equity < lowest_equity:
                lowest_equity = current_equity

            drawdown = peak_equity - current_equity

            if drawdown > max_drawdown:
                max_drawdown = drawdown

        max_drawdown_percent = Decimal("0")

        if peak_equity > 0:
            max_drawdown_percent = (max_drawdown / peak_equity) * Decimal("100")

        # ------------------------------------------------------
        # Recovery factor
        # ------------------------------------------------------

        recovery_factor = None

        if max_drawdown > 0:
            recovery_factor = net_profit / max_drawdown

        # ------------------------------------------------------
        # Build snapshot
        # ------------------------------------------------------

        return PerformanceCreate(
            strategy_run_id=strategy_run_id,
            period=period,
            generated_at=generated_at,
            total_trades=total_trades,
            winning_trades=winning_trades,
            losing_trades=losing_trades,
            breakeven_trades=breakeven_trades,
            gross_profit=gross_profit,
            gross_loss=gross_loss,
            net_profit=net_profit,
            total_commission=total_commission,
            total_swap=total_swap,
            total_fees=total_fees,
            win_rate=win_rate,
            profit_factor=profit_factor,
            expectancy=expectancy,
            sharpe_ratio=None,
            sortino_ratio=None,
            calmar_ratio=None,
            max_drawdown=max_drawdown,
            max_drawdown_percent=max_drawdown_percent,
            average_r_multiple=None,
            recovery_factor=recovery_factor,
            payoff_ratio=payoff_ratio,
            average_trade_duration_seconds=average_duration,
            average_win=average_win,
            average_loss=average_loss,
            largest_win=largest_win,
            largest_loss=largest_loss,
            starting_balance=starting_balance,
            ending_balance=ending_balance,
            peak_equity=peak_equity,
            lowest_equity=lowest_equity,
        )

    # ==========================================================
    # GENERATE ACCOUNT PERFORMANCE
    # ==========================================================

    async def generate_account_performance(
        self,
        account_id: UUID,
        strategy_run_id: UUID,
        period: PerformancePeriod,
        start: datetime,
        end: datetime,
        generated_at: datetime,
        starting_balance: Decimal,
        ending_balance: Decimal,
    ):

        trades = await self.trade_repository.get_by_account_and_period(
            account_id,
            start,
            end,
        )

        data = await self.calculate_from_trades(
            trades=trades,
            strategy_run_id=strategy_run_id,
            period=period,
            generated_at=generated_at,
            starting_balance=starting_balance,
            ending_balance=ending_balance,
        )

        existing = await self.repository.get_by_strategy_run(strategy_run_id)

        if existing:
            return await self.repository.update(
                existing,
                **data.model_dump(
                    exclude={
                        "strategy_run_id",
                    }
                ),
            )

        return await self.repository.create(**data.model_dump())

    # ==========================================================
    # EXISTING CRUD / READ METHODS
    # ==========================================================

    async def create_performance(
        self,
        data: PerformanceCreate,
    ):

        existing = await self.repository.get_by_strategy_run(data.strategy_run_id)

        if existing:
            raise ValueError("Performance already exists for this strategy run")

        return await self.repository.create(**data.model_dump())

    async def get_performance(
        self,
        performance_id: UUID,
    ):

        performance = await self.repository.get_by_id(performance_id)

        if not performance:
            raise ValueError("Performance record not found")

        return performance

    async def get_strategy_performance(
        self,
        strategy_run_id: UUID,
    ):

        return await self.repository.get_by_strategy_run(strategy_run_id)

    async def get_all_performance(self):

        return await self.repository.get_all()

    async def get_by_period(
        self,
        period: PerformancePeriod,
    ):

        return await self.repository.get_by_period(period)

    async def get_latest(self):

        return await self.repository.get_latest()

    async def update_performance(
        self,
        performance_id: UUID,
        data: PerformanceUpdate,
    ):

        performance = await self.get_performance(performance_id)

        return await self.repository.update(
            performance,
            **data.model_dump(exclude_unset=True),
        )

    async def delete_performance(
        self,
        performance_id: UUID,
    ):

        performance = await self.get_performance(performance_id)

        await self.repository.delete(performance)

    @staticmethod
    def _calculate_profit_factor(
        gross_profit: Decimal,
        gross_loss: Decimal,
    ) -> Decimal | None:

        if gross_loss > 0:
            return gross_profit / gross_loss

        if gross_profit == 0:
            return None

        return None
