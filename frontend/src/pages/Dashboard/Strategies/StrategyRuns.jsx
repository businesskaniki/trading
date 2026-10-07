import { useCallback, useEffect, useMemo, useState } from "react";
import {
  FaCheckCircle,
  FaClock,
  FaExclamationCircle,
  FaMinus,
  FaPlus,
  FaPowerOff,
  FaRobot,
  FaSave,
  FaSyncAlt,
  FaTimes,
  FaTimesCircle,
} from "react-icons/fa";
import { useDispatch, useSelector } from "react-redux";

import {
  disableStrategyRun,
  enableStrategyRun,
  fetchStrategyRuns,
  updateStrategyRun,
} from "../../../redux/dashboard/strategyRuns/strategyRunsThunks";

import { fetchTradingUniverse } from "../../../redux/dashboard/symbols/symbolsThunks";

import "../../../css/strategyRuns.css";

const getStatusClass = (status) => {
  if (!status) {
    return "unknown";
  }

  return String(status).trim().toLowerCase().replace(/\s+/g, "-");
};

const getStatusIcon = (status) => {
  const normalized = String(status || "")
    .trim()
    .toLowerCase();

  if (["running", "active", "started"].includes(normalized)) {
    return <FaClock />;
  }

  if (["completed", "complete", "success", "successful"].includes(normalized)) {
    return <FaCheckCircle />;
  }

  if (["failed", "error"].includes(normalized)) {
    return <FaExclamationCircle />;
  }

  if (["stopped", "cancelled", "canceled"].includes(normalized)) {
    return <FaTimesCircle />;
  }

  return null;
};

const formatDateTime = (value) => {
  if (!value) {
    return "-";
  }

  const date = new Date(value);

  if (Number.isNaN(date.getTime())) {
    return "-";
  }

  return date.toLocaleString();
};

const normalizeStatus = (status) => {
  return String(status || "")
    .trim()
    .toLowerCase();
};

/**
 * Extract the broker symbol name from an account-symbol object.
 *
 * The trading-universe endpoint may expose the symbol under different
 * property names depending on the backend response schema.
 */
const getSymbolName = (item) => {
  if (typeof item === "string") {
    return item;
  }

  if (!item || typeof item !== "object") {
    return null;
  }

  const candidates = [
    item.symbol,
    item.name,
    item.broker_symbol,
    item.symbol_name,
    item.code,
  ];

  const value = candidates.find(
    (candidate) => typeof candidate === "string" && candidate.trim().length > 0,
  );

  return value ? value.trim() : null;
};

const normalizeSymbolName = (value) => {
  if (typeof value !== "string") {
    return "";
  }

  return value.trim().toUpperCase();
};

