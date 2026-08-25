from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field


# ==========================================================
# ACCOUNT PERFORMANCE SUMMARY
# ==========================================================

class AccountPerformanceSummary(BaseModel):
    """
    Live performance summary calculated from completed Trades.
    """

    total_trades: int

    winning_trades: int

    losing_trades: int

    breakeven_trades: int

    win_rate: Decimal

    gross_profit: Decimal

    gross_loss: Decimal

    net_profit: Decimal

    total_commission: Decimal

    total_swap: Decimal

    total_fees: Decimal

    profit_factor: Decimal | None

    expectancy: Decimal

    average_win: Decimal

    average_loss: Decimal

    largest_win: Decimal

    largest_loss: Decimal

    average_trade_duration_seconds: int

    longest_trade_duration_seconds: int

    shortest_trade_duration_seconds: int


# ==========================================================
# COMMON DATE RANGE REQUEST
# ==========================================================

class AnalyticsDateRangeRequest(BaseModel):
    """
    Generic date-range request for analytics endpoints.
    """

    account_id: UUID

    start: datetime

    end: datetime


# ==========================================================
# EQUITY CURVE REQUEST
# ==========================================================

class EquityCurveRequest(BaseModel):
    """
    Request used to generate an account equity curve.
    """

    account_id: UUID

    start: datetime

    end: datetime

    starting_balance: Decimal = Field(
        ...,
        ge=0,
    )


# ==========================================================
# EQUITY CURVE POINT
# ==========================================================

class EquityPoint(BaseModel):
    """
    One point in the account equity/P&L time series.
    """

    trade_id: str

    ticket: int

    closed_at: datetime

    trade_profit: Decimal

    cumulative_pnl: Decimal

    equity: Decimal

    peak_equity: Decimal

    drawdown: Decimal

    drawdown_percent: Decimal


# ==========================================================
# DAILY P&L REQUEST
# ==========================================================

class DailyPnLRequest(BaseModel):
    """
    Request used to generate daily P&L analytics.
    """

    account_id: UUID

    start: datetime

    end: datetime


# ==========================================================
# DAILY P&L POINT
# ==========================================================

class DailyPnLPoint(BaseModel):
    """
    Aggregated P&L for one calendar day.
    """

    date: date

    trade_count: int

    gross_profit: Decimal

    gross_loss: Decimal

    net_profit: Decimal

    cumulative_pnl: Decimal


# ==========================================================
# MONTHLY P&L REQUEST
# ==========================================================

class MonthlyPnLRequest(BaseModel):
    """
    Request used to generate monthly P&L analytics.
    """

    account_id: UUID

    start: datetime

    end: datetime


# ==========================================================
# MONTHLY P&L POINT
# ==========================================================

class MonthlyPnLPoint(BaseModel):
    """
    Aggregated P&L for one calendar month.
    """

    month: str

    trade_count: int

    gross_profit: Decimal

    gross_loss: Decimal

    net_profit: Decimal

    cumulative_pnl: Decimal


# ==========================================================
# DRAWDOWN REQUEST
# ==========================================================

class DrawdownRequest(BaseModel):
    """
    Request used to generate drawdown analytics.
    """

    account_id: UUID

    start: datetime

    end: datetime

    starting_balance: Decimal = Field(
        ...,
        ge=0,
    )


# ==========================================================
# DRAWDOWN POINT
# ==========================================================

class DrawdownPoint(BaseModel):
    """
    One point in the account drawdown series.
    """

    trade_id: str

    ticket: int

    closed_at: datetime

    equity: Decimal

    peak_equity: Decimal

    drawdown: Decimal

    drawdown_percent: Decimal


# ==========================================================
# STRATEGY PERFORMANCE
# ==========================================================

