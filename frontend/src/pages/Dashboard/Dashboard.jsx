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
  FaBolt,
} from "react-icons/fa";

import { loadDashboard } from "../../redux/dashboard/dashboardThunks";
import {
  fetchBotStatus,
  startBot,
  stopBot,
} from "../../redux/dashboard/botThunks";
import { fetchTradingUniverse } from "../../redux/dashboard/symbols/symbolsThunks";
import { fetchAccounts } from "../../redux/dashboard/accounts/accountsThunks";

import { openTickStream } from "../../api/tickStream";

import "../../css/dashboard.css";

const Dashboard = () => {
  const dispatch = useDispatch();

  // --------------------------------------------------
  // DASHBOARD STATE
  // --------------------------------------------------

  const {
    accounts: dashboardAccounts = [],
    positions = [],
    trades = [],
    loading,
    error,
    brokerAccount,
    lastUpdated,
  } = useSelector((state) => state.dashboard);

  // --------------------------------------------------
  // ACCOUNTS STATE
  // --------------------------------------------------

  const accountsState = useSelector((state) => state.accounts);

  const selectedAccount = accountsState?.selectedAccount || null;

  const accountList = useMemo(() => {
    if (Array.isArray(accountsState?.accounts)) {
      return accountsState.accounts;
    }

    if (Array.isArray(dashboardAccounts)) {
      return dashboardAccounts;
    }

    return [];
  }, [accountsState?.accounts, dashboardAccounts]);

  // --------------------------------------------------
  // SYMBOL STATE
  // --------------------------------------------------

  const selectedSymbols = useSelector(
    (state) => state.symbols?.selectedSymbols || [],
  );

  const accountSymbols = useSelector((state) =>
    state.symbols?.symbolsByAccount?.[String(selectedAccount?.id)] || [],
  );

  // --------------------------------------------------
  // BOT STATE
  // --------------------------------------------------

  const bot = useSelector((state) => state.bot);

  // --------------------------------------------------
  // LOCAL STATE
  // --------------------------------------------------

  const [liveTicks, setLiveTicks] = useState({});

  // --------------------------------------------------
  // LOAD DASHBOARD
  // --------------------------------------------------

  useEffect(() => {
    dispatch(loadDashboard());
    dispatch(fetchBotStatus());
    dispatch(fetchAccounts());
  }, [dispatch]);

  // --------------------------------------------------
  // LOAD SELECTED ACCOUNT'S TRADING UNIVERSE
  // --------------------------------------------------

  useEffect(() => {
    if (!selectedAccount?.id) {
      return;
    }

    dispatch(fetchTradingUniverse(selectedAccount.id));
  }, [dispatch, selectedAccount?.id]);

  // --------------------------------------------------
  // REFRESH DASHBOARD
  // --------------------------------------------------

  useEffect(() => {
    const refresh = window.setInterval(() => {
      dispatch(loadDashboard());
      dispatch(fetchAccounts());

      if (selectedAccount?.id) {
        dispatch(fetchTradingUniverse(selectedAccount.id));
      }
    }, 30000);

    return () => window.clearInterval(refresh);
  }, [dispatch, selectedAccount?.id]);

  // --------------------------------------------------
  // LIVE TICK STREAMS
  // --------------------------------------------------

  useEffect(() => {
    const symbolsForStream =
      selectedSymbols.length > 0
        ? selectedSymbols
        : accountSymbols.filter((symbol) => symbol.enabled === true);

    const sockets = symbolsForStream
      .filter((symbol) => symbol.enabled !== false)
      .map(
        (symbol) =>
          symbol.name ||
          symbol.symbol ||
          symbol.symbol_name ||
          symbol.broker_symbol ||
          symbol.symbol?.name,
      )
      .filter(Boolean)
      .map((symbol) =>
        openTickStream(
          symbol,
          (payload) =>
            setLiveTicks((current) => ({
              ...current,
              [symbol]: payload.tick,
            })),
          () => undefined,
        ),
      );

    return () => {
      sockets.forEach((socket) => socket.close());
    };
  }, [selectedSymbols, accountSymbols]);

  // --------------------------------------------------
  // MANUAL REFRESH
  // --------------------------------------------------

  const handleRefresh = () => {
    dispatch(loadDashboard());
    dispatch(fetchBotStatus());
    dispatch(fetchAccounts());

    if (selectedAccount?.id) {
      dispatch(fetchTradingUniverse(selectedAccount.id));
    }
  };

  // --------------------------------------------------
  // ENGINE CONTROLS
  // --------------------------------------------------

  const handleStartEngine = () => {
    const symbols = selectedSymbols
      .map(
        (symbol) =>
          symbol.broker_symbol ||
          symbol.name ||
          symbol.symbol ||
          symbol.symbol_name,
      )
      .filter(Boolean);

    dispatch(
      startBot({
        strategy_name: "ema_cross",
        strategy_version: "1.0.0",
        symbols,
        timeframe: "M1",
        risk_percent: 1,
      }),
    );
  };

  const handleStopEngine = () => {
    dispatch(stopBot());
  };

  // --------------------------------------------------
  // FORMATTERS
  // --------------------------------------------------

  const formatMoney = (value, currency = "USD") => {
    const number = Number(value);

    if (!Number.isFinite(number)) {
      return `${currency} 0.00`;
    }

    return new Intl.NumberFormat("en-US", {
      style: "currency",
      currency: currency || "USD",
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
  // ACTIVE ACCOUNT
  // --------------------------------------------------

  const connectedAccounts = useMemo(
    () =>
      accountList.filter(
        (account) => account.status === "CONNECTED" && account.active !== false,
      ),
    [accountList],
  );

  const activeAccount = useMemo(() => {
    if (
      selectedAccount &&
      selectedAccount.status === "CONNECTED" &&
      selectedAccount.active !== false
    ) {
      return selectedAccount;
    }

    if (selectedAccount) {
      return selectedAccount;
    }

    if (connectedAccounts.length > 0) {
      return connectedAccounts[0];
    }

    return accountList[0] || null;
  }, [selectedAccount, connectedAccounts, accountList]);

  // --------------------------------------------------
  // ACCOUNT CURRENCY
  // --------------------------------------------------

  const accountCurrency = activeAccount?.currency || "USD";

  // --------------------------------------------------
  // BALANCE
  // --------------------------------------------------

  const totalBalance = useMemo(() => {
    if (
      activeAccount?.balance !== undefined &&
      activeAccount?.balance !== null
    ) {
      return Number(activeAccount.balance);
    }

    if (
      brokerAccount?.balance !== undefined &&
      brokerAccount?.balance !== null
    ) {
      return Number(brokerAccount.balance);
    }

    return 0;
  }, [activeAccount, brokerAccount]);

  // --------------------------------------------------
  // EQUITY
  // --------------------------------------------------

  const totalEquity = useMemo(() => {
    if (activeAccount?.equity !== undefined && activeAccount?.equity !== null) {
      return Number(activeAccount.equity);
    }

    if (brokerAccount?.equity !== undefined && brokerAccount?.equity !== null) {
      return Number(brokerAccount.equity);
    }

    return 0;
  }, [activeAccount, brokerAccount]);

  // --------------------------------------------------
  // MARGIN
  // --------------------------------------------------

  const margin = Number(activeAccount?.margin || brokerAccount?.margin || 0);

  const freeMargin = Number(
    activeAccount?.free_margin ||
      brokerAccount?.free_margin ||
      Math.max(totalEquity - margin, 0),
  );

  const marginLevel = Number(
    activeAccount?.margin_level || brokerAccount?.margin_level || 0,
  );

  // --------------------------------------------------
  // SELECTED SYMBOLS
  // --------------------------------------------------

  const activeSymbols = useMemo(() => {
    return selectedSymbols.filter((symbol) => symbol.enabled === true);
  }, [selectedSymbols]);

  // --------------------------------------------------
  // SYMBOL LOOKUP
  // --------------------------------------------------

  const symbolById = useMemo(() => {
    const map = {};

    accountSymbols.forEach((symbol) => {
      const name =
        symbol.broker_symbol ||
        symbol.name ||
        symbol.symbol ||
        symbol.symbol_name;

      if (symbol.id && name) {
        map[symbol.id] = name;
      }
    });

    return map;
  }, [accountSymbols]);

  // --------------------------------------------------
  // LIVE POSITIONS
  // --------------------------------------------------

  const livePositions = useMemo(
    () =>
      positions.map((position) => {
        const symbol =
          symbolById[position.account_symbol_id] ||
          symbolById[position.symbol_id] ||
          position.broker_symbol ||
          position.symbol_name ||
          position.symbol;

        const tick = symbol ? liveTicks[symbol] : null;

        const currentPrice = Number(
          position.direction === "SELL"
            ? tick?.ask ||
                tick?.last ||
                position.current_price ||
                position.price_current ||
                0
            : tick?.bid ||
                tick?.last ||
                position.current_price ||
                position.price_current ||
                0,
        );

        const entryPrice = Number(
          position.entry_price ||
            position.open_price ||
            position.price_open ||
            0,
        );

        const volume = Number(
          position.current_volume || position.volume || position.lots || 0,
        );

        const direction =
          position.direction === "SELL" || position.type === "SELL" ? -1 : 1;

        const liveProfit =
          tick && currentPrice && entryPrice
            ? (currentPrice - entryPrice) * volume * direction
            : Number(
                position.floating_profit ||
                  position.unrealized_pnl ||
                  position.profit ||
                  0,
              );

        return {
          ...position,
          displaySymbol: symbol || "—",
          liveCurrentPrice: currentPrice,
          liveFloatingProfit: liveProfit,
        };
      }),
    [positions, symbolById, liveTicks],
  );

  // --------------------------------------------------
  // OPEN POSITIONS
  // --------------------------------------------------

  const openPositions = useMemo(
    () =>
      livePositions.filter(
        (position) => position.status === "OPEN" || position.status === "open",
      ),
    [livePositions],
  );

  // --------------------------------------------------
  // FLOATING PROFIT
  // --------------------------------------------------

  const floatingProfit = useMemo(
    () =>
      livePositions.reduce(
        (sum, position) => sum + Number(position.liveFloatingProfit || 0),
        0,
      ),
    [livePositions],
  );

  // --------------------------------------------------
  // WIN RATE
  // --------------------------------------------------

  const winningTrades = useMemo(
    () =>
      trades.filter(
        (trade) =>
          trade.result === "WIN" ||
          trade.result === "win" ||
          Number(trade.profit || trade.realized_profit || 0) > 0,
      ).length,
    [trades],
  );

  const winRate = trades.length > 0 ? (winningTrades / trades.length) * 100 : 0;

  // --------------------------------------------------
  // ENGINE STATUS
  // --------------------------------------------------

  const engineRunning = Boolean(bot.status?.active);

  // --------------------------------------------------
  // RENDER
  // --------------------------------------------------

  return (
    <main className="dashboard">
      {/* HEADER */}
      <header className="dashboard-header">
        <div>
          <span className="dashboard-eyebrow">Athena Quant Engine</span>

          <h1>Trading Dashboard</h1>

          <p>
            Monitor your account, trading universe, positions and engine
            activity.
          </p>
        </div>

        <button
          type="button"
          className="dashboard-refresh"
          onClick={handleRefresh}
          disabled={loading}
        >
          <FaSyncAlt className={loading ? "spin" : ""} />

          {loading ? "Refreshing..." : "Refresh"}
        </button>
      </header>

      {/* ENGINE CONTROL */}
      <section className="engine-control">
        <div className="engine-control__info">
          <div className="engine-control__icon">
            <FaBolt />
          </div>

          <div>
            <h2>Trading Engine</h2>

            <p>
              {selectedAccount
                ? `Running against ${selectedAccount.account_name || "selected account"}`
                : "Select a trading account to operate the engine."}
            </p>
          </div>
        </div>

        <div className="engine-control__actions">
          <span
            className={`engine-status ${
              engineRunning ? "engine-status--active" : ""
            }`}
          >
            <span className="engine-status__dot" />

            {engineRunning ? "RUNNING" : "STOPPED"}
          </span>

          <span className="engine-mode">
            {activeAccount?.is_demo ? "DEMO" : "LIVE"}
          </span>

          {!engineRunning ? (
            <button
              type="button"
              className="engine-button engine-button--start"
              onClick={handleStartEngine}
              disabled={!selectedAccount || activeSymbols.length === 0}
            >
              <FaPlay />
              Start Engine
            </button>
          ) : (
            <button
              type="button"
              className="engine-button engine-button--stop"
              onClick={handleStopEngine}
            >
              <FaStop />
              Stop Engine
            </button>
          )}
        </div>
      </section>

      {/* ERROR */}
      {error && (
        <div className="dashboard-error">
          {typeof error === "string"
            ? error
            : "Unable to load some dashboard data."}
        </div>
      )}

      {/* STAT CARDS */}
      <section className="dashboard-stats">
        <article className="stat-card">
          <div className="stat-icon">
            <FaWallet />
          </div>

          <div>
            <span>Balance</span>

            <strong>{formatMoney(totalBalance, accountCurrency)}</strong>
          </div>
        </article>

        <article className="stat-card">
          <div className="stat-icon">
            <FaChartLine />
          </div>

          <div>
            <span>Equity</span>

            <strong>{formatMoney(totalEquity, accountCurrency)}</strong>
          </div>
        </article>

        <article className="stat-card">
          <div className="stat-icon">
            <FaExchangeAlt />
          </div>

          <div>
            <span>Floating P/L</span>

            <strong
              className={
                floatingProfit > 0
                  ? "positive"
                  : floatingProfit < 0
                    ? "negative"
                    : ""
              }
            >
              {formatMoney(floatingProfit, accountCurrency)}
            </strong>
          </div>
        </article>

        <article className="stat-card">
          <div className="stat-icon">
            <FaPercentage />
          </div>

          <div>
            <span>Win Rate</span>

            <strong>{winRate.toFixed(1)}%</strong>
          </div>
        </article>
      </section>

      {/* ACCOUNT + RISK */}
      <section className="dashboard-grid">
        {/* ACCOUNT */}
        <article className="dashboard-card">
          <div className="card-header">
            <div>
              <span>TRADING ACCOUNT</span>

              <h2>Active Account</h2>
            </div>

            <FaWallet />
          </div>

          {activeAccount ? (
            <div className="connected-account">
              <div className="connected-account__identity">
                <div>
                  <strong>
                    {activeAccount.account_name || "Trading Account"}
                  </strong>

                  <span>
                    {activeAccount.broker || "MT5"} •{" "}
                    {activeAccount.is_demo ? "Demo" : "Live"}
                  </span>
                </div>

                <span
                  className={
                    activeAccount.status === "CONNECTED"
                      ? "connected"
                      : "disconnected"
                  }
                >
                  {activeAccount.status || "UNKNOWN"}
                </span>
              </div>

              <div className="connected-account__details">
                <div>
                  <span>Login</span>

                  <strong>{activeAccount.login || "—"}</strong>
                </div>

                <div>
                  <span>Server</span>

                  <strong>{activeAccount.server || "—"}</strong>
                </div>

                <div>
                  <span>Currency</span>

                  <strong>{activeAccount.currency || "USD"}</strong>
                </div>

                <div>
                  <span>Leverage</span>

                  <strong>1:{activeAccount.leverage || "—"}</strong>
                </div>

                <div>
                  <span>Balance</span>

                  <strong>
                    {formatMoney(activeAccount.balance, activeAccount.currency)}
                  </strong>
                </div>

                <div>
                  <span>Equity</span>

                  <strong>
                    {formatMoney(activeAccount.equity, activeAccount.currency)}
                  </strong>
                </div>
              </div>
            </div>
          ) : (
            <div className="empty-state">No trading account selected.</div>
          )}
        </article>

        {/* RISK */}
        <article className="dashboard-card">
          <div className="card-header">
            <div>
              <span>ACCOUNT RISK</span>

              <h2>Risk Overview</h2>
            </div>

            <FaShieldAlt />
          </div>

          <div className="risk-content">
            <div className="risk-item">
              <span>Open Positions</span>

              <strong>{openPositions.length}</strong>
            </div>

            <div className="risk-item">
              <span>Selected Symbols</span>

              <strong>{activeSymbols.length}</strong>
            </div>

            <div className="risk-item">
              <span>Connected Accounts</span>

              <strong>{connectedAccounts.length}</strong>
            </div>

            <div className="risk-item">
              <span>Free Margin</span>

              <strong>{formatMoney(freeMargin, accountCurrency)}</strong>
            </div>

            <div className="risk-item">
              <span>Margin Used</span>

              <strong>{formatMoney(margin, accountCurrency)}</strong>
            </div>

            <div className="risk-item">
              <span>Margin Level</span>

              <strong>
                {marginLevel > 0 ? `${formatNumber(marginLevel)}%` : "—"}
              </strong>
            </div>

            <div className="risk-status">
              <span className="risk-dot" />

              <strong>Risk monitoring active</strong>
            </div>
          </div>
        </article>
      </section>

      {/* POSITIONS */}
      <section className="dashboard-card positions-card">
        <div className="card-header">
          <div>
            <span>LIVE MARKET EXPOSURE</span>

            <h2>Open Positions</h2>
          </div>

          <FaChartLine />
        </div>

        {openPositions.length > 0 ? (
          <div className="table-wrapper">
            <table>
              <thead>
                <tr>
                  <th>Symbol</th>
                  <th>Direction</th>
                  <th>Volume</th>
                  <th>Entry</th>
                  <th>Current</th>
                  <th>Floating P/L</th>
                  <th>Status</th>
                </tr>
              </thead>

              <tbody>
                {openPositions.map((position) => {
                  const direction = position.direction || position.type || "—";

                  const isBuy = direction === "BUY";

                  return (
                    <tr key={position.id}>
                      <td>
                        <strong>{position.displaySymbol}</strong>
                      </td>

                      <td>
                        <span className={`direction ${isBuy ? "buy" : "sell"}`}>
                          {isBuy ? <FaArrowUp /> : <FaArrowDown />}

                          {direction}
                        </span>
                      </td>

                      <td>
                        {formatNumber(
                          position.current_volume || position.volume,
                        )}
                      </td>

                      <td>
                        {formatNumber(
                          position.entry_price ||
                            position.open_price ||
                            position.price_open,
                        )}
                      </td>

                      <td>{formatNumber(position.liveCurrentPrice)}</td>

                      <td
                        className={
                          position.liveFloatingProfit > 0
                            ? "positive"
                            : position.liveFloatingProfit < 0
                              ? "negative"
                              : ""
                        }
                      >
                        {formatMoney(
                          position.liveFloatingProfit,
                          accountCurrency,
                        )}
                      </td>

                      <td>
                        <span className="status-open">OPEN</span>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="empty-state">No open positions.</div>
        )}
      </section>

      {/* BOTTOM GRID */}
      <section className="dashboard-bottom-grid">
        {/* RECENT TRADES */}
        <article className="dashboard-card">
          <div className="card-header">
            <div>
              <span>EXECUTION HISTORY</span>

              <h2>Recent Trades</h2>
            </div>

            <FaExchangeAlt />
          </div>

          {trades.length > 0 ? (
            <div className="trade-list">
              {trades.slice(0, 6).map((trade) => {
                const profit = Number(
                  trade.profit || trade.realized_profit || trade.pnl || 0,
                );

                const symbol =
                  trade.broker_symbol ||
                  trade.symbol_name ||
                  trade.symbol ||
                  "Unknown";

                return (
                  <div className="trade-row" key={trade.id}>
                    <div>
                      <strong>{symbol}</strong>

                      <span>{trade.direction || trade.type || "TRADE"}</span>
                    </div>

                    <strong
                      className={
                        profit > 0 ? "positive" : profit < 0 ? "negative" : ""
                      }
                    >
                      {formatMoney(profit, accountCurrency)}
                    </strong>
                  </div>
                );
              })}
            </div>
          ) : (
            <div className="empty-state">No recent trades.</div>
          )}
        </article>

        {/* BROKER */}
        <article className="dashboard-card">
          <div className="card-header">
            <div>
              <span>BROKER CONNECTION</span>

              <h2>MT5 Account</h2>
            </div>

            <FaBolt />
          </div>

          {brokerAccount || activeAccount ? (
            <div className="broker-info">
              <div>
                <span>Login</span>

                <strong>
                  {brokerAccount?.login || activeAccount?.login || "—"}
                </strong>
              </div>

              <div>
                <span>Server</span>

                <strong>
                  {brokerAccount?.server || activeAccount?.server || "—"}
                </strong>
              </div>

              <div>
                <span>Balance</span>

                <strong>
                  {formatMoney(
                    brokerAccount?.balance ?? activeAccount?.balance ?? 0,
                    accountCurrency,
                  )}
                </strong>
              </div>

              <div>
                <span>Equity</span>

                <strong>
                  {formatMoney(
                    brokerAccount?.equity ?? activeAccount?.equity ?? 0,
                    accountCurrency,
                  )}
                </strong>
              </div>

              <div>
                <span>Symbols</span>

                <strong>{activeSymbols.length}</strong>
              </div>

              <div>
                <span>Engine</span>

                <strong
                  className={engineRunning ? "connected" : "disconnected"}
                >
                  {engineRunning ? "RUNNING" : "STOPPED"}
                </strong>
              </div>
            </div>
          ) : (
            <div className="empty-state">
              No broker account information available.
            </div>
          )}
        </article>
      </section>

      {/* FOOTER */}
      <footer className="dashboard-footer">
        <span>Accounts: {accountList.length}</span>

        <span>Selected Symbols: {activeSymbols.length}</span>

        <span>Positions: {openPositions.length}</span>

        <span>Trades: {trades.length}</span>

        {lastUpdated && (
          <span>Updated: {new Date(lastUpdated).toLocaleTimeString()}</span>
        )}
      </footer>
    </main>
  );
};

export default Dashboard;
