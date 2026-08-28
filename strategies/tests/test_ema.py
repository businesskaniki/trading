from datetime import datetime, timedelta, timezone
from decimal import Decimal

from strategies.core.context import (
    StrategyConfig,
    StrategyContext,
)
from strategies.core.enums import (
    PriceSource,
    StrategyCategory,
    StrategyExecutionMode,
    Timeframe,
)
from strategies.core.market_data import (
    Candle,
    MarketData,
)
from strategies.core.signal import Signal
from strategies.setups.trend.ema import (
    EMATrendStrategy,
)


# ----------------------------------------------------------------------
# Test helpers
# ----------------------------------------------------------------------


def create_candle(
    timestamp: datetime,
    price: str,
) -> Candle:
    """
    Create a synthetic candle with realistic internal volatility.
    """

    value = Decimal(price)

    return Candle(
        timestamp=timestamp,
        open=value,
        high=value + Decimal("0.00005"),
        low=value - Decimal("0.00005"),
        close=value,
        volume=Decimal("100"),
        tick_volume=100,
        spread=Decimal("0.00001"),
    )


def create_context(
    prices: list[str],
    *,
    parameters: dict | None = None,
) -> StrategyContext:
    """
    Build a StrategyContext for testing.
    """

    start = datetime(
        2026,
        1,
        1,
        tzinfo=timezone.utc,
    )

    candles = [
        create_candle(
            start + timedelta(minutes=15 * index),
            price,
        )
        for index, price in enumerate(prices)
    ]

    market_data = MarketData(
        symbol="EURUSD",
        timeframe=Timeframe.M15,
        source=PriceSource.HISTORICAL,
        candles=candles,
        received_at=start,
    )

    strategy_config = StrategyConfig(
        strategy_id="ema_trend",
        name="EMA Trend Following",
        category=StrategyCategory.TREND,
        timeframe=Timeframe.M15,
        parameters=parameters or {
            "fast_period": 9,
            "slow_period": 21,
            "atr_period": 14,
            "atr_multiplier": "1.5",
            "risk_reward": "2.0",
            "min_ema_separation": "0.0001",
        },
        enabled=True,
    )

    return StrategyContext(
        timestamp=candles[-1].timestamp,
        execution_mode=StrategyExecutionMode.BACKTEST,
        strategy=strategy_config,
        market_data=market_data,
    )


# ----------------------------------------------------------------------
# Tests
# ----------------------------------------------------------------------


def test_ema_strategy_returns_none_without_setup():
    """
    A flat/ranging market should not generate a signal.
    """

    prices = [
        "1.10000",
        "1.10002",
        "1.10001",
        "1.10003",
        "1.10000",
        "1.10002",
        "1.10001",
        "1.10003",
    ] * 8

    context = create_context(prices)

    strategy = EMATrendStrategy()

    signal = strategy.evaluate(context)

    assert signal is None


def test_ema_strategy_has_correct_metadata():
    """
    Verify strategy identity and configuration metadata.
    """

    strategy = EMATrendStrategy()

    metadata = strategy.metadata()

    assert metadata["strategy_id"] == "ema_trend"

    assert metadata["name"] == "EMA Trend Following"

    assert metadata["category"] == "TREND"

    assert metadata["timeframe"] == "M15"

    assert metadata["minimum_candles"] == 50


def test_ema_strategy_can_generate_bullish_signal():
    """
    A clear bearish-to-bullish transition should produce BUY.
    """

    prices = [
        # Initial downtrend
        "1.1100",
        "1.1095",
        "1.1090",
        "1.1085",
        "1.1080",
        "1.1075",
        "1.1070",
        "1.1065",
        "1.1060",
        "1.1055",
        "1.1050",
        "1.1045",
        "1.1040",
        "1.1035",
        "1.1030",
        "1.1025",
        "1.1020",
        "1.1015",
        "1.1010",
        "1.1005",
        "1.1000",

        # Strong bullish transition
        "1.1010",
        "1.1020",
        "1.1030",
        "1.1040",
        "1.1050",
        "1.1060",
        "1.1070",
        "1.1080",
        "1.1090",
        "1.1100",
        "1.1110",
        "1.1120",
        "1.1130",
        "1.1140",
        "1.1150",
        "1.1160",
        "1.1170",
        "1.1180",
        "1.1190",
        "1.1200",
        "1.1210",
        "1.1220",
        "1.1230",
        "1.1240",
        "1.1250",
        "1.1260",
        "1.1270",
        "1.1280",
        "1.1290",
        "1.1300",
    ]

    context = create_context(prices)

    strategy = EMATrendStrategy()

    signal = strategy.evaluate(context)

    assert signal is not None

    assert isinstance(signal, Signal)

    assert signal.strategy_id == "ema_trend"

    assert signal.symbol == "EURUSD"

    assert signal.timeframe == Timeframe.M15

    assert signal.direction.value == "BUY"

    assert signal.entry_price == Decimal("1.1300")

    assert signal.stop_loss < signal.entry_price

    assert signal.take_profit > signal.entry_price


def test_ema_strategy_can_generate_bearish_signal():
    """
    A clear bullish-to-bearish transition should produce SELL.
    """

    prices = [
        # Initial uptrend
        "1.0900",
        "1.0905",
        "1.0910",
        "1.0915",
        "1.0920",
        "1.0925",
        "1.0930",
        "1.0935",
        "1.0940",
        "1.0945",
        "1.0950",
        "1.0955",
        "1.0960",
        "1.0965",
        "1.0970",
        "1.0975",
        "1.0980",
        "1.0985",
        "1.0990",
        "1.0995",
        "1.1000",

        # Strong bearish transition
        "1.0990",
        "1.0980",
        "1.0970",
        "1.0960",
        "1.0950",
        "1.0940",
        "1.0930",
        "1.0920",
        "1.0910",
        "1.0900",
        "1.0890",
        "1.0880",
        "1.0870",
        "1.0860",
        "1.0850",
        "1.0840",
        "1.0830",
        "1.0820",
        "1.0810",
        "1.0800",
        "1.0790",
        "1.0780",
        "1.0770",
        "1.0760",
        "1.0750",
        "1.0740",
        "1.0730",
        "1.0720",
        "1.0710",
        "1.0700",
    ]

    context = create_context(prices)

    strategy = EMATrendStrategy()

    signal = strategy.evaluate(context)

    assert signal is not None

    assert isinstance(signal, Signal)

    assert signal.strategy_id == "ema_trend"

    assert signal.symbol == "EURUSD"

    assert signal.timeframe == Timeframe.M15

    assert signal.direction.value == "SELL"

    assert signal.entry_price == Decimal("1.0700")

    assert signal.stop_loss > signal.entry_price

    assert signal.take_profit < signal.entry_price


def test_ema_strategy_disabled_returns_none():
    """
    A disabled strategy must never generate a signal.
    """

    prices = [
        "1.1000",
        "1.1001",
        "1.1002",
        "1.1003",
        "1.1004",
        "1.1005",
    ] * 10

    context = create_context(prices)

    disabled_config = context.strategy.model_copy(
        update={
            "enabled": False,
        }
    )

    disabled_context = context.model_copy(
        update={
            "strategy": disabled_config,
        }
    )

    strategy = EMATrendStrategy()

    signal = strategy.evaluate(disabled_context)

    assert signal is None