const StrategyRuns = () => {
  const dispatch = useDispatch();

  const {
    items: strategyRuns,
    loading,
    error,
    mutationLoading,
    mutationError,
  } = useSelector((state) => state.strategyRuns);

  const {
    selectedSymbols,
    selectedAccountId,
    loading: symbolsLoading,
    error: symbolsError,
  } = useSelector((state) => state.symbols);

  const [actionStrategyId, setActionStrategyId] = useState(null);

  const [symbolEditorOpen, setSymbolEditorOpen] = useState(false);
  const [editingStrategy, setEditingStrategy] = useState(null);
  const [editingSymbols, setEditingSymbols] = useState([]);
  const [symbolSaveError, setSymbolSaveError] = useState(null);

  const runs = Array.isArray(strategyRuns) ? strategyRuns : [];

  const availableAccountSymbols = Array.isArray(selectedSymbols)
    ? selectedSymbols
    : [];

  const loadRuns = useCallback(() => {
    dispatch(fetchStrategyRuns());
  }, [dispatch]);

  useEffect(() => {
    loadRuns();
  }, [loadRuns]);

  const summary = useMemo(() => {
    let running = 0;
    let completed = 0;
    let enabled = 0;
    let disabled = 0;
    let totalTrades = 0;

    for (const run of runs) {
      const status = normalizeStatus(run.status);

      if (status === "running") {
        running += 1;
      }

      if (["completed", "complete", "success", "successful"].includes(status)) {
        completed += 1;
      }

      if (run.enabled) {
        enabled += 1;
      } else {
        disabled += 1;
      }

      totalTrades += Number(run.total_trades || 0);
    }

    return {
      total: runs.length,
      running,
      completed,
      enabled,
      disabled,
      totalTrades,
    };
  }, [runs]);

  const handleToggleStrategy = async (run) => {
    if (!run?.id || mutationLoading || actionStrategyId) {
      return;
    }

    setActionStrategyId(run.id);

    try {
      if (run.enabled) {
        await dispatch(disableStrategyRun(run.id)).unwrap();
      } else {
        await dispatch(enableStrategyRun(run.id)).unwrap();
      }
    } catch {
      // The thunk stores the mutation error in Redux.
    } finally {
      setActionStrategyId(null);
    }
  };

  /**
   * Open the symbol editor for a strategy.
   *
   * The trading universe is loaded specifically for this strategy's
   * account so symbols from another account cannot accidentally appear.
   */
  const handleOpenSymbolEditor = async (run) => {
    if (!run?.id || !run?.account_id) {
      return;
    }

    setSymbolSaveError(null);
    setEditingStrategy(run);
    setEditingSymbols(
      Array.isArray(run.symbols)
        ? run.symbols.filter(
            (symbol) => typeof symbol === "string" && symbol.trim().length > 0,
          )
        : [],
    );
    setSymbolEditorOpen(true);

    try {
      await dispatch(fetchTradingUniverse(run.account_id)).unwrap();
    } catch {
      // symbolsError from Redux is displayed inside the modal.
    }
  };

  const handleCloseSymbolEditor = () => {
    if (mutationLoading) {
      return;
    }

    setSymbolEditorOpen(false);
    setEditingStrategy(null);
    setEditingSymbols([]);
    setSymbolSaveError(null);
  };

  const handleAddSymbol = (symbol) => {
    const symbolName = getSymbolName(symbol);

    if (!symbolName) {
      return;
    }

    setEditingSymbols((current) => {
      const normalized = normalizeSymbolName(symbolName);

      const alreadyAssigned = current.some(
        (assignedSymbol) => normalizeSymbolName(assignedSymbol) === normalized,
      );

      if (alreadyAssigned) {
        return current;
      }

      return [...current, symbolName];
    });

    setSymbolSaveError(null);
  };

  const handleRemoveSymbol = (symbol) => {
    const normalized = normalizeSymbolName(symbol);

    setEditingSymbols((current) =>
      current.filter(
        (assignedSymbol) => normalizeSymbolName(assignedSymbol) !== normalized,
      ),
    );

    setSymbolSaveError(null);
  };

  const handleSaveSymbols = async () => {
    if (!editingStrategy?.id) {
      return;
    }

    setSymbolSaveError(null);

    try {
      await dispatch(
        updateStrategyRun({
          strategyRunId: editingStrategy.id,
          payload: {
            symbols: editingSymbols,
          },
        }),
      ).unwrap();

      setSymbolEditorOpen(false);
      setEditingStrategy(null);
      setEditingSymbols([]);

      /*
       * The update thunk already updates the strategy in Redux.
       * Reloading ensures the table reflects the authoritative backend
       * representation as well.
       */
      await dispatch(fetchStrategyRuns()).unwrap();
    } catch (error) {
      setSymbolSaveError(
        typeof error === "string"
          ? error
          : "Failed to update strategy symbols.",
      );
    }
  };

  const assignedSymbolKeys = useMemo(
    () => new Set(editingSymbols.map((symbol) => normalizeSymbolName(symbol))),
    [editingSymbols],
  );

  const availableSymbols = useMemo(() => {
    if (!Array.isArray(availableAccountSymbols)) {
      return [];
    }

    return availableAccountSymbols.filter((symbol) => {
      const symbolName = getSymbolName(symbol);

      if (!symbolName) {
        return false;
      }

      return !assignedSymbolKeys.has(normalizeSymbolName(symbolName));
    });
  }, [availableAccountSymbols, assignedSymbolKeys]);

  const universeBelongsToStrategyAccount =
    editingStrategy?.account_id &&
    selectedAccountId &&
    String(editingStrategy.account_id) === String(selectedAccountId);

  return (
    <main className="strategy-runs-page">
      <header className="strategy-runs-header">
        <div className="strategy-runs-header__content">
          <span className="dashboard-eyebrow">AUTOMATION MONITOR</span>

          <h1>Strategy Runs</h1>

          <p>
            Monitor deployed strategies, their assigned symbols, execution
            state, and trading performance.
          </p>
        </div>

        <button
          type="button"
          className="strategy-runs-refresh"
          onClick={loadRuns}
          disabled={loading || mutationLoading}
        >
          <FaSyncAlt className={loading ? "strategy-spin" : ""} />

          <span>{loading ? "Refreshing..." : "Refresh"}</span>
        </button>
      </header>

      {error && (
        <div className="dashboard-error strategy-runs-error">
          <FaExclamationCircle />

          <span>{error}</span>
        </div>
      )}

      {mutationError && (
        <div className="dashboard-error strategy-runs-error">
          <FaExclamationCircle />

          <span>{mutationError}</span>
        </div>
      )}

      <section className="strategy-runs-summary">
        <div className="strategy-runs-summary__item">
          <span>Total Strategies</span>
          <strong>{summary.total}</strong>
        </div>

        <div className="strategy-runs-summary__item">
          <span>Active</span>
          <strong>{summary.enabled}</strong>
        </div>

        <div className="strategy-runs-summary__item">
          <span>Disabled</span>
          <strong>{summary.disabled}</strong>
        </div>

        <div className="strategy-runs-summary__item">
          <span>Running</span>
          <strong>{summary.running}</strong>
        </div>

        <div className="strategy-runs-summary__item">
          <span>Total Trades</span>
          <strong>{summary.totalTrades}</strong>
        </div>
      </section>

      <section className="strategy-runs-table-wrap">
        <div className="strategy-runs-table-header">
          <div>
            <span className="strategy-runs-table-eyebrow">
              STRATEGY ASSIGNMENTS
            </span>

            <h2>Strategy activity</h2>
          </div>

          <span className="strategy-runs-count">
            {runs.length} {runs.length === 1 ? "strategy" : "strategies"}
          </span>
        </div>

        <div className="strategy-runs-table-scroll">
          <table>
            <thead>
              <tr>
                <th>Strategy</th>
                <th>Type</th>
                <th>Enabled</th>
                <th>Status</th>
                <th>Symbols</th>
                <th>Timeframe</th>
                <th>Trades</th>
                <th>Started</th>
                <th>Ended</th>
                <th>Action</th>
              </tr>
            </thead>

            <tbody>
              {loading && (
                <tr>
                  <td colSpan="10" className="strategy-empty">
                    <FaSyncAlt className="strategy-spin" />

                    <strong>Loading strategies...</strong>

                    <span>
                      Retrieving the latest strategy assignments and execution
                      history.
                    </span>
                  </td>
                </tr>
              )}

              {!loading && runs.length === 0 && (
                <tr>
                  <td colSpan="10" className="strategy-empty">
                    <FaRobot />

                    <strong>No strategies assigned</strong>

                    <span>
                      Existing strategy assignments will appear here when they
                      are available.
                    </span>
                  </td>
                </tr>
              )}

              {!loading &&
                runs.map((run) => {
                  const status = run.status || "UNKNOWN";
                  const statusClass = getStatusClass(status);
                  const statusIcon = getStatusIcon(status);
                  const isProcessing = actionStrategyId === run.id;

                  return (
                    <tr key={run.id}>
                      <td>
                        <div className="strategy-name-cell">
                          <strong>
                            {run.strategy_name || "Unknown Strategy"}
                          </strong>

                          {run.run_name && <span>{run.run_name}</span>}

                          {run.strategy_version && (
                            <span>v{run.strategy_version}</span>
                          )}
                        </div>
                      </td>

                      <td>
                        <span className="strategy-type">
                          {run.run_type || "-"}
                        </span>
                      </td>

                      <td>
                        <span
                          className={`strategy-enabled ${
                            run.enabled
                              ? "strategy-enabled--active"
                              : "strategy-enabled--disabled"
                          }`}
                        >
                          <span className="strategy-enabled__dot" />

                          {run.enabled ? "Enabled" : "Disabled"}
                        </span>
                      </td>

                      <td>
                        <span
                          className={`strategy-status strategy-status--${statusClass}`}
                        >
                          {statusIcon}

                          <span>{status}</span>
                        </span>
                      </td>

                      <td>
                        <div className="strategy-symbols">
                          {Array.isArray(run.symbols) &&
                          run.symbols.length > 0 ? (
                            run.symbols.map((symbol) => (
                              <span
                                className="strategy-symbol"
                                key={`${run.id}-${symbol}`}
                              >
                                {symbol}
                              </span>
                            ))
                          ) : (
                            <span>-</span>
                          )}

                          <button
                            type="button"
                            className="strategy-symbol-manage"
                            onClick={() => handleOpenSymbolEditor(run)}
                            disabled={mutationLoading}
                            title="Manage strategy symbols"
                          >
                            <FaPlus />

                            <span>Manage</span>
                          </button>
                        </div>
                      </td>

                      <td>
                        <span className="strategy-timeframe">
                          {run.timeframe || "-"}
                        </span>
                      </td>

                      <td>
                        <strong className="strategy-trades">
                          {Number(run.total_trades || 0)}
                        </strong>
                      </td>

                      <td>
                        <span className="strategy-date">
                          {formatDateTime(run.started_at)}
                        </span>
                      </td>

                      <td>
                        <span className="strategy-date">
                          {formatDateTime(run.ended_at)}
                        </span>
                      </td>

                      <td>
                        <button
                          type="button"
                          className={`strategy-action ${
                            run.enabled
                              ? "strategy-action--disable"
                              : "strategy-action--enable"
                          }`}
                          onClick={() => handleToggleStrategy(run)}
                          disabled={
                            mutationLoading ||
                            Boolean(actionStrategyId && !isProcessing)
                          }
                          title={
                            run.enabled
                              ? "Deactivate strategy"
                              : "Activate strategy"
                          }
                        >
                          {isProcessing ? (
                            <FaSyncAlt className="strategy-spin" />
                          ) : (
                            <FaPowerOff />
                          )}

                          <span>
                            {isProcessing
                              ? run.enabled
                                ? "Disabling..."
                                : "Enabling..."
                              : run.enabled
                                ? "Disable"
                                : "Enable"}
                          </span>
                        </button>
                      </td>
                    </tr>
                  );
                })}
            </tbody>
          </table>
        </div>
      </section>

      {symbolEditorOpen && editingStrategy && (
        <div
          className="strategy-symbol-modal-backdrop"
          onMouseDown={(event) => {
            if (event.target === event.currentTarget) {
              handleCloseSymbolEditor();
            }
          }}
        >
          <section
            className="strategy-symbol-modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="strategy-symbol-modal-title"
          >
            <header className="strategy-symbol-modal__header">
              <div>
                <span className="strategy-runs-table-eyebrow">
                  SYMBOL ASSIGNMENT
                </span>

                <h2 id="strategy-symbol-modal-title">
                  {editingStrategy.strategy_name || "Strategy"}
                </h2>

                {editingStrategy.run_name && <p>{editingStrategy.run_name}</p>}
              </div>

              <button
                type="button"
                className="strategy-symbol-modal__close"
                onClick={handleCloseSymbolEditor}
                disabled={mutationLoading}
                aria-label="Close symbol manager"
              >
                <FaTimes />
              </button>
            </header>

            <div className="strategy-symbol-modal__body">
              {symbolSaveError && (
                <div className="dashboard-error strategy-symbol-modal__error">
                  <FaExclamationCircle />

                  <span>{symbolSaveError}</span>
                </div>
              )}

              {symbolsError && (
                <div className="dashboard-error strategy-symbol-modal__error">
                  <FaExclamationCircle />

                  <span>{symbolsError}</span>
                </div>
              )}

              <section className="strategy-symbol-section">
                <div className="strategy-symbol-section__header">
                  <div>
                    <h3>Assigned symbols</h3>

                    <p>Symbols currently assigned to this strategy.</p>
                  </div>

                  <span className="strategy-symbol-section__count">
                    {editingSymbols.length}
                  </span>
                </div>

                <div className="strategy-symbol-assigned">
                  {editingSymbols.length > 0 ? (
                    editingSymbols.map((symbol) => (
                      <div
                        className="strategy-symbol-assigned__item"
                        key={symbol}
                      >
                        <span>{symbol}</span>

                        <button
                          type="button"
                          onClick={() => handleRemoveSymbol(symbol)}
                          disabled={mutationLoading}
                          title={`Remove ${symbol}`}
                          aria-label={`Remove ${symbol}`}
                        >
                          <FaMinus />
                        </button>
                      </div>
                    ))
                  ) : (
                    <div className="strategy-symbol-empty">
                      <FaRobot />

                      <span>
                        No symbols are currently assigned to this strategy.
                      </span>
                    </div>
                  )}
                </div>
              </section>

              <section className="strategy-symbol-section">
                <div className="strategy-symbol-section__header">
                  <div>
                    <h3>Available account symbols</h3>

                    <p>
                      Only symbols selected for this trading account can be
                      assigned to the strategy.
                    </p>
                  </div>

                  {symbolsLoading && (
                    <FaSyncAlt className="strategy-spin strategy-symbol-loading" />
                  )}
                </div>

                {!symbolsLoading && !universeBelongsToStrategyAccount && (
                  <div className="strategy-symbol-empty">
                    <FaSyncAlt className="strategy-spin" />

                    <span>Loading the account trading universe...</span>
                  </div>
                )}

                {!symbolsLoading &&
                  universeBelongsToStrategyAccount &&
                  availableSymbols.length === 0 && (
                    <div className="strategy-symbol-empty">
                      <FaCheckCircle />

                      <span>
                        All selected account symbols are already assigned to
                        this strategy.
                      </span>
                    </div>
                  )}

                {!symbolsLoading &&
                  universeBelongsToStrategyAccount &&
                  availableSymbols.length > 0 && (
                    <div className="strategy-symbol-available">
                      {availableSymbols.map((symbol) => {
                        const symbolName = getSymbolName(symbol);

                        return (
                          <button
                            type="button"
                            className="strategy-symbol-available__item"
                            key={
                              symbol?.id || symbolName || JSON.stringify(symbol)
                            }
                            onClick={() => handleAddSymbol(symbol)}
                            disabled={mutationLoading}
                          >
                            <span>{symbolName}</span>

                            <FaPlus />
                          </button>
                        );
                      })}
                    </div>
                  )}
              </section>
            </div>

            <footer className="strategy-symbol-modal__footer">
              <button
                type="button"
                className="strategy-symbol-modal__button strategy-symbol-modal__button--cancel"
                onClick={handleCloseSymbolEditor}
                disabled={mutationLoading}
              >
                <FaTimes />

                <span>Cancel</span>
              </button>

              <button
                type="button"
                className="strategy-symbol-modal__button strategy-symbol-modal__button--save"
                onClick={handleSaveSymbols}
                disabled={
                  mutationLoading ||
                  symbolsLoading ||
                  !universeBelongsToStrategyAccount
                }
              >
                {mutationLoading ? (
                  <FaSyncAlt className="strategy-spin" />
                ) : (
                  <FaSave />
                )}

                <span>{mutationLoading ? "Saving..." : "Save Changes"}</span>
              </button>
            </footer>
          </section>
        </div>
      )}
    </main>
  );
};

export default StrategyRuns;
