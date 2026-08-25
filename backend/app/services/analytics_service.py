from collections import defaultdict
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from app.core.constants import TradeResult
from app.repositories.analytics_repository import (
    AnalyticsRepository,
)
from app.schemas.analytics import (
    AccountPerformanceSummary,
    DailyPnLPoint,
    DirectionComparison,
    DirectionPerformance,
    DrawdownPoint,
    EquityPoint,
    MonthlyPnLPoint,
    ProfitDistributionPoint,
    ProfitDistributionResponse,
    StrategyComparison,
    StrategyPerformance,
    SymbolComparison,
    SymbolPerformance,
    TradeStatistics,
)


class AnalyticsService:
    """
    Business logic layer for live trading analytics.

    All analytics are derived from immutable completed Trade
    records.
    """

    def __init__(
        self,
        repository: AnalyticsRepository,
    ):
        self.repository = repository

    # ==========================================================
    # SHARED CALCULATIONS
    # ==========================================================

    @staticmethod
    def _profit_factor(
        gross_profit: Decimal,
        gross_loss: Decimal,
    ) -> Decimal | None:
        """
        Profit Factor = Gross Profit / Gross Loss.

        If there is no loss, the ratio is undefined and NULL
        is returned.
        """

        if gross_loss <= 0:
            return None

        value = (
            gross_profit
            / gross_loss
        )

        if value == 0:
            return Decimal("0.0000")

        return value.quantize(
            Decimal("0.0001")
        )

    @staticmethod
    def _win_rate(
        winning_trades: int,
        total_trades: int,
    ) -> Decimal:

        if total_trades <= 0:
            return Decimal("0.0000")

        return (
            Decimal(winning_trades)
            / Decimal(total_trades)
            * Decimal("100")
        ).quantize(
            Decimal("0.0001")
        )

    @staticmethod
    def _average(
        values: list[Decimal],
    ) -> Decimal:

        if not values:
            return Decimal("0.00")

        return (
            sum(
                values,
                Decimal("0"),
            )
            / Decimal(len(values))
        ).quantize(
            Decimal("0.01")
        )

    @staticmethod
    def _largest_positive(
        values: list[Decimal],
    ) -> Decimal:

        if not values:
            return Decimal("0.00")

        return max(values).quantize(
            Decimal("0.01")
        )

    @staticmethod
    def _largest_loss(
        values: list[Decimal],
    ) -> Decimal:

        if not values:
            return Decimal("0.00")

        return max(
            (
                abs(value)
                for value in values
            )
        ).quantize(
            Decimal("0.01")
        )

    @staticmethod
    def _expectancy(
        winning_trades: int,
        losing_trades: int,
        total_trades: int,
        average_win: Decimal,
        average_loss: Decimal,
    ) -> Decimal:

        if total_trades <= 0:
            return Decimal("0.0000")

        win_probability = (
            Decimal(winning_trades)
            / Decimal(total_trades)
        )

        loss_probability = (
            Decimal(losing_trades)
            / Decimal(total_trades)
        )

        expectancy = (
            win_probability
            * average_win
        ) - (
            loss_probability
            * average_loss
        )

        return expectancy.quantize(
            Decimal("0.0001")
        )

    @staticmethod
    def _trade_metrics(
        trades,
    ) -> dict:

        total_trades = len(trades)

        winning_trades = sum(
            1
            for trade in trades
            if trade.result == TradeResult.WIN
        )

        losing_trades = sum(
            1
            for trade in trades
            if trade.result == TradeResult.LOSS
        )

        breakeven_trades = sum(
            1
            for trade in trades
            if trade.result == TradeResult.BREAKEVEN
        )

        gross_profit = sum(
            (
                trade.gross_profit
                for trade in trades
                if trade.gross_profit > 0
            ),
            Decimal("0"),
        )

        gross_loss = sum(
            (
                abs(trade.gross_profit)
                for trade in trades
                if trade.gross_profit < 0
            ),
            Decimal("0"),
        )

        net_profit = sum(
            (
                trade.net_profit
                for trade in trades
            ),
            Decimal("0"),
        )

        total_commission = sum(
            (
                trade.commission
                for trade in trades
            ),
            Decimal("0"),
        )

        total_swap = sum(
            (
                trade.swap
                for trade in trades
            ),
            Decimal("0"),
        )

        total_fees = sum(
            (
                trade.fees
                for trade in trades
            ),
            Decimal("0"),
        )

        win_values = [
            trade.net_profit
            for trade in trades
            if trade.net_profit > 0
        ]

        loss_values = [
            trade.net_profit
            for trade in trades
            if trade.net_profit < 0
        ]

        average_win = AnalyticsService._average(
            win_values
        )

        average_loss = AnalyticsService._average(
            [
                abs(value)
                for value in loss_values
            ]
        )

        longest_duration = max(
            (
                trade.duration_seconds
                for trade in trades
            ),
            default=0,
        )

        shortest_duration = min(
            (
                trade.duration_seconds
                for trade in trades
            ),
            default=0,
        )

        average_duration = 0

        if trades:
            average_duration = int(
                sum(
                    trade.duration_seconds
                    for trade in trades
                )
                / len(trades)
            )

        return {
            "total_trades": total_trades,
            "winning_trades": winning_trades,
            "losing_trades": losing_trades,
            "breakeven_trades": breakeven_trades,
            "win_rate": AnalyticsService._win_rate(
                winning_trades,
                total_trades,
            ),
            "gross_profit": gross_profit.quantize(
                Decimal("0.01")
            ),
            "gross_loss": gross_loss.quantize(
                Decimal("0.01")
            ),
            "net_profit": net_profit.quantize(
                Decimal("0.01")
            ),
            "total_commission": total_commission.quantize(
                Decimal("0.01")
            ),
            "total_swap": total_swap.quantize(
                Decimal("0.01")
            ),
            "total_fees": total_fees.quantize(
                Decimal("0.01")
            ),
            "profit_factor": AnalyticsService._profit_factor(
                gross_profit,
                gross_loss,
            ),
            "expectancy": AnalyticsService._expectancy(
                winning_trades,
                losing_trades,
                total_trades,
                average_win,
                average_loss,
            ),
            "average_win": average_win,
            "average_loss": average_loss,
            "largest_win": AnalyticsService._largest_positive(
                win_values
            ),
            "largest_loss": AnalyticsService._largest_loss(
                loss_values
            ),
            "average_trade_duration_seconds": average_duration,
            "longest_trade_duration_seconds": longest_duration,
            "shortest_trade_duration_seconds": shortest_duration,
        }

    # ==========================================================
    # ACCOUNT SUMMARY
    # ==========================================================

    async def get_account_summary(
        self,
        account_id: UUID,
    ) -> AccountPerformanceSummary:

        trades = await self.repository.get_account_trades(
            account_id
        )

        metrics = self._trade_metrics(
            trades
        )

        return AccountPerformanceSummary(
            **metrics
        )

    # ==========================================================
    # EQUITY CURVE
    # ==========================================================

    async def get_account_equity_curve(
        self,
        account_id: UUID,
        start: datetime,
        end: datetime,
        starting_balance: Decimal,
    ) -> list[EquityPoint]:

        trades = (
            await self.repository.get_account_trades_by_period(
                account_id=account_id,
                start=start,
                end=end,
            )
        )

        cumulative_pnl = Decimal("0")
        equity = starting_balance
        peak_equity = starting_balance

        points = []

        for trade in trades:

            trade_profit = trade.net_profit

            cumulative_pnl += trade_profit

            equity = (
                starting_balance
                + cumulative_pnl
            )

            if equity > peak_equity:
                peak_equity = equity

            drawdown = (
                peak_equity
                - equity
            )

            drawdown_percent = Decimal("0")

            if peak_equity > 0:
                drawdown_percent = (
                    drawdown
                    / peak_equity
                    * Decimal("100")
                )

            points.append(
                EquityPoint(
                    trade_id=str(
                        trade.id
                    ),
                    ticket=trade.ticket,
                    closed_at=trade.closed_at,
                    trade_profit=trade_profit.quantize(
                        Decimal("0.01")
                    ),
                    cumulative_pnl=cumulative_pnl.quantize(
                        Decimal("0.01")
                    ),
                    equity=equity.quantize(
                        Decimal("0.01")
                    ),
                    peak_equity=peak_equity.quantize(
                        Decimal("0.01")
                    ),
                    drawdown=drawdown.quantize(
                        Decimal("0.01")
                    ),
                    drawdown_percent=drawdown_percent.quantize(
                        Decimal("0.0001")
                    ),
                )
            )

        return points

    # ==========================================================
    # DAILY P&L
    # ==========================================================

    async def get_daily_pnl(
        self,
        account_id: UUID,
        start: datetime,
        end: datetime,
    ) -> list[DailyPnLPoint]:

        trades = (
            await self.repository.get_account_trades_by_period(
                account_id=account_id,
                start=start,
                end=end,
            )
        )

        daily = defaultdict(
            lambda: {
                "trade_count": 0,
                "gross_profit": Decimal("0"),
                "gross_loss": Decimal("0"),
                "net_profit": Decimal("0"),
            }
        )

        for trade in trades:

            day = trade.closed_at.date()

            daily[day]["trade_count"] += 1

            if trade.gross_profit > 0:
                daily[day]["gross_profit"] += (
                    trade.gross_profit
                )

            elif trade.gross_profit < 0:
                daily[day]["gross_loss"] += abs(
                    trade.gross_profit
                )

            daily[day]["net_profit"] += (
                trade.net_profit
            )

        cumulative_pnl = Decimal("0")
        points = []

        for day in sorted(daily):

            data = daily[day]

            cumulative_pnl += data["net_profit"]

            points.append(
                DailyPnLPoint(
                    date=day,
                    trade_count=data["trade_count"],
                    gross_profit=data[
                        "gross_profit"
                    ].quantize(
                        Decimal("0.01")
                    ),
                    gross_loss=data[
                        "gross_loss"
                    ].quantize(
                        Decimal("0.01")
                    ),
                    net_profit=data[
                        "net_profit"
                    ].quantize(
                        Decimal("0.01")
                    ),
                    cumulative_pnl=cumulative_pnl.quantize(
                        Decimal("0.01")
                    ),
                )
            )

        return points

    # ==========================================================
    # MONTHLY P&L
    # ==========================================================

    async def get_monthly_pnl(
        self,
        account_id: UUID,
        start: datetime,
        end: datetime,
    ) -> list[MonthlyPnLPoint]:

        trades = (
            await self.repository.get_account_trades_by_period(
                account_id=account_id,
                start=start,
                end=end,
            )
        )

        monthly = defaultdict(
            lambda: {
                "trade_count": 0,
                "gross_profit": Decimal("0"),
                "gross_loss": Decimal("0"),
                "net_profit": Decimal("0"),
            }
        )

        for trade in trades:

            month_key = trade.closed_at.strftime(
                "%Y-%m"
            )

            monthly[month_key]["trade_count"] += 1

            if trade.gross_profit > 0:
                monthly[month_key]["gross_profit"] += (
                    trade.gross_profit
                )

            elif trade.gross_profit < 0:
                monthly[month_key]["gross_loss"] += (
                    abs(
                        trade.gross_profit
                    )
                )

            monthly[month_key]["net_profit"] += (
                trade.net_profit
            )

        cumulative_pnl = Decimal("0")
        points = []

        for month in sorted(monthly):

            data = monthly[month]

            cumulative_pnl += data["net_profit"]

            points.append(
                MonthlyPnLPoint(
                    month=month,
                    trade_count=data[
                        "trade_count"
                    ],
                    gross_profit=data[
                        "gross_profit"
                    ].quantize(
                        Decimal("0.01")
                    ),
                    gross_loss=data[
                        "gross_loss"
                    ].quantize(
                        Decimal("0.01")
                    ),
                    net_profit=data[
                        "net_profit"
                    ].quantize(
                        Decimal("0.01")
                    ),
                    cumulative_pnl=cumulative_pnl.quantize(
                        Decimal("0.01")
                    ),
                )
            )

        return points

    # ==========================================================
    # DRAWDOWN
    # ==========================================================

    async def get_drawdown(
        self,
        account_id: UUID,
        start: datetime,
        end: datetime,
        starting_balance: Decimal,
    ) -> list[DrawdownPoint]:

        equity_points = (
            await self.get_account_equity_curve(
                account_id=account_id,
                start=start,
                end=end,
                starting_balance=starting_balance,
            )
        )

        return [
            DrawdownPoint(
                trade_id=point.trade_id,
                ticket=point.ticket,
                closed_at=point.closed_at,
                equity=point.equity,
                peak_equity=point.peak_equity,
                drawdown=point.drawdown,
                drawdown_percent=point.drawdown_percent,
            )
            for point in equity_points
        ]

    # ==========================================================
    # STRATEGY PERFORMANCE
    # ==========================================================

    async def get_strategy_performance(
        self,
        account_id: UUID,
    ) -> list[StrategyPerformance]:

        trades = await self.repository.get_account_trades(
            account_id
        )

        grouped = defaultdict(list)

        for trade in trades:
            grouped[
                trade.strategy
            ].append(trade)

        results = []

        for strategy in sorted(
            grouped
        ):

            metrics = self._trade_metrics(
                grouped[strategy]
            )

            results.append(
                StrategyPerformance(
                    strategy=strategy,
                    **metrics,
                )
            )

        return results

    # ==========================================================
    # SYMBOL PERFORMANCE
    # ==========================================================

    async def get_symbol_performance(
        self,
        account_id: UUID,
    ) -> list[SymbolPerformance]:

        trades = await self.repository.get_account_trades(
            account_id
        )

        grouped = defaultdict(list)

        for trade in trades:

            grouped[
                trade.symbol_id
            ].append(trade)

        results = []

        for symbol_id in sorted(
            grouped,
            key=str,
        ):

            symbol_trades = grouped[
                symbol_id
            ]

            metrics = self._trade_metrics(
                symbol_trades
            )

            # --------------------------------------------------
            # Resolve actual symbol name
            # --------------------------------------------------

            symbol_name = None

            if symbol_trades:

                symbol = getattr(
                    symbol_trades[0],
                    "symbol",
                    None,
                )

                if symbol is not None:

                    symbol_name = (
                        getattr(
                            symbol,
                            "symbol",
                            None,
                        )
                        or getattr(
                            symbol,
                            "name",
                            None,
                        )
                        or getattr(
                            symbol,
                            "code",
                            None,
                        )
                    )

            results.append(
                SymbolPerformance(
                    symbol_id=symbol_id,
                    symbol=symbol_name,
                    **metrics,
                )
            )

        return results

    # ==========================================================
    # DIRECTION PERFORMANCE
    # ==========================================================

    async def get_direction_performance(
        self,
        account_id: UUID,
    ) -> list[DirectionPerformance]:

        trades = await self.repository.get_account_trades(
            account_id
        )

        grouped = defaultdict(list)

        for trade in trades:

            grouped[
                str(trade.direction)
            ].append(trade)

        results = []

        for direction in sorted(
            grouped
        ):

            metrics = self._trade_metrics(
                grouped[direction]
            )

            results.append(
                DirectionPerformance(
                    direction=direction,
                    total_trades=metrics[
                        "total_trades"
                    ],
                    winning_trades=metrics[
                        "winning_trades"
                    ],
                    losing_trades=metrics[
                        "losing_trades"
                    ],
                    breakeven_trades=metrics[
                        "breakeven_trades"
                    ],
                    win_rate=metrics[
                        "win_rate"
                    ],
                    gross_profit=metrics[
                        "gross_profit"
                    ],
                    gross_loss=metrics[
                        "gross_loss"
                    ],
                    net_profit=metrics[
                        "net_profit"
                    ],
                    profit_factor=metrics[
                        "profit_factor"
                    ],
                    expectancy=metrics[
                        "expectancy"
                    ],
                    average_win=metrics[
                        "average_win"
                    ],
                    average_loss=metrics[
                        "average_loss"
                    ],
                    largest_win=metrics[
                        "largest_win"
                    ],
                    largest_loss=metrics[
                        "largest_loss"
                    ],
                )
            )

        return results

    # ==========================================================
    # TRADE STATISTICS
    # ==========================================================

    async def get_trade_statistics(
        self,
        account_id: UUID,
        start: datetime,
        end: datetime,
    ) -> TradeStatistics:

        trades = (
            await self.repository.get_account_trades_by_period(
                account_id=account_id,
                start=start,
                end=end,
            )
        )

        metrics = self._trade_metrics(
            trades
        )

        total_volume = sum(
            (
                trade.volume
                for trade in trades
            ),
            Decimal("0"),
        )

        average_volume = Decimal("0")

        if trades:
            average_volume = (
                total_volume
                / Decimal(len(trades))
            )

        return TradeStatistics(
            total_trades=metrics[
                "total_trades"
            ],
            winning_trades=metrics[
                "winning_trades"
            ],
            losing_trades=metrics[
                "losing_trades"
            ],
            breakeven_trades=metrics[
                "breakeven_trades"
            ],
            average_duration_seconds=metrics[
                "average_trade_duration_seconds"
            ],
            longest_duration_seconds=metrics[
                "longest_trade_duration_seconds"
            ],
            shortest_duration_seconds=metrics[
                "shortest_trade_duration_seconds"
            ],
            average_win=metrics[
                "average_win"
            ],
            average_loss=metrics[
                "average_loss"
            ],
            largest_win=metrics[
                "largest_win"
            ],
            largest_loss=metrics[
                "largest_loss"
            ],
            total_volume=total_volume.quantize(
                Decimal("0.01")
            ),
            average_volume=average_volume.quantize(
                Decimal("0.01")
            ),
        )

    # ==========================================================
    # STRATEGY COMPARISON
    # ==========================================================

    async def get_strategy_comparison(
        self,
        account_id: UUID,
    ) -> list[StrategyComparison]:

        strategy_data = (
            await self.get_strategy_performance(
                account_id
            )
        )

        return [
            StrategyComparison(
                strategy=item.strategy,
                total_trades=item.total_trades,
                win_rate=item.win_rate,
                net_profit=item.net_profit,
                profit_factor=item.profit_factor,
                expectancy=item.expectancy,
            )
            for item in strategy_data
        ]

    # ==========================================================
    # SYMBOL COMPARISON
    # ==========================================================

    async def get_symbol_comparison(
        self,
        account_id: UUID,
    ) -> list[SymbolComparison]:

        symbol_data = (
            await self.get_symbol_performance(
                account_id
            )
        )

        return [
            SymbolComparison(
                symbol_id=item.symbol_id,
                total_trades=item.total_trades,
                win_rate=item.win_rate,
                net_profit=item.net_profit,
                profit_factor=item.profit_factor,
                expectancy=item.expectancy,
            )
            for item in symbol_data
        ]

    # ==========================================================
    # DIRECTION COMPARISON
    # ==========================================================

    async def get_direction_comparison(
        self,
        account_id: UUID,
    ) -> list[DirectionComparison]:

        direction_data = (
            await self.get_direction_performance(
                account_id
            )
        )

        return [
            DirectionComparison(
                direction=item.direction,
                total_trades=item.total_trades,
                win_rate=item.win_rate,
                net_profit=item.net_profit,
                profit_factor=item.profit_factor,
                expectancy=item.expectancy,
            )
            for item in direction_data
        ]

    # ==========================================================
    # PROFIT DISTRIBUTION
    # ==========================================================

    async def get_profit_distribution(
        self,
        account_id: UUID,
        start: datetime,
        end: datetime,
        bucket_size: Decimal = Decimal("10.00"),
    ) -> ProfitDistributionResponse:

        if bucket_size <= 0:
            raise ValueError(
                "bucket_size must be greater than zero"
            )

        trades = (
            await self.repository.get_account_trades_by_period(
                account_id=account_id,
                start=start,
                end=end,
            )
        )

        profitable_trades = sum(
            1
            for trade in trades
            if trade.net_profit > 0
        )

        losing_trades = sum(
            1
            for trade in trades
            if trade.net_profit < 0
        )

        breakeven_trades = sum(
            1
            for trade in trades
            if trade.net_profit == 0
        )

        buckets = defaultdict(int)

        for trade in trades:

            profit = trade.net_profit

            bucket_index = int(
                profit
                // bucket_size
            )

            minimum = (
                Decimal(bucket_index)
                * bucket_size
            )

            maximum = (
                minimum
                + bucket_size
            )

            buckets[
                (
                    minimum,
                    maximum,
                )
            ] += 1

        distribution = []

        for (
            minimum,
            maximum,
        ) in sorted(
            buckets
        ):

            distribution.append(
                ProfitDistributionPoint(
                    minimum=minimum.quantize(
                        Decimal("0.01")
                    ),
                    maximum=maximum.quantize(
                        Decimal("0.01")
                    ),
                    trade_count=buckets[
                        (
                            minimum,
                            maximum,
                        )
                    ],
                )
            )

        return ProfitDistributionResponse(
            total_trades=len(trades),
            profitable_trades=profitable_trades,
            losing_trades=losing_trades,
            breakeven_trades=breakeven_trades,
            buckets=distribution,
        )