import { useCallback, useEffect, useMemo, useState } from "react";
import { useDispatch, useSelector } from "react-redux";
import {
  FaCalendarAlt,
  FaChartLine,
  FaCheckCircle,
  FaClock,
  FaPlay,
  FaPlus,
  FaRedo,
  FaStop,
  FaTrash,
  FaWallet,
} from "react-icons/fa";

import {
  clearBacktestCreateError,
  clearBacktestDeleteError,
  clearBacktestDetailError,
  clearBacktestStartError,
  clearBacktestStopError,
  clearBacktestingError,
  clearSelectedBacktest,
  setSelectedBacktest,
} from "../../../redux/dashboard/backtesting/backtestingSlice";

import {
  createBacktest,
  deleteBacktest,
  fetchBacktest,
  fetchBacktests,
  startBacktest,
  stopBacktest,
} from "../../../redux/dashboard/backtesting/backtestingThunks";

import "../../../css/backtesting.css";

/* ========================================================================== */
/* Helpers                                                                    */
/* ========================================================================== */

const getAccountId = (account) => {
  return account?.id || account?.account_id || null;
};

const getAccountName = (account) => {
  if (!account) {
    return "Trading Account";
  }

  return (
    account.account_name ||
    account.name ||
    account.login ||
    account.account_login ||
    "Trading Account"
  );
};

const getBacktestId = (backtest) => {
  return backtest?.backtest_id || backtest?.id || null;
};

const getBacktestConfig = (backtest) => {
  return backtest?.config || {};
};

const getBacktestRun = (backtest) => {
  return backtest?.run || {};
};

const getBacktestPortfolio = (backtest) => {
  return backtest?.portfolio || {};
};

const getBacktestStatus = (backtest) => {
  if (!backtest) {
    return "UNKNOWN";
  }

  return String(backtest.status || "UNKNOWN").toUpperCase();
};

const isRunningStatus = (status) => {
  return ["RUNNING", "STARTING", "IN_PROGRESS"].includes(status);
};

const isCompletedStatus = (status) => {
  return ["COMPLETED", "COMPLETE", "FINISHED"].includes(status);
};

const isStoppedStatus = (status) => {
  return ["STOPPED", "CANCELLED", "CANCELED"].includes(status);
};

const isFailedStatus = (status) => {
  return ["FAILED", "ERROR"].includes(status);
};

const formatDate = (value) => {
  if (!value) {
    return "—";
  }

  const date = new Date(value);

  if (Number.isNaN(date.getTime())) {
    return String(value);
  }

  return date.toLocaleString();
};

