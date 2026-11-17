import { useCallback, useEffect, useMemo, useRef, useState } from "react";
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

import "../../css/dashboard.css";

const Dashboard = () => {
  const dispatch = useDispatch();

  // --------------------------------------------------
  // DASHBOARD STATE
  // --------------------------------------------------

  const dashboardState = useSelector((state) => state.dashboard || {});

  const positions = Array.isArray(dashboardState.positions)
    ? dashboardState.positions
    : [];
  const trades = Array.isArray(dashboardState.trades)
    ? dashboardState.trades
    : [];
  const loading = dashboardState.loading;
  const error = dashboardState.error;
  const brokerAccount = dashboardState.brokerAccount;
  const lastUpdated = dashboardState.lastUpdated;

  // --------------------------------------------------
  // ACCOUNTS STATE
  // --------------------------------------------------

  const accountsState = useSelector((state) => state.accounts || {});

  const selectedAccount = accountsState?.selectedAccount || null;

  const accountList = Array.isArray(accountsState?.accounts)
    ? accountsState.accounts
    : [];

  const dataAccountId =
    selectedAccount?.id ??
    accountList.find((account) => account?.active !== false)?.id ??
    accountList[0]?.id ??
    null;

  // --------------------------------------------------
  // SYMBOL STATE
  // --------------------------------------------------

  const selectedSymbols = useSelector((state) =>
    Array.isArray(state.symbols?.selectedSymbols)
      ? state.symbols.selectedSymbols
      : [],
  );

  const accountSymbols = useSelector((state) => {
    const symbols = state.symbols?.symbolsByAccount?.[String(dataAccountId)];
    return Array.isArray(symbols) ? symbols : [];
  });

  // --------------------------------------------------
  // ENGINE STATE
  // --------------------------------------------------

  const engine = useSelector((state) => state.engine || {});

  const engineStatus = engine.status || "STOPPED";

  const engineRunning = engineStatus === "RUNNING";
  const enginePaused = engineStatus === "PAUSED";
  const engineStarting = engineStatus === "STARTING";
  const engineStopping = engineStatus === "STOPPING";

  const engineBusy = engineStarting || engineStopping || engine.actionLoading;

  const engineAccount = engine.account || null;

  // --------------------------------------------------
  // LIVE PIPELINE STATE
  // --------------------------------------------------
  //
  // Expected backend response:
  //
  // pipeline: {
  //   configured: true,
  //   running: true,
  //   details: {
  //     started: true,
  //     stats: {
  //       received: 0,
  //       risk_evaluations: 0,
  //       approved: 0,
  //       ...
  //     }
  //   }
  // }
  // --------------------------------------------------

  const pipelineContainer =
    engine.pipeline && typeof engine.pipeline === "object"
      ? engine.pipeline
      : {};

  const pipelineDetails = pipelineContainer.details || null;

  const rawPipelineStats =
    pipelineDetails?.stats ?? pipelineContainer.stats ?? null;

  const pipelineStats =
    rawPipelineStats && typeof rawPipelineStats === "object"
      ? rawPipelineStats
      : null;

  const lastContextFailure =
    pipelineStats?.last_context_failure &&
    typeof pipelineStats.last_context_failure === "object"
      ? pipelineStats.last_context_failure
      : null;

  const pipelineConfigured = pipelineContainer.configured === true;

  const pipelineRunning =
    pipelineContainer.running === true || pipelineDetails?.started === true;

  const pipelineStatusLabel = pipelineRunning
    ? "LISTENING"
    : pipelineConfigured
      ? "INACTIVE"
      : "NOT CONFIGURED";

  // --------------------------------------------------
  // LOCAL STATE
  // --------------------------------------------------

  const [visibleError, setVisibleError] = useState(null);

  // --------------------------------------------------
  // REQUEST DIAGNOSTICS + IN-FLIGHT DEDUPLICATION
  // --------------------------------------------------

  const inFlightRequestsRef = useRef(new Map());

  const runRequest = useCallback(
    (trigger, label, thunkCreator, arg) => {
      const thunkType = thunkCreator.typePrefix || thunkCreator.name || label;

      let serializedArg = "<no-arg>";

      if (arg !== undefined) {
        try {
          serializedArg = JSON.stringify(arg);
        } catch {
          serializedArg = String(arg);
        }
      }

      const key = `${thunkType}:${serializedArg}`;
      const existingRequest = inFlightRequestsRef.current.get(key);

      if (existingRequest) {
        console.debug("[AQE Request] DEDUPLICATED", {
          trigger,
          thunk: label,
          thunkType,
          arg: arg === undefined ? null : arg,
          key,
        });

        return existingRequest;
      }

      const startedAt = performance.now();

      console.info("[AQE Request] START", {
        trigger,
        thunk: label,
        thunkType,
        arg: arg === undefined ? null : arg,
        key,
      });

      let dispatched;

      try {
        dispatched = dispatch(
          arg === undefined ? thunkCreator() : thunkCreator(arg),
        );
      } catch (error) {
        console.error("[AQE Request] THROWN", {
          trigger,
          thunk: label,
          thunkType,
          arg: arg === undefined ? null : arg,
          durationMs: Math.round(performance.now() - startedAt),
          error,
        });

        throw error;
      }

      let trackedPromise;

      trackedPromise = Promise.resolve(dispatched)
        .then((action) => {
          const durationMs = Math.round(performance.now() - startedAt);
          const meta = action?.meta || {};

          const failed =
            meta.requestStatus === "rejected" || Boolean(action?.error);

          const details = {
            trigger,
            thunk: label,
            thunkType,
            arg: arg === undefined ? null : arg,
            requestId: meta.requestId || null,
            requestStatus: meta.requestStatus || null,
            durationMs,
            payload: action?.payload,
            error: action?.error || null,
          };

          if (failed) {
            console.error("[AQE Request] FAILED", details);
          } else {
            console.info("[AQE Request] COMPLETED", details);
          }

          return action;
        })
        .catch((error) => {
          console.error("[AQE Request] THROWN", {
            trigger,
            thunk: label,
            thunkType,
            arg: arg === undefined ? null : arg,
            durationMs: Math.round(performance.now() - startedAt),
            error,
          });

          throw error;
        })
        .finally(() => {
          if (inFlightRequestsRef.current.get(key) === trackedPromise) {
            inFlightRequestsRef.current.delete(key);
          }
        });

      inFlightRequestsRef.current.set(key, trackedPromise);

      return trackedPromise;
    },
    [dispatch],
  );

  // --------------------------------------------------
  // INITIAL DASHBOARD LOAD
  // --------------------------------------------------

  useEffect(() => {
    runRequest("initial-load", "fetchAccounts", fetchAccounts);
    runRequest("initial-load", "fetchEngineStatus", fetchEngineStatus);
  }, [runRequest]);

  // --------------------------------------------------
  // LOAD SELECTED ACCOUNT DATA
  // --------------------------------------------------

  useEffect(() => {
    if (
      dataAccountId === null ||
      dataAccountId === undefined ||
      dataAccountId === ""
    ) {
      return;
    }

    runRequest(
      "account-data-load",
      "fetchPositions",
      fetchPositions,
      dataAccountId,
    );

    runRequest("account-data-load", "fetchTrades", fetchTrades, dataAccountId);

    runRequest(
      "account-data-load",
      "fetchTradingUniverse",
      fetchTradingUniverse,
      dataAccountId,
    );

    runRequest(
      "account-data-load",
      "fetchBrokerAccount",
      fetchBrokerAccount,
      dataAccountId,
    );
  }, [runRequest, dataAccountId]);

  // --------------------------------------------------
  // PERIODIC DASHBOARD REFRESH
  // --------------------------------------------------

  useEffect(() => {
    const refresh = window.setInterval(() => {
      if (
        dataAccountId !== null &&
        dataAccountId !== undefined &&
        dataAccountId !== ""
      ) {
        runRequest("poll-30s", "fetchPositions", fetchPositions, dataAccountId);

        runRequest("poll-30s", "fetchTrades", fetchTrades, dataAccountId);
      }

      runRequest("poll-30s", "fetchEngineStatus", fetchEngineStatus);
    }, 30000);

    return () => window.clearInterval(refresh);
  }, [runRequest, dataAccountId]);

  // --------------------------------------------------
  // MANUAL REFRESH
  // --------------------------------------------------

  const handleRefresh = () => {
    runRequest("manual-refresh", "fetchAccounts", fetchAccounts);
    runRequest("manual-refresh", "fetchEngineStatus", fetchEngineStatus);

    if (
      dataAccountId !== null &&
      dataAccountId !== undefined &&
      dataAccountId !== ""
    ) {
      runRequest(
        "manual-refresh",
        "fetchPositions",
        fetchPositions,
        dataAccountId,
      );

      runRequest("manual-refresh", "fetchTrades", fetchTrades, dataAccountId);

      runRequest(
        "manual-refresh",
        "fetchTradingUniverse",
        fetchTradingUniverse,
        dataAccountId,
      );

      runRequest(
        "manual-refresh",
        "fetchBrokerAccount",
        fetchBrokerAccount,
        dataAccountId,
      );
    } else {
      console.warn(
        "[AQE Request] Skipping positions/trades refresh because no account ID is available.",
      );
    }
  };

  // --------------------------------------------------
  // ENGINE CONTROLS
  // --------------------------------------------------

  const handleStartEngine = async () => {
    if (!selectedAccount?.id || engineBusy) {
      return;
    }

    await runRequest(
      "engine-control:start",
      "startEngine",
      startEngine,
      selectedAccount.id,
    );

    runRequest(
      "engine-control:start-status",
      "fetchEngineStatus",
      fetchEngineStatus,
    );
  };

  const handleStopEngine = async () => {
    if (engineBusy) {
      return;
    }

    await runRequest("engine-control:stop", "stopEngine", stopEngine);

    runRequest(
      "engine-control:stop-status",
      "fetchEngineStatus",
      fetchEngineStatus,
    );
  };

  const handlePauseEngine = async () => {
    if (!engineRunning || engineBusy) {
      return;
    }

    await runRequest("engine-control:pause", "pauseEngine", pauseEngine);

    runRequest(
      "engine-control:pause-status",
      "fetchEngineStatus",
      fetchEngineStatus,
    );
  };

  const handleResumeEngine = async () => {
    if (!enginePaused || engineBusy) {
      return;
    }

    await runRequest("engine-control:resume", "resumeEngine", resumeEngine);

    runRequest(
      "engine-control:resume-status",
      "fetchEngineStatus",
      fetchEngineStatus,
    );
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
  // LIVE PIPELINE METRICS
  // --------------------------------------------------

  const pipelineMetrics = [
    { key: "received", label: "Signals Received" },
    { key: "context_failures", label: "Context Failures" },
    { key: "risk_evaluations", label: "Risk Evaluations" },
    { key: "approved", label: "Risk Approved" },
    { key: "risk_rejections", label: "Risk Rejected" },
    { key: "execution_successes", label: "Successful Executions" },
    { key: "execution_placements", label: "Orders Placed" },
    { key: "execution_partial_fills", label: "Partial Fills" },
    { key: "execution_unresolved", label: "Unresolved Executions" },
    { key: "execution_not_submitted", label: "Not Submitted" },
    { key: "execution_rejections", label: "Execution Rejections" },
    { key: "execution_failures", label: "Execution Failures" },
  ].map((metric) => ({
    ...metric,
    value:
      pipelineStats?.[metric.key] !== undefined &&
      pipelineStats?.[metric.key] !== null
        ? formatNumber(pipelineStats[metric.key])
        : "—",
  }));

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

  const margin = Number(activeAccount?.margin ?? brokerAccount?.margin ?? 0);

  const freeMargin = Number(
    activeAccount?.free_margin ??
      brokerAccount?.free_margin ??
      Math.max(totalEquity - margin, 0),
  );

  const marginLevel = Number(
    activeAccount?.margin_level ?? brokerAccount?.margin_level ?? 0,
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

        const currentPrice = Number(
          position.current_price ?? position.price_current ?? 0,
        );

        const entryPrice = Number(
          position.entry_price ??
            position.open_price ??
            position.price_open ??
            0,
        );

        const volume = Number(
          position.current_volume ?? position.volume ?? position.lots ?? 0,
        );

        const floatingProfit = Number(
          position.floating_profit ??
            position.unrealized_pnl ??
            position.profit ??
            0,
        );

        return {
          ...position,
          displaySymbol: symbol || "—",
          liveCurrentPrice: currentPrice,
          liveFloatingProfit: floatingProfit,
        };
      }),
    [positions, symbolById],
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
      openPositions.reduce(
        (sum, position) => sum + Number(position.liveFloatingProfit || 0),
        0,
      ),
    [openPositions],
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
          Number(trade.profit ?? trade.realized_profit ?? 0) > 0,
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
  // DASHBOARD ERROR
  // --------------------------------------------------

  const dashboardError = error || engine.error;

  // --------------------------------------------------
  // AUTO-DISMISS ERRORS
  // --------------------------------------------------

  useEffect(() => {
    if (!dashboardError) {
      setVisibleError(null);
      return;
    }

    setVisibleError(dashboardError);

    const timeoutId = window.setTimeout(() => {
      setVisibleError(null);
    }, 5000);

    return () => window.clearTimeout(timeoutId);
  }, [dashboardError]);

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

            <strong>
              {pipelineRunning
                ? "ACTIVE"
                : pipelineConfigured
                  ? "INACTIVE"
                  : "NOT CONFIGURED"}
            </strong>
          </div>

          <div className="engine-runtime__item">
            <span>Execution</span>

            <strong>{engine.execution ? "ACTIVE" : "—"}</strong>
          </div>
        </section>
      )}

      {/* LIVE EXECUTION PIPELINE MONITOR */}
      {(engineRunning ||
        enginePaused ||
        pipelineConfigured ||
        pipelineDetails ||
        pipelineStats) && (
        <section className="dashboard-card engine-pipeline-monitor">
          <div className="card-header">
            <div>
              <span>AUTOMATED TRADING</span>
              <h2>Live Execution Monitor</h2>
            </div>

            <FaBolt />
          </div>

          <div className="pipeline-monitor-status">
            <span
              className={`pipeline-status-dot ${
                pipelineRunning ? "pipeline-status-dot--active" : ""
              }`}
            />

            <strong>{pipelineStatusLabel}</strong>

            <span className="pipeline-monitor-description">
              Strategy → Risk Engine → Execution → MT5
            </span>
          </div>

          {pipelineStats ? (
            <div className="pipeline-metrics-grid">
              {pipelineMetrics.map((metric) => (
                <div className="pipeline-metric" key={metric.key}>
                  <span>{metric.label}</span>
                  <strong>{metric.value}</strong>
                </div>
              ))}
            </div>
          ) : (
            <div className="empty-state">
              Pipeline statistics have not yet been returned by the engine.
            </div>
          )}

          {lastContextFailure && (
            <div className="pipeline-context-error">
              <h3>Last Risk Context Failure</h3>

              <div>
                <span>Signal ID</span>
                <strong>{lastContextFailure.signal_id || "—"}</strong>
              </div>

              <div>
                <span>Strategy</span>
                <strong>
                  {lastContextFailure.strategy ||
                    lastContextFailure.strategy_id ||
                    "—"}
                </strong>
              </div>

              <div>
                <span>Symbol / Timeframe</span>
                <strong>
                  {[lastContextFailure.symbol, lastContextFailure.timeframe]
                    .filter(Boolean)
                    .join(" / ") || "—"}
                </strong>
              </div>

              <div>
                <span>Exception</span>
                <strong>{lastContextFailure.exception_type || "—"}</strong>
              </div>

              <p>
                {lastContextFailure.message ||
                  "No exception message was supplied."}
              </p>

              {lastContextFailure.cause && (
                <p>
                  Underlying cause: {lastContextFailure.cause_type || "Error"}:{" "}
                  {lastContextFailure.cause}
                </p>
              )}
            </div>
          )}
        </section>
      )}

      {/* ERROR */}
      {visibleError && (
        <div className="dashboard-error">
          {typeof visibleError === "string"
            ? visibleError
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

                  const normalizedDirection = String(direction).toUpperCase();
                  const isBuy =
                    normalizedDirection === "BUY" ||
                    normalizedDirection === "LONG";

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
                  trade.profit ?? trade.realized_profit ?? trade.pnl ?? 0,
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
