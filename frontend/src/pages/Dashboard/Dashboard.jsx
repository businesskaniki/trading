import { useEffect, useMemo, useState } from "react";
import { useDispatch, useSelector } from "react-redux";

import {
    FaWallet,
    FaChartLine,
    FaExchangeAlt,
    FaPercentage,
    FaSyncAlt,
    FaShieldAlt,
    FaArrowUp,
    FaArrowDown,
    FaPlay,
    FaStop,
} from "react-icons/fa";

import { loadDashboard } from "../../redux/dashboard/dashboardThunks";
import { fetchBotStatus, startBot, stopBot } from "../../redux/dashboard/botThunks";
import { openTickStream } from "../../api/tickStream";

import "../../css/dashboard.css";

const Dashboard = () => {
    const dispatch = useDispatch();

    const {
        accounts,
        positions,
        trades,
        symbols,
        loading,
        error,
        brokerAccount,
        lastUpdated,
    } = useSelector(
        (state) => state.dashboard
    );
    const bot = useSelector((state) => state.bot);
    const [liveTicks, setLiveTicks] = useState({});

    useEffect(() => {
        dispatch(loadDashboard());
        dispatch(fetchBotStatus());
    }, [dispatch]);

    useEffect(() => {
        const sockets = symbols
            .map((symbol) => symbol.name || symbol.symbol)
            .filter(Boolean)
            .map((symbol) => openTickStream(
                symbol,
                (payload) => setLiveTicks((current) => ({
                    ...current,
                    [symbol]: payload.tick,
                })),
                () => undefined,
            ));

        return () => sockets.forEach((socket) => socket.close());
    }, [symbols]);

    useEffect(() => {
        const refresh = window.setInterval(() => dispatch(loadDashboard()), 30000);
        return () => window.clearInterval(refresh);
    }, [dispatch]);

    // --------------------------------------------------
    // Refresh
    // --------------------------------------------------

    const handleRefresh = () => {
        dispatch(loadDashboard());
    };

    const handleStartBot = () => {
        dispatch(startBot({
            strategy_name: "ema_cross",
            strategy_version: "1.0.0",
            symbols: ["EURUSD"],
            timeframe: "M1",
            risk_percent: 1,
        }));
    };

    const handleStopBot = () => {
        dispatch(stopBot());
    };

    // --------------------------------------------------
    // Helpers
    // --------------------------------------------------

    const formatMoney = (value) => {
        const number = Number(value);

        if (!Number.isFinite(number)) {
            return "$0.00";
        }

        return new Intl.NumberFormat("en-US", {
            style: "currency",
            currency: "USD",
            maximumFractionDigits: 2,
        }).format(number);
    };

    const formatNumber = (value) => {
        const number = Number(value);

        if (!Number.isFinite(number)) {
            return "0";
        }

        return new Intl.NumberFormat("en-US", {
            maximumFractionDigits: 2,
        }).format(number);
    };

    // --------------------------------------------------
    // Account statistics
    // --------------------------------------------------

    const totalBalance = accounts.reduce(
        (sum, account) =>
            sum + Number(account.balance || 0),
        0
    );

    const totalEquity = accounts.reduce(
        (sum, account) =>
            sum + Number(account.equity || 0),
        0
    );

    const symbolById = useMemo(
        () => Object.fromEntries(symbols.map((symbol) => [symbol.id, symbol.name || symbol.symbol])),
        [symbols],
    );

    const livePositions = positions.map((position) => {
        const symbol = symbolById[position.symbol_id];
        const tick = symbol ? liveTicks[symbol] : null;
        const currentPrice = Number(
            position.direction === "SELL"
                ? tick?.ask || tick?.last || position.current_price
                : tick?.bid || tick?.last || position.current_price,
        );
        const entryPrice = Number(position.entry_price || 0);
        const volume = Number(position.current_volume || position.volume || 0);
        const direction = position.direction === "BUY" ? 1 : -1;
        const liveProfit = (currentPrice - entryPrice) * volume * direction;

        return {
            ...position,
            liveCurrentPrice: currentPrice,
            liveFloatingProfit: tick ? liveProfit : Number(position.floating_profit || 0),
        };
    });

    const floatingProfit = livePositions.reduce(
        (sum, position) => sum + position.liveFloatingProfit,
        0,
    );

    const openPositions = livePositions.filter(
        (position) =>
            position.status === "OPEN"
    );

    // --------------------------------------------------
    // Trades
    // --------------------------------------------------

    const winningTrades = trades.filter(
        (trade) =>
            trade.result === "WIN"
    ).length;

    const winRate =
        trades.length > 0
            ? (winningTrades / trades.length) * 100
            : 0;

    return (
        <main className="dashboard">

            {/* ==========================================
                HEADER
            ========================================== */}

            <section className="dashboard-header">

                <div>
                    <span className="dashboard-eyebrow">
                        ATHENA QUANT ENGINE
                    </span>

                    <h1>
                        Trading Dashboard
                    </h1>

                    <p>
                        Monitor your trading infrastructure,
                        accounts, positions and performance.
                    </p>
                </div>

                <button
                    className="dashboard-refresh"
                    onClick={handleRefresh}
                    disabled={loading}
                >
                    <FaSyncAlt
                        className={
                            loading
                                ? "spin"
                                : ""
                        }
                    />

                    {loading
                        ? "Refreshing..."
                        : "Refresh"}
                </button>

            </section>

            <section className="bot-control">
                <div>
                    <span className="dashboard-eyebrow">AUTOMATION</span>
                    <h2>Paper trading bot</h2>
                    <p>
                        {bot.status?.active
                            ? `${bot.status.strategy_name} is running at ${bot.status.risk_percent}% risk.`
                            : "Stopped. Start only after reviewing the configured risk."}
                    </p>
                </div>
                <div className="bot-control__actions">
                    <span className={bot.status?.active ? "bot-status bot-status--active" : "bot-status"}>
                        {bot.status?.active ? "RUNNING" : "STOPPED"}
                    </span>
                    {bot.status?.active ? (
                        <button className="bot-button bot-button--stop" onClick={handleStopBot} disabled={bot.loading}>
                            <FaStop /> Stop bot
                        </button>
                    ) : (
                        <button className="bot-button bot-button--start" onClick={handleStartBot} disabled={bot.loading}>
                            <FaPlay /> Start paper bot
                        </button>
                    )}
                </div>
            </section>

            {bot.error && <div className="dashboard-error">{bot.error}</div>}


            {/* ==========================================
                ERROR
            ========================================== */}

            {error && (
                <div className="dashboard-error">
                    {typeof error === "string"
                        ? error
                        : JSON.stringify(error)}
                </div>
            )}


            {/* ==========================================
                STAT CARDS
            ========================================== */}

            <section className="dashboard-stats">

                <div className="stat-card">

                    <div className="stat-icon">
                        <FaWallet />
                    </div>

                    <div>
                        <span>
                            Total Balance
                        </span>

                        <strong>
                            {formatMoney(
                                totalBalance
                            )}
                        </strong>
                    </div>

                </div>


                <div className="stat-card">

                    <div className="stat-icon">
                        <FaChartLine />
                    </div>

                    <div>
                        <span>
                            Total Equity
                        </span>

                        <strong>
                            {formatMoney(
                                totalEquity
                            )}
                        </strong>
                    </div>

                </div>


                <div className="stat-card">

                    <div className="stat-icon">
                        <FaExchangeAlt />
                    </div>

                    <div>
                        <span>
                            Live Floating P&L
                        </span>

                        <strong
                            className={
                                floatingProfit >= 0
                                    ? "positive"
                                    : "negative"
                            }
                        >
                            {formatMoney(floatingProfit)}
                        </strong>
                    </div>

                </div>


                <div className="stat-card">

                    <div className="stat-icon">
                        <FaPercentage />
                    </div>

                    <div>
                        <span>
                            Win Rate
                        </span>

                        <strong>
                            {formatNumber(
                                winRate
                            )}%
                        </strong>
                    </div>

                </div>

            </section>


            {/* ==========================================
                MAIN GRID
            ========================================== */}

            <section className="dashboard-grid">

                {/* ======================================
                    ACCOUNTS
                ====================================== */}

                <div className="dashboard-card">

                    <div className="card-header">

                        <div>
                            <span>
                                ACCOUNTS
                            </span>

                            <h2>
                                Trading Accounts
                            </h2>
                        </div>

                        <FaWallet />

                    </div>


                    <div className="account-list">

                        {accounts.length === 0 ? (

                            <div className="empty-state">
                                No trading accounts found.
                            </div>

                        ) : (

                            accounts
                                .slice(0, 5)
                                .map((account) => (

                                    <div
                                        className="account-row"
                                        key={account.id}
                                    >

                                        <div>

                                            <strong>
                                                {account.account_name ||
                                                    "Trading Account"}
                                            </strong>

                                            <span>
                                                {account.broker}
                                                {" • "}
                                                {account.is_demo
                                                    ? "Demo"
                                                    : "Live"}
                                            </span>

                                        </div>

                                        <div className="account-values">

                                            <strong>
                                                {formatMoney(
                                                    account.equity
                                                )}
                                            </strong>

                                            <span
                                                className={
                                                    account.status ===
                                                    "CONNECTED"
                                                        ? "connected"
                                                        : "disconnected"
                                                }
                                            >
                                                {account.status}
                                            </span>

                                        </div>

                                    </div>

                                ))
                        )}

                    </div>

                </div>


                {/* ======================================
                    RISK
                ====================================== */}

                <div className="dashboard-card">

                    <div className="card-header">

                        <div>
                            <span>
                                RISK ENGINE
                            </span>

                            <h2>
                                Risk Overview
                            </h2>
                        </div>

                        <FaShieldAlt />

                    </div>


                    <div className="risk-content">

                        <div className="risk-item">

                            <span>
                                Open Positions
                            </span>

                            <strong>
                                {openPositions.length}
                            </strong>

                        </div>


                        <div className="risk-item">

                            <span>
                                Active Symbols
                            </span>

                            <strong>
                                {symbols.length}
                            </strong>

                        </div>


                        <div className="risk-item">

                            <span>
                                Active Accounts
                            </span>

                            <strong>
                                {
                                    accounts.filter(
                                        (account) =>
                                            account.active
                                    ).length
                                }
                            </strong>

                        </div>


                        <div className="risk-status">

                            <span className="risk-dot" />

                            <strong>
                                Risk Engine Active
                            </strong>

                        </div>

                    </div>

                </div>

            </section>


            {/* ==========================================
                OPEN POSITIONS
            ========================================== */}

            <section className="dashboard-card positions-card">

                <div className="card-header">

                    <div>
                        <span>
                            LIVE TRADING
                        </span>

                        <h2>
                            Open Positions
                        </h2>
                    </div>

                    <span className="live-indicator">
                        LIVE
                    </span>

                </div>


                {openPositions.length === 0 ? (

                    <div className="empty-state">
                        No open positions.
                    </div>

                ) : (

                    <div className="table-wrapper">

                        <table>

                            <thead>
                                <tr>
                                    <th>
                                        Strategy
                                    </th>

                                    <th>
                                        Direction
                                    </th>

                                    <th>
                                        Volume
                                    </th>

                                    <th>
                                        Entry
                                    </th>

                                    <th>
                                        Current
                                    </th>

                                    <th>
                                        Floating P&L
                                    </th>

                                    <th>
                                        Status
                                    </th>
                                </tr>
                            </thead>

                            <tbody>

                                {openPositions
                                    .slice(0, 10)
                                    .map(
                                        (position) => (

                                            <tr
                                                key={
                                                    position.id
                                                }
                                            >

                                                <td>
                                                    {position.strategy ||
                                                        "—"}
                                                </td>

                                                <td>

                                                    <span
                                                        className={
                                                            position.direction ===
                                                            "BUY"
                                                                ? "direction buy"
                                                                : "direction sell"
                                                        }
                                                    >

                                                        {position.direction ===
                                                        "BUY" ? (
                                                            <FaArrowUp />
                                                        ) : (
                                                            <FaArrowDown />
                                                        )}

                                                        {
                                                            position.direction
                                                        }

                                                    </span>

                                                </td>

                                                <td>
                                                    {formatNumber(
                                                        position.volume
                                                    )}
                                                </td>

                                                <td>
                                                    {formatNumber(
                                                        position.entry_price
                                                    )}
                                                </td>

                                                <td>
                                                    {formatNumber(
                                                        position.liveCurrentPrice
                                                    )}
                                                </td>

                                                <td
                                                    className={
                                                        Number(
                                                            position.liveFloatingProfit
                                                        ) >=
                                                        0
                                                            ? "positive"
                                                            : "negative"
                                                    }
                                                >
                                                    {formatMoney(
                                                        position.floating_profit
                                                    )}
                                                </td>

                                                <td>
                                                    <span className="status-open">
                                                        {
                                                            position.status
                                                        }
                                                    </span>
                                                </td>

                                            </tr>

                                        )
                                    )}

                            </tbody>

                        </table>

                    </div>

                )}

            </section>


            {/* ==========================================
                BOTTOM GRID
            ========================================== */}

            <section className="dashboard-bottom-grid">

                {/* Recent Trades */}

                <div className="dashboard-card">

                    <div className="card-header">

                        <div>
                            <span>
                                EXECUTION
                            </span>

                            <h2>
                                Recent Trades
                            </h2>
                        </div>

                    </div>


                    <div className="trade-list">

                        {trades.length === 0 ? (

                            <div className="empty-state">
                                No trades found.
                            </div>

                        ) : (

                            trades
                                .slice(0, 6)
                                .map((trade) => (

                                    <div
                                        className="trade-row"
                                        key={trade.id}
                                    >

                                        <div>

                                            <strong>
                                                {trade.strategy ||
                                                    "Strategy"}
                                            </strong>

                                            <span>
                                                {
                                                    trade.direction
                                                }
                                            </span>

                                        </div>

                                        <strong
                                            className={
                                                Number(
                                                    trade.net_profit
                                                ) >= 0
                                                    ? "positive"
                                                    : "negative"
                                            }
                                        >
                                            {formatMoney(
                                                trade.net_profit
                                            )}
                                        </strong>

                                    </div>

                                ))
                        )}

                    </div>

                </div>


                {/* Broker */}

                <div className="dashboard-card">

                    <div className="card-header">

                        <div>
                            <span>
                                BROKER
                            </span>

                            <h2>
                                Broker Account
                            </h2>
                        </div>

                    </div>


                    {brokerAccount ? (

                        <div className="broker-info">

                            <div>
                                <span>
                                    Broker
                                </span>

                                <strong>
                                    {
                                        brokerAccount.broker ||
                                        "MT5"
                                    }
                                </strong>
                            </div>

                            <div>
                                <span>
                                    Account
                                </span>

                                <strong>
                                    {
                                        brokerAccount.account_number ||
                                        "—"
                                    }
                                </strong>
                            </div>

                            <div>
                                <span>
                                    Balance
                                </span>

                                <strong>
                                    {formatMoney(
                                        brokerAccount.balance
                                    )}
                                </strong>
                            </div>

                            <div>
                                <span>
                                    Equity
                                </span>

                                <strong>
                                    {formatMoney(
                                        brokerAccount.equity
                                    )}
                                </strong>
                            </div>

                        </div>

                    ) : (

                        <div className="empty-state">
                            Broker account unavailable.
                        </div>

                    )}

                </div>

            </section>


            {/* ==========================================
                FOOTER
            ========================================== */}

            <div className="dashboard-footer">

                <span>
                    Symbols: {symbols.length}
                </span>

                <span>
                    Positions: {positions.length}
                </span>

                <span>
                    Trades: {trades.length}
                </span>

                <span className={Object.keys(liveTicks).length ? "connected" : "disconnected"}>
                    Live feed: {Object.keys(liveTicks).length ? "CONNECTED" : "CONNECTING"}
                </span>

                {lastUpdated && (
                    <span>
                        Updated{" "}
                        {new Date(
                            lastUpdated
                        ).toLocaleTimeString()}
                    </span>
                )}

            </div>

        </main>
    );
};

export default Dashboard;