const formatMoney = (value) => {
  if (value === null || value === undefined || value === "") {
    return "—";
  }

  const numericValue = Number(value);

  if (!Number.isFinite(numericValue)) {
    return String(value);
  }

  return numericValue.toLocaleString(undefined, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
};

const formatNumber = (value) => {
  if (value === null || value === undefined || value === "") {
    return "0";
  }

  const numericValue = Number(value);

  if (!Number.isFinite(numericValue)) {
    return String(value);
  }

  return numericValue.toLocaleString();
};

const formatSymbols = (symbols) => {
  if (!Array.isArray(symbols) || symbols.length === 0) {
    return "—";
  }

  return symbols.join(", ");
};

/* ========================================================================== */
/* Component                                                                  */
/* ========================================================================== */

const Backtesting = () => {
  const dispatch = useDispatch();

  /* ---------------------------------------------------------------------- */
  /* Redux                                                                   */
  /* ---------------------------------------------------------------------- */

  const accountsState = useSelector(
    (state) => state.tradingAccounts || state.accounts || {},
  );

  const backtestingState = useSelector((state) => state.backtesting || {});

  const accounts = useMemo(() => {
    if (Array.isArray(accountsState.items)) {
      return accountsState.items;
    }

    if (Array.isArray(accountsState.accounts)) {
      return accountsState.accounts;
    }

    return [];
  }, [accountsState.items, accountsState.accounts]);

  const {
    items = [],
    selected = null,
    loading = false,
    detailLoading = false,
    creating = false,
    startingId = null,
    stoppingId = null,
    deletingId = null,
    error = null,
    detailError = null,
    createError = null,
    startError = null,
    stopError = null,
    deleteError = null,
  } = backtestingState;

  /* ---------------------------------------------------------------------- */
  /* Configuration                                                           */
  /* ---------------------------------------------------------------------- */

  const [accountId, setAccountId] = useState("");
  const [initialBalance, setInitialBalance] = useState("");
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const [closePositionsAtEnd, setClosePositionsAtEnd] = useState(true);

  /* ---------------------------------------------------------------------- */
  /* UI state                                                                */
  /* ---------------------------------------------------------------------- */

  const [showConfiguration, setShowConfiguration] = useState(true);
  const [actionError, setActionError] = useState(null);

  /* ====================================================================== */
  /* INITIAL LOAD                                                           */
  /* ====================================================================== */

  useEffect(() => {
    dispatch(fetchBacktests());
  }, [dispatch]);

  /* ====================================================================== */
  /* DEFAULT ACCOUNT                                                        */
  /* ====================================================================== */

  useEffect(() => {
    if (accountId || accounts.length === 0) {
      return;
    }

    const activeAccount =
      accounts.find((account) => account?.active !== false) || accounts[0];

    const id = getAccountId(activeAccount);

    if (id) {
      setAccountId(String(id));
    }
  }, [accounts, accountId]);

  /* ====================================================================== */
  /* POLL RUNNING BACKTEST                                                  */
  /* ====================================================================== */

  useEffect(() => {
    const selectedId = getBacktestId(selected);

    if (!selectedId) {
      return undefined;
    }

    const status = getBacktestStatus(selected);

    if (!isRunningStatus(status)) {
      return undefined;
    }

    const intervalId = window.setInterval(() => {
      dispatch(fetchBacktest(selectedId));
    }, 2000);

    return () => {
      window.clearInterval(intervalId);
    };
  }, [dispatch, selected?.backtest_id, selected?.id, selected?.status]);

  /* ====================================================================== */
  /* SELECT BACKTEST                                                        */
  /* ====================================================================== */

  const handleSelectBacktest = useCallback(
    async (backtest) => {
      const backtestId = getBacktestId(backtest);

      if (!backtestId) {
        console.warn(
          "[AQE] Cannot select backtest without backtest_id.",
          backtest,
        );
        return;
      }

      setActionError(null);
      setShowConfiguration(false);

      dispatch(clearBacktestDetailError());
      dispatch(setSelectedBacktest(backtest));

      try {
        await dispatch(fetchBacktest(backtestId)).unwrap();
      } catch {
        /*
         * Redux stores the detail error.
         */
      }
    },
    [dispatch],
  );

  /* ====================================================================== */
  /* CREATE BACKTEST                                                        */
  /* ====================================================================== */

  const handleCreateBacktest = async (event) => {
    event?.preventDefault();

    console.log("[AQE] Create Backtest clicked.");

    setActionError(null);

    dispatch(clearBacktestingError());
    dispatch(clearBacktestCreateError());

    if (!accountId) {
      setActionError("Select a trading account before creating a backtest.");
      return;
    }

    if (!initialBalance) {
      setActionError("Enter the initial balance.");
      return;
    }

    if (!startDate || !endDate) {
      setActionError("Select both the start and end date.");
      return;
    }

    const start = new Date(startDate);
    const end = new Date(endDate);

    if (Number.isNaN(start.getTime()) || Number.isNaN(end.getTime())) {
      setActionError("The selected dates are invalid.");
      return;
    }

    if (start >= end) {
      setActionError("The backtest start date must be before the end date.");
      return;
    }

    const payload = {
      accountId: String(accountId),
      initialBalance: String(initialBalance),
      start: start.toISOString(),
      end: end.toISOString(),
      closePositionsAtEnd,
    };

    console.log("[AQE] Creating backtest with payload:", payload);

    try {
      const created = await dispatch(createBacktest(payload)).unwrap();

      console.log("[AQE] Backtest created:", created);

      const createdId = getBacktestId(created);

      if (createdId) {
        dispatch(setSelectedBacktest(created));
        setShowConfiguration(false);

        try {
          const refreshed = await dispatch(fetchBacktest(createdId)).unwrap();

          if (refreshed) {
            dispatch(setSelectedBacktest(refreshed));
          }
        } catch {
          /*
           * Creation succeeded even if detail refresh fails.
           */
        }
      } else {
        setActionError(
          "The backtest was created, but the server response did not contain a backtest_id.",
        );
      }

      await dispatch(fetchBacktests()).unwrap();
    } catch (error) {
      console.error("[AQE] Create backtest failed:", error);

      setActionError(
        typeof error === "string" ? error : "Failed to create the backtest.",
      );
    }
  };

  /* ====================================================================== */
  /* START BACKTEST                                                         */
  /* ====================================================================== */

  const handleStartBacktest = async (backtest) => {
    const backtestId = getBacktestId(backtest);

    if (!backtestId) {
      console.warn(
        "[AQE] Cannot start backtest without backtest_id.",
        backtest,
      );
      return;
    }

    console.log("[AQE] Starting backtest:", backtestId);

    setActionError(null);
    dispatch(clearBacktestStartError());

    try {
      const started = await dispatch(startBacktest(backtestId)).unwrap();

      console.log("[AQE] Backtest started:", started);

      if (started) {
        dispatch(setSelectedBacktest(started));
      }

      await dispatch(fetchBacktests()).unwrap();

      const refreshed = await dispatch(fetchBacktest(backtestId)).unwrap();

      if (refreshed) {
        dispatch(setSelectedBacktest(refreshed));
      }
    } catch (error) {
      console.error("[AQE] Start backtest failed:", error);

      setActionError(
        typeof error === "string" ? error : "Failed to start the backtest.",
      );
    }
  };

  /* ====================================================================== */
  /* STOP BACKTEST                                                          */
  /* ====================================================================== */

  const handleStopBacktest = async (backtest) => {
    const backtestId = getBacktestId(backtest);

    if (!backtestId) {
      console.warn("[AQE] Cannot stop backtest without backtest_id.", backtest);
      return;
    }

    console.log("[AQE] Stopping backtest:", backtestId);

    setActionError(null);
    dispatch(clearBacktestStopError());

    try {
      const stopped = await dispatch(stopBacktest(backtestId)).unwrap();

      console.log("[AQE] Backtest stopped:", stopped);

      if (stopped) {
        dispatch(setSelectedBacktest(stopped));
      }

      await dispatch(fetchBacktests()).unwrap();

      const refreshed = await dispatch(fetchBacktest(backtestId)).unwrap();

      if (refreshed) {
        dispatch(setSelectedBacktest(refreshed));
      }
    } catch (error) {
      console.error("[AQE] Stop backtest failed:", error);

      setActionError(
        typeof error === "string" ? error : "Failed to stop the backtest.",
      );
    }
  };

  /* ====================================================================== */
  /* DELETE BACKTEST                                                        */
  /* ====================================================================== */

  const handleDeleteBacktest = async (backtest) => {
    const backtestId = getBacktestId(backtest);

    if (!backtestId) {
      console.warn(
        "[AQE] Cannot delete backtest without backtest_id.",
        backtest,
      );
      return;
    }

    const status = getBacktestStatus(backtest);

    if (isRunningStatus(status)) {
      setActionError(
        "A running backtest must be stopped before it can be deleted.",
      );
      return;
    }

    const confirmed = window.confirm(
      "Delete this backtest? This action cannot be undone.",
    );

    if (!confirmed) {
      return;
    }

    console.log("[AQE] Deleting backtest:", backtestId);

    setActionError(null);
    dispatch(clearBacktestDeleteError());

    try {
      await dispatch(deleteBacktest(backtestId)).unwrap();

      dispatch(clearSelectedBacktest());

      setShowConfiguration(true);

      await dispatch(fetchBacktests()).unwrap();
    } catch (error) {
      console.error("[AQE] Delete backtest failed:", error);

      setActionError(
        typeof error === "string" ? error : "Failed to delete the backtest.",
      );
    }
  };

  /* ====================================================================== */
  /* REFRESH                                                                */
  /* ====================================================================== */

  const handleRefresh = async () => {
    console.log("[AQE] Refreshing backtests.");

    setActionError(null);
    dispatch(clearBacktestingError());

    try {
      await dispatch(fetchBacktests()).unwrap();

      const selectedId = getBacktestId(selected);

      if (selectedId) {
        const refreshed = await dispatch(fetchBacktest(selectedId)).unwrap();

        if (refreshed) {
          dispatch(setSelectedBacktest(refreshed));
        }
      }
    } catch {
      /*
       * Redux owns the error state.
       */
    }
  };

  /* ====================================================================== */
  /* DERIVED STATE                                                          */
  /* ====================================================================== */

  const selectedBacktestId = getBacktestId(selected);

  const selectedConfig = getBacktestConfig(selected);

  const selectedRun = getBacktestRun(selected);

  const selectedPortfolio = getBacktestPortfolio(selected);

  const selectedStatus = getBacktestStatus(selected);

  const selectedAccount = accounts.find(
    (account) =>
      String(getAccountId(account)) ===
      String(
        selectedConfig.account_id ||
          selected?.account_id ||
          selected?.accountId ||
          "",
      ),
  );

  const displayedError =
    actionError ||
    error ||
    detailError ||
    createError ||
    startError ||
    stopError ||
    deleteError;

  const createDisabled = creating || accounts.length === 0;

  /* ====================================================================== */
  /* RENDER                                                                 */
  /* ====================================================================== */

  return (
    <div className="backtesting-page">
      {/* ================================================================== */}
      {/* HEADER                                                             */}
      {/* ================================================================== */}

      <div className="backtesting-header">
        <div>
          <div className="backtesting-title-row">
            <div className="backtesting-title-icon">
              <FaChartLine />
            </div>

            <div>
              <h1>Backtesting</h1>

              <p>
                Test your configured strategies against historical market data.
              </p>
            </div>
          </div>
        </div>

        <div className="backtesting-header-actions">
          <button
            type="button"
            className="backtesting-button secondary"
            onClick={handleRefresh}
            disabled={loading || detailLoading}
          >
            <FaRedo className={loading ? "backtesting-spin" : ""} />
            Refresh
          </button>

          <button
            type="button"
            className="backtesting-button primary"
            onClick={() => {
              setShowConfiguration(true);
              setActionError(null);
              dispatch(clearSelectedBacktest());
            }}
          >
            <FaPlus />
            New Backtest
          </button>
        </div>
      </div>

      {/* ================================================================== */}
      {/* ERROR                                                              */}
      {/* ================================================================== */}

      {displayedError && (
        <div className="backtesting-error">
          <span>{displayedError}</span>

          <button
            type="button"
            onClick={() => {
              setActionError(null);

              dispatch(clearBacktestingError());

              dispatch(clearBacktestDetailError());

              dispatch(clearBacktestCreateError());

              dispatch(clearBacktestStartError());

              dispatch(clearBacktestStopError());

              dispatch(clearBacktestDeleteError());
            }}
          >
            Dismiss
          </button>
        </div>
      )}

      {/* ================================================================== */}
      {/* MAIN                                                               */}
      {/* ================================================================== */}

      <div className="backtesting-layout">
        {/* ================================================================ */}
        {/* SIDEBAR                                                          */}
        {/* ================================================================ */}

        <aside className="backtesting-sidebar">
          <div className="backtesting-sidebar-header">
            <div>
              <span className="backtesting-section-label">Backtests</span>

              <strong>{items.length}</strong>
            </div>

            <FaClock />
          </div>

          {loading && items.length === 0 ? (
            <div className="backtesting-sidebar-empty">
              <FaRedo className="backtesting-spin" />

              <span>Loading backtests...</span>
            </div>
          ) : items.length === 0 ? (
            <div className="backtesting-sidebar-empty">
              <FaChartLine />

              <strong>No backtests yet</strong>

              <span>Create your first historical simulation.</span>
            </div>
          ) : (
            <div className="backtesting-list">
              {items.map((backtest) => {
                const backtestId = getBacktestId(backtest);

                const config = getBacktestConfig(backtest);

                const status = getBacktestStatus(backtest);

                const isSelected =
                  selectedBacktestId &&
                  String(selectedBacktestId) === String(backtestId);

                const backtestAccount = accounts.find(
                  (account) =>
                    String(getAccountId(account)) ===
                    String(config.account_id || ""),
                );

                return (
                  <button
                    type="button"
                    key={backtestId}
                    className={`backtesting-list-item ${
                      isSelected ? "selected" : ""
                    }`}
                    onClick={() => handleSelectBacktest(backtest)}
                  >
                    <div className="backtesting-list-item-top">
                      <strong>{getAccountName(backtestAccount)}</strong>

                      <span
                        className={`backtesting-status ${status.toLowerCase()}`}
                      >
                        {status}
                      </span>
                    </div>

                    <div className="backtesting-list-item-meta">
                      <span>{formatDate(config.start)}</span>

                      <span>
                        {backtestId ? String(backtestId).slice(0, 8) : "—"}
                      </span>
                    </div>
                  </button>
                );
              })}
            </div>
          )}
        </aside>

        {/* ================================================================ */}
        {/* CONTENT                                                          */}
        {/* ================================================================ */}

        <main className="backtesting-content">
          {/* ============================================================ */}
          {/* CONFIGURATION                                                  */}
          {/* ============================================================ */}

          {showConfiguration && (
            <section className="backtesting-card">
              <div className="backtesting-card-header">
                <div>
                  <span className="backtesting-section-label">
                    Configuration
                  </span>

                  <h2>Create Backtest</h2>

                  <p>
                    The selected account determines the strategies, symbols,
                    timeframes, and instrument configuration used by the
                    backtest.
                  </p>
                </div>
              </div>

              <form
                className="backtesting-form"
                onSubmit={handleCreateBacktest}
              >
                {/* ACCOUNT */}

                <div className="backtesting-field full">
                  <label htmlFor="backtest-account">Trading Account</label>

                  <div className="backtesting-input-icon">
                    <FaWallet />

                    <select
                      id="backtest-account"
                      value={accountId}
                      onChange={(event) => setAccountId(event.target.value)}
                      disabled={creating}
                    >
                      <option value="">Select trading account</option>

                      {accounts.map((account) => {
                        const id = getAccountId(account);

                        if (!id) {
                          return null;
                        }

                        return (
                          <option key={id} value={id}>
                            {getAccountName(account)}

                            {account.login ? ` — #${account.login}` : ""}
                          </option>
                        );
                      })}
                    </select>
                  </div>

                  {accounts.length === 0 && (
                    <div className="backtesting-field-help error">
                      No trading accounts are available. Create or load a
                      trading account first.
                    </div>
                  )}
                </div>

                {/* BALANCE */}

                <div className="backtesting-field">
                  <label htmlFor="backtest-balance">Initial Balance</label>

                  <input
                    id="backtest-balance"
                    type="number"
                    min="0.01"
                    step="0.01"
                    placeholder="10000.00"
                    value={initialBalance}
                    onChange={(event) => setInitialBalance(event.target.value)}
                    disabled={creating}
                  />
                </div>

                {/* START */}

                <div className="backtesting-field">
                  <label htmlFor="backtest-start">Start Date</label>

                  <div className="backtesting-input-icon">
                    <FaCalendarAlt />

                    <input
                      id="backtest-start"
                      type="datetime-local"
                      value={startDate}
                      onChange={(event) => setStartDate(event.target.value)}
                      disabled={creating}
                    />
                  </div>
                </div>

                {/* END */}

                <div className="backtesting-field">
                  <label htmlFor="backtest-end">End Date</label>

                  <div className="backtesting-input-icon">
                    <FaCalendarAlt />

                    <input
                      id="backtest-end"
                      type="datetime-local"
                      value={endDate}
                      onChange={(event) => setEndDate(event.target.value)}
                      disabled={creating}
                    />
                  </div>
                </div>

                {/* CLOSE POSITIONS */}

                <div className="backtesting-field full">
                  <label className="backtesting-checkbox">
                    <input
                      type="checkbox"
                      checked={closePositionsAtEnd}
                      onChange={(event) =>
                        setClosePositionsAtEnd(event.target.checked)
                      }
                      disabled={creating}
                    />

                    <span>Close open positions at the end of the backtest</span>
                  </label>
                </div>

                {/* ACTIONS */}

                <div className="backtesting-form-actions">
                  <button
                    type="submit"
                    className="backtesting-button primary large"
                    disabled={createDisabled}
                  >
                    {creating ? (
                      <>
                        <FaRedo className="backtesting-spin" />
                        Creating...
                      </>
                    ) : (
                      <>
                        <FaPlus />
                        Create Backtest
                      </>
                    )}
                  </button>
                </div>
              </form>
            </section>
          )}

          {/* ============================================================ */}
          {/* SELECTED BACKTEST                                              */}
          {/* ============================================================ */}

          {selected && (
            <section className="backtesting-card">
              <div className="backtesting-card-header">
                <div>
                  <span className="backtesting-section-label">Backtest</span>

                  <h2>Simulation Details</h2>

                  <p>
                    {selectedBacktestId
                      ? `Run ${String(selectedBacktestId).slice(0, 8)}`
                      : "Selected backtest"}
                  </p>
                </div>

                <div
                  className={`backtesting-status-large ${selectedStatus.toLowerCase()}`}
                >
                  <span className="backtesting-status-dot" />

                  {selectedStatus}
                </div>
              </div>

              {/* DETAILS */}

              <div className="backtesting-details-grid">
                <div className="backtesting-detail">
                  <span className="backtesting-detail-label">Account</span>

                  <strong className="backtesting-detail-value">
                    {getAccountName(selectedAccount)}
                  </strong>
                </div>

                <div className="backtesting-detail">
                  <span className="backtesting-detail-label">
                    Initial Balance
                  </span>

                  <strong className="backtesting-detail-value">
                    {formatMoney(selectedConfig.initial_balance)}
                  </strong>
                </div>

                <div className="backtesting-detail">
                  <span className="backtesting-detail-label">Start</span>

                  <strong className="backtesting-detail-value">
                    {formatDate(selectedConfig.start)}
                  </strong>
                </div>

                <div className="backtesting-detail">
                  <span className="backtesting-detail-label">End</span>

                  <strong className="backtesting-detail-value">
                    {formatDate(selectedConfig.end)}
                  </strong>
                </div>

                <div className="backtesting-detail">
                  <span className="backtesting-detail-label">Symbols</span>

                  <strong className="backtesting-detail-value">
                    {formatSymbols(selectedConfig.symbols)}
                  </strong>
                </div>

                <div className="backtesting-detail">
                  <span className="backtesting-detail-label">Timeframes</span>

                  <strong className="backtesting-detail-value">
                    {formatSymbols(selectedConfig.timeframes)}
                  </strong>
                </div>

                <div className="backtesting-detail">
                  <span className="backtesting-detail-label">
                    Processed Candles
                  </span>

                  <strong className="backtesting-detail-value">
                    {formatNumber(selectedRun.processed_candles)}
                  </strong>
                </div>

                <div className="backtesting-detail">
                  <span className="backtesting-detail-label">Executions</span>

                  <strong className="backtesting-detail-value">
                    {formatNumber(selectedRun.executions)}
                  </strong>
                </div>

                <div className="backtesting-detail">
                  <span className="backtesting-detail-label">Balance</span>

                  <strong className="backtesting-detail-value">
                    {formatMoney(selectedPortfolio.balance)}
                  </strong>
                </div>
              </div>

              {/* ACTIONS */}

              <div className="backtesting-run-actions">
                {selectedStatus === "CREATED" && (
                  <button
                    type="button"
                    className="backtesting-button primary"
                    onClick={() => handleStartBacktest(selected)}
                    disabled={startingId === selectedBacktestId}
                  >
                    {startingId === selectedBacktestId ? (
                      <>
                        <FaRedo className="backtesting-spin" />
                        Starting...
                      </>
                    ) : (
                      <>
                        <FaPlay />
                        Start Backtest
                      </>
                    )}
                  </button>
                )}

                {isRunningStatus(selectedStatus) && (
                  <button
                    type="button"
                    className="backtesting-button danger"
                    onClick={() => handleStopBacktest(selected)}
                    disabled={stoppingId === selectedBacktestId}
                  >
                    {stoppingId === selectedBacktestId ? (
                      <>
                        <FaRedo className="backtesting-spin" />
                        Stopping...
                      </>
                    ) : (
                      <>
                        <FaStop />
                        Stop Backtest
                      </>
                    )}
                  </button>
                )}

                {!isRunningStatus(selectedStatus) && (
                  <button
                    type="button"
                    className="backtesting-button danger-outline"
                    onClick={() => handleDeleteBacktest(selected)}
                    disabled={deletingId === selectedBacktestId}
                  >
                    {deletingId === selectedBacktestId ? (
                      <>
                        <FaRedo className="backtesting-spin" />
                        Deleting...
                      </>
                    ) : (
                      <>
                        <FaTrash />
                        Delete
                      </>
                    )}
                  </button>
                )}
              </div>

              {/* RUNNING */}

              {isRunningStatus(selectedStatus) && (
                <div className="backtesting-running-panel">
                  <div className="backtesting-running-icon">
                    <FaChartLine />
                  </div>

                  <div>
                    <strong>Backtest is running</strong>

                    <span>
                      The engine is processing historical market data. This
                      panel will update automatically.
                    </span>
                  </div>

                  <FaRedo className="backtesting-spin" />
                </div>
              )}

              {/* COMPLETED */}

              {isCompletedStatus(selectedStatus) && (
                <div className="backtesting-result-placeholder">
                  <div className="backtesting-result-icon">
                    <FaCheckCircle />
                  </div>

                  <div>
                    <strong>Backtest completed</strong>

                    <span>The simulation completed successfully.</span>
                  </div>
                </div>
              )}

              {/* STOPPED */}

              {isStoppedStatus(selectedStatus) && (
                <div className="backtesting-result-placeholder stopped">
                  <div className="backtesting-result-icon">
                    <FaStop />
                  </div>

                  <div>
                    <strong>Backtest stopped</strong>

                    <span>The simulation was stopped before completion.</span>
                  </div>
                </div>
              )}

              {/* FAILED */}

              {isFailedStatus(selectedStatus) && (
                <div className="backtesting-result-placeholder failed">
                  <div className="backtesting-result-icon">
                    <FaStop />
                  </div>

                  <div>
                    <strong>Backtest failed</strong>

                    <span>
                      {selected.error ||
                        "The backtest engine reported a failure. Check the backend logs for details."}
                    </span>
                  </div>
                </div>
              )}

              {/* DETAIL LOADING */}

              {detailLoading && (
                <div className="backtesting-detail-loading">
                  <FaRedo className="backtesting-spin" />
                  Updating backtest...
                </div>
              )}

              {/* CURRENT ENGINE TIME */}

              {selectedRun.current_time && (
                <div className="backtesting-detail-loading">
                  Current simulation time:{" "}
                  {formatDate(selectedRun.current_time)}
                </div>
              )}
            </section>
          )}

          {/* ============================================================ */}
          {/* EMPTY STATE                                                     */}
          {/* ============================================================ */}

          {!selected && !showConfiguration && (
            <section className="backtesting-card backtesting-empty-state">
              <FaChartLine />

              <h2>Select a backtest</h2>

              <p>
                Choose an existing backtest from the list or create a new one.
              </p>

              <button
                type="button"
                className="backtesting-button primary"
                onClick={() => setShowConfiguration(true)}
              >
                <FaPlus />
                New Backtest
              </button>
            </section>
          )}
        </main>
      </div>
    </div>
  );
};

export default Backtesting;