class StrategyPerformance(BaseModel):
    """
    Performance metrics for a single trading strategy.
    """

    strategy: str

    total_trades: int

    winning_trades: int

    losing_trades: int

    breakeven_trades: int

    win_rate: Decimal

    gross_profit: Decimal

    gross_loss: Decimal

    net_profit: Decimal

    total_commission: Decimal

    total_swap: Decimal

    total_fees: Decimal

    profit_factor: Decimal | None

    expectancy: Decimal

    average_win: Decimal

    average_loss: Decimal

    largest_win: Decimal

    largest_loss: Decimal

    average_trade_duration_seconds: int

    longest_trade_duration_seconds: int

    shortest_trade_duration_seconds: int


# ==========================================================
# SYMBOL PERFORMANCE
# ==========================================================

class SymbolPerformance(BaseModel):
    symbol_id: UUID
    symbol: str | None = None

    total_trades: int
    winning_trades: int
    losing_trades: int
    breakeven_trades: int

    win_rate: Decimal

    gross_profit: Decimal
    gross_loss: Decimal
    net_profit: Decimal

    total_commission: Decimal
    total_swap: Decimal
    total_fees: Decimal

    profit_factor: Decimal | None
    expectancy: Decimal

    average_win: Decimal
    average_loss: Decimal

    largest_win: Decimal
    largest_loss: Decimal

    average_trade_duration_seconds: int
    longest_trade_duration_seconds: int
    shortest_trade_duration_seconds: int

    
# ==========================================================
# DIRECTION PERFORMANCE
# ==========================================================

class DirectionPerformance(BaseModel):
    """
    Performance metrics split by trade direction.
    """

    direction: str

    total_trades: int

    winning_trades: int

    losing_trades: int

    breakeven_trades: int

    win_rate: Decimal

    gross_profit: Decimal

    gross_loss: Decimal

    net_profit: Decimal

    profit_factor: Decimal | None

    expectancy: Decimal

    average_win: Decimal

    average_loss: Decimal

    largest_win: Decimal

    largest_loss: Decimal


# ==========================================================
# TRADE STATISTICS REQUEST
# ==========================================================

class TradeStatisticsRequest(BaseModel):
    """
    Request used to generate aggregate trade statistics.
    """

    account_id: UUID

    start: datetime

    end: datetime


# ==========================================================
# TRADE STATISTICS
# ==========================================================

class TradeStatistics(BaseModel):
    """
    Aggregate statistics describing trade behavior.
    """

    total_trades: int

    winning_trades: int

    losing_trades: int

    breakeven_trades: int

    average_duration_seconds: int

    longest_duration_seconds: int

    shortest_duration_seconds: int

    average_win: Decimal

    average_loss: Decimal

    largest_win: Decimal

    largest_loss: Decimal

    total_volume: Decimal

    average_volume: Decimal


# ==========================================================
# STRATEGY COMPARISON
# ==========================================================

class StrategyComparison(BaseModel):
    """
    Compact strategy ranking/comparison.
    """

    strategy: str

    total_trades: int

    win_rate: Decimal

    net_profit: Decimal

    profit_factor: Decimal | None

    expectancy: Decimal


# ==========================================================
# SYMBOL COMPARISON
# ==========================================================

class SymbolComparison(BaseModel):
    """
    Compact symbol ranking/comparison.
    """

    symbol_id: UUID

    total_trades: int

    win_rate: Decimal

    net_profit: Decimal

    profit_factor: Decimal | None

    expectancy: Decimal


# ==========================================================
# PERFORMANCE DISTRIBUTION
# ==========================================================

class ProfitDistributionPoint(BaseModel):
    """
    Distribution bucket for realized trade P&L.
    """

    minimum: Decimal

    maximum: Decimal

    trade_count: int


class ProfitDistributionResponse(BaseModel):
    """
    Realized P&L distribution.
    """

    total_trades: int

    profitable_trades: int

    losing_trades: int

    breakeven_trades: int

    buckets: list[ProfitDistributionPoint]


# ==========================================================
# DIRECTION COMPARISON
# ==========================================================

class DirectionComparison(BaseModel):
    """
    Compact comparison by BUY/SELL direction.
    """

    direction: str

    total_trades: int

    win_rate: Decimal

    net_profit: Decimal

    profit_factor: Decimal | None

    expectancy: Decimal