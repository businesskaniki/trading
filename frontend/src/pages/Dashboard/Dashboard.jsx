import { useEffect } from "react";
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
} from "react-icons/fa";

import { loadDashboard } from "../../redux/dashboard/dashboardThunks";

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

    useEffect(() => {
        dispatch(loadDashboard());
    }, [dispatch]);

    // --------------------------------------------------
    // Refresh
    // --------------------------------------------------

    const handleRefresh = () => {
        dispatch(loadDashboard());
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

    const floatingProfit = positions.reduce(
        (sum, position) =>
            sum +
            Number(position.floating_profit || 0),
        0
    );

    const openPositions = positions.filter(
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
                            Floating P&L
                        </span>

                        <strong
                            className={
                                floatingProfit >= 0
                                    ? "positive"
                                    : "negative"
                            }
                        >
                            {formatMoney(
                                floatingProfit
                            )}
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
                                                        position.current_price
                                                    )}
                                                </td>

                                                <td
                                                    className={
                                                        Number(
                                                            position.floating_profit
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