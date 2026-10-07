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
  FaPause,
  FaRedo,
} from "react-icons/fa";

import {
  fetchPositions,
  fetchTrades,
  fetchBrokerAccount,
} from "../../redux/dashboard/dashboardThunks";

import {
  fetchEngineStatus,
  startEngine,
  stopEngine,
  pauseEngine,
  resumeEngine,
} from "../../redux/dashboard/engine/engineThunks";

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

  // Accounts are owned by accountsSlice.
  // Do not maintain a second account source in dashboardSlice.
  const accountList = accountsState?.accounts || [];

  // --------------------------------------------------
  // SYMBOL STATE
  // --------------------------------------------------

  const selectedSymbols = useSelector(
    (state) => state.symbols?.selectedSymbols || [],
  );

  const accountSymbols = useSelector(
    (state) =>
      state.symbols?.symbolsByAccount?.[String(selectedAccount?.id)] || [],
  );

  // --------------------------------------------------
  // ENGINE STATE
  // --------------------------------------------------

  const engine = useSelector(
    (state) =>
      state.engine || {
        status: "STOPPED",
        mode: null,
        account: null,
        market_data: null,
        strategies: null,
        pipeline: null,
        execution: null,
        loading: false,
        actionLoading: false,
        error: null,
        lastUpdated: null,
      },
  );

  const engineStatus = engine.status || "STOPPED";

  const engineRunning = engineStatus === "RUNNING";
  const enginePaused = engineStatus === "PAUSED";
  const engineStarting = engineStatus === "STARTING";
  const engineStopping = engineStatus === "STOPPING";

  const engineBusy = engineStarting || engineStopping || engine.actionLoading;

  const engineAccount = engine.account || null;

  // --------------------------------------------------
  // LOCAL STATE
  // --------------------------------------------------

  const [liveTicks, setLiveTicks] = useState({});

  // --------------------------------------------------
  // INITIAL DASHBOARD LOAD
  // --------------------------------------------------
  //
  // These requests are independent and start concurrently:
  //
  //   - accounts
  //   - positions
  //   - trades
  //   - engine status
  //
  // Account-dependent data is loaded separately once
  // selectedAccount becomes available.
  // --------------------------------------------------

  useEffect(() => {
    dispatch(fetchAccounts());
    dispatch(fetchPositions());
    dispatch(fetchTrades());
    dispatch(fetchEngineStatus());
  }, [dispatch]);

  // --------------------------------------------------
  // LOAD SELECTED ACCOUNT DATA
  // --------------------------------------------------
  //
  // Once the account slice has selected an account,
  // these requests execute concurrently:
  //
  //   - trading universe
  //   - broker account
  // --------------------------------------------------

  useEffect(() => {
    const accountId = selectedAccount?.id;

    if (!accountId) {
      return;
    }

    dispatch(fetchTradingUniverse(accountId));
    dispatch(fetchBrokerAccount(accountId));
  }, [dispatch, selectedAccount?.id]);

  // --------------------------------------------------
  // PERIODIC DASHBOARD REFRESH
  // --------------------------------------------------
  //
  // Only refresh data that changes continuously during
  // normal Dashboard operation.
  //
  // Accounts, trading universe and broker account are
  // intentionally excluded. They are refreshed when the
  // selected account changes or during manual refresh.
  // --------------------------------------------------

  useEffect(() => {
    const refresh = window.setInterval(() => {
      dispatch(fetchPositions());
      dispatch(fetchTrades());
      dispatch(fetchEngineStatus());
    }, 30000);

    return () => window.clearInterval(refresh);
  }, [dispatch]);

  // --------------------------------------------------
  // LIVE TICK STREAMS
  // --------------------------------------------------

  // --------------------------------------------------
  // MANUAL REFRESH
  // --------------------------------------------------
  //
  // Manual refresh reloads all currently relevant
  // Dashboard data.
  // --------------------------------------------------

  const handleRefresh = () => {
    dispatch(fetchAccounts());
    dispatch(fetchPositions());
    dispatch(fetchTrades());
    dispatch(fetchEngineStatus());

    if (selectedAccount?.id) {
      dispatch(fetchTradingUniverse(selectedAccount.id));
      dispatch(fetchBrokerAccount(selectedAccount.id));
    }
  };

  // --------------------------------------------------
  // ENGINE CONTROLS
  // --------------------------------------------------

  const handleStartEngine = async () => {
    if (!selectedAccount?.id || engineBusy) {
      return;
    }

    await dispatch(startEngine(selectedAccount.id));
  };

  const handleStopEngine = async () => {
    if (engineBusy) {
      return;
    }

    await dispatch(stopEngine());
  };

  const handlePauseEngine = async () => {
    if (!engineRunning || engineBusy) {
      return;
    }

    await dispatch(pauseEngine());
  };

  const handleResumeEngine = async () => {
    if (!enginePaused || engineBusy) {
      return;
    }

    await dispatch(resumeEngine());
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
  // ENGINE ACCOUNT MATCH
  // --------------------------------------------------

  const engineAccountId = engineAccount?.id ? String(engineAccount.id) : null;

  const selectedAccountId = selectedAccount?.id
    ? String(selectedAccount.id)
    : null;

  const engineAccountMatchesSelection =
    !engineAccountId ||
    !selectedAccountId ||
    engineAccountId === selectedAccountId;

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
  // ENGINE STATUS LABEL
  // --------------------------------------------------

  const engineStatusLabel = useMemo(() => {
    switch (engineStatus) {
      case "STARTING":
        return "STARTING";

      case "RUNNING":
        return "RUNNING";

      case "PAUSED":
        return "PAUSED";

      case "STOPPING":
        return "STOPPING";

      case "STOPPED":
      default:
        return "STOPPED";
    }
  }, [engineStatus]);

  // --------------------------------------------------
  // ENGINE STATUS CLASS
  // --------------------------------------------------

  const engineStatusClass = useMemo(() => {
    switch (engineStatus) {
      case "RUNNING":
        return "engine-status engine-status--active";

      case "PAUSED":
        return "engine-status engine-status--paused";

      case "STARTING":
      case "STOPPING":
        return "engine-status engine-status--transitioning";

      case "STOPPED":
      default:
        return "engine-status";
    }
  }, [engineStatus]);

  // --------------------------------------------------
  // ENGINE MODE
  // --------------------------------------------------

  const engineModeLabel =
    engine.mode ||
    (engineAccount?.is_demo
      ? "DEMO"
      : activeAccount?.is_demo
        ? "DEMO"
        : "LIVE");

  // --------------------------------------------------
  // ENGINE ERROR
  // --------------------------------------------------

  const dashboardError = error || engine.error;

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
          disabled={loading || engine.loading}
        >
          <FaSyncAlt className={loading || engine.loading ? "spin" : ""} />

          {loading || engine.loading ? "Refreshing..." : "Refresh"}
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
              {engineRunning || enginePaused
                ? engineAccount
                  ? `Engine attached to ${
                      engineAccount.account_name ||
                      engineAccount.login ||
                      "active account"
                    }`
                  : "Engine is operating."
                : selectedAccount
                  ? `Ready to operate ${
                      selectedAccount.account_name || "selected account"
                    }`
                  : "Select a trading account to operate the engine."}
            </p>

            {(engineRunning || enginePaused) &&
              !engineAccountMatchesSelection && (
                <small className="engine-account-warning">
                  The selected account is different from the account currently
                  running the engine.
                </small>
              )}
          </div>
        </div>

        <div className="engine-control__actions">
          <span className={engineStatusClass}>
            <span className="engine-status__dot" />

            {engineStatusLabel}
          </span>

          <span className="engine-mode">{engineModeLabel}</span>

          {/* STOPPED */}
          {engineStatus === "STOPPED" && (
            <button
              type="button"
              className="engine-button engine-button--start"
              onClick={handleStartEngine}
              disabled={!selectedAccount?.id || engineBusy}
            >
              <FaPlay />
              Start Engine
            </button>
          )}

          {/* STARTING */}
          {engineStatus === "STARTING" && (
            <button type="button" className="engine-button" disabled>
              <FaSyncAlt className="spin" />
              Starting...
            </button>
          )}

          {/* RUNNING */}
          {engineStatus === "RUNNING" && (
            <>
              <button
                type="button"
                className="engine-button"
                onClick={handlePauseEngine}
                disabled={engineBusy}
              >
                <FaPause />
                Pause
              </button>

              <button
                type="button"
                className="engine-button engine-button--stop"
                onClick={handleStopEngine}
                disabled={engineBusy}
              >
                <FaStop />
                Stop Engine
              </button>
            </>
          )}

          {/* PAUSED */}
          {engineStatus === "PAUSED" && (
            <>
              <button
                type="button"
                className="engine-button engine-button--start"
                onClick={handleResumeEngine}
                disabled={engineBusy}
              >
                <FaRedo />
                Resume
              </button>

              <button
                type="button"
                className="engine-button engine-button--stop"
                onClick={handleStopEngine}
                disabled={engineBusy}
              >
                <FaStop />
                Stop Engine
              </button>
            </>
          )}

          {/* STOPPING */}
          {engineStatus === "STOPPING" && (
            <button type="button" className="engine-button" disabled>
              <FaSyncAlt className="spin" />
              Stopping...
            </button>
          )}
        </div>
      </section>

      {/* ENGINE DETAILS */}
      {(engineRunning || enginePaused) && (
        <section className="engine-runtime">
          <div className="engine-runtime__item">
            <span>Account</span>

            <strong>
              {engineAccount?.account_name ||
                engineAccount?.login ||
                engineAccount?.id ||
                "—"}
            </strong>
          </div>

          <div className="engine-runtime__item">
            <span>Mode</span>

            <strong>{engineModeLabel}</strong>
          </div>

          <div className="engine-runtime__item">
            <span>Market Data</span>

            <strong>{engine.market_data ? "ACTIVE" : "—"}</strong>
          </div>

          <div className="engine-runtime__item">
            <span>Strategies</span>

            <strong>
              {engine.strategies
                ? Array.isArray(engine.strategies)
                  ? engine.strategies.length
                  : (engine.strategies.count ??
                    engine.strategies.active ??
                    "ACTIVE")
                : "—"}
            </strong>
          </div>

          <div className="engine-runtime__item">
            <span>Pipeline</span>

            <strong>{engine.pipeline ? "ACTIVE" : "—"}</strong>
          </div>

          <div className="engine-runtime__item">
            <span>Execution</span>

            <strong>{engine.execution ? "ACTIVE" : "—"}</strong>
          </div>
        </section>
      )}

      {/* ERROR */}
      {dashboardError && (
        <div className="dashboard-error">
          {typeof dashboardError === "string"
            ? dashboardError
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
                  className={
                    engineRunning || enginePaused ? "connected" : "disconnected"
                  }
                >
                  {engineStatusLabel}
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

        <span>Engine: {engineStatusLabel}</span>

        {engine.lastUpdated && (
          <span>
            Engine Updated: {new Date(engine.lastUpdated).toLocaleTimeString()}
          </span>
        )}

        {lastUpdated && (
          <span>Updated: {new Date(lastUpdated).toLocaleTimeString()}</span>
        )}
      </footer>
    </main>
  );
};

export default Dashboard;
