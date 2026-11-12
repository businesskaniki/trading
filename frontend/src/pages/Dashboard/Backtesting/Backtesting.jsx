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
  return ["QUEUED", "PREPARING", "RUNNING", "STARTING", "IN_PROGRESS"].includes(
    String(status || "").toUpperCase(),
  );
};

const isCompletedStatus = (status) => {
  return ["COMPLETED", "COMPLETE", "FINISHED"].includes(
    String(status || "").toUpperCase(),
  );
};

const isStoppedStatus = (status) => {
  return ["STOPPED", "CANCELLED", "CANCELED"].includes(
    String(status || "").toUpperCase(),
  );
};

const isFailedStatus = (status) => {
  return ["FAILED", "ERROR"].includes(String(status || "").toUpperCase());
};

const isDeletableStatus = (status) => {
  return (
    isCompletedStatus(status) ||
    isStoppedStatus(status) ||
    isFailedStatus(status)
  );
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
  const [actionNotice, setActionNotice] = useState(null);
  const [selectedBacktestIds, setSelectedBacktestIds] = useState([]);
  const [bulkDeleting, setBulkDeleting] = useState(false);
  const [deleteConfirmation, setDeleteConfirmation] = useState(null);

  /* ====================================================================== */
  /* INITIAL LOAD                                                           */
  /* ====================================================================== */

  useEffect(() => {
    dispatch(fetchBacktests());
  }, [dispatch]);

  useEffect(() => {
    if (!deleteConfirmation || bulkDeleting) {
      return undefined;
    }

    const handleKeyDown = (event) => {
      if (event.key === "Escape") {
        setDeleteConfirmation(null);
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [deleteConfirmation, bulkDeleting]);

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
      setActionNotice(null);
      setShowConfiguration(false);

      dispatch(clearBacktestDetailError());
      dispatch(setSelectedBacktest(backtest));

      try {
        await dispatch(fetchBacktest(backtestId)).unwrap();
      } catch {
        /* Redux stores the detail error. */
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
    setActionNotice(null);

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
          /* Creation succeeded even if detail refresh fails. */
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
    setActionNotice(null);
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
    setActionNotice(null);
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

  const handleDeleteBacktest = async (backtest, confirmed = false) => {
    const backtestId = getBacktestId(backtest);

    if (!backtestId) {
      console.warn(
        "[AQE] Cannot delete backtest without backtest_id.",
        backtest,
      );
      return;
    }

    const status = getBacktestStatus(backtest);

    if (!isDeletableStatus(status)) {
      setActionError(
        "Only completed, stopped, or failed backtests can be deleted.",
      );
      return;
    }

    if (!confirmed) {
      setDeleteConfirmation({
        type: "single",
        backtest,
        backtestId: String(backtestId),
      });
      return;
    }

    console.log("[AQE] Deleting backtest:", backtestId);

    setActionError(null);
    setActionNotice(null);
    dispatch(clearBacktestDeleteError());

    try {
      await dispatch(deleteBacktest(backtestId)).unwrap();

      setSelectedBacktestIds((current) =>
        current.filter((id) => id !== String(backtestId)),
      );

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
  /* BULK DELETE BACKTESTS                                                  */
  /* ====================================================================== */

  const handleDeleteSelectedBacktests = async (confirmed = false) => {
    const targets = items.filter((backtest) => {
      const id = getBacktestId(backtest);

      return (
        id !== null &&
        id !== undefined &&
        selectedDeletableIds.includes(String(id)) &&
        isDeletableStatus(getBacktestStatus(backtest))
      );
    });

    if (targets.length === 0) {
      setActionError(
        "Select at least one completed, stopped, or failed backtest to delete.",
      );
      return;
    }

    if (!confirmed) {
      setDeleteConfirmation({ type: "bulk", count: targets.length });
      return;
    }

    setActionError(null);
    setActionNotice(null);
    setBulkDeleting(true);
    dispatch(clearBacktestDeleteError());

    const selectedIdBeforeDelete = getBacktestId(selected);
    const deletedIds = [];
    const failures = [];

    try {
      // Delete sequentially through the existing API thunk.
      for (const backtest of targets) {
        const backtestId = String(getBacktestId(backtest));

        try {
          await dispatch(deleteBacktest(backtestId)).unwrap();
          deletedIds.push(backtestId);
        } catch (error) {
          failures.push({
            id: backtestId,
            message:
              typeof error === "string"
                ? error
                : error?.message || "Delete request failed.",
          });
        }
      }

      setSelectedBacktestIds((current) =>
        current.filter((id) => !deletedIds.includes(id)),
      );

      // Clear the detail panel only if its backtest was deleted.
      if (
        selectedIdBeforeDelete &&
        deletedIds.includes(String(selectedIdBeforeDelete))
      ) {
        dispatch(clearSelectedBacktest());
        setShowConfiguration(true);
      }

      let refreshError = null;

      try {
        await dispatch(fetchBacktests()).unwrap();
      } catch (error) {
        refreshError =
          typeof error === "string"
            ? error
            : error?.message || "The backtest list could not be refreshed.";
      }

      if (failures.length > 0) {
        const failureDetails = failures
          .slice(0, 3)
          .map(({ id, message }) => `${id.slice(0, 8)}: ${message}`)
          .join(" | ");

        const remainingFailures =
          failures.length > 3 ? ` (+${failures.length - 3} more)` : "";

        setActionError(
          `Deleted ${deletedIds.length} of ${targets.length} selected backtests. ` +
            `${failures.length} failed. ${failureDetails}${remainingFailures}` +
            (refreshError ? ` List refresh also failed: ${refreshError}` : ""),
        );
      } else if (refreshError) {
        setActionError(
          `Deleted ${deletedIds.length} backtest(s), but the list refresh failed: ${refreshError}`,
        );
      } else {
        setActionNotice(
          `Successfully deleted ${deletedIds.length} backtest(s).`,
        );
      }
    } finally {
      setBulkDeleting(false);
    }
  };

  const handleConfirmDelete = async () => {
    const confirmation = deleteConfirmation;

    if (!confirmation) {
      return;
    }

    setDeleteConfirmation(null);

    if (confirmation.type === "single") {
      await handleDeleteBacktest(confirmation.backtest, true);
      return;
    }

    await handleDeleteSelectedBacktests(true);
  };

  /* ====================================================================== */
  /* REFRESH                                                                */
  /* ====================================================================== */

  const handleRefresh = async () => {
    console.log("[AQE] Refreshing backtests.");

    setActionError(null);
    setActionNotice(null);
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
      /* Redux owns the error state. */
    }
  };

  /* ====================================================================== */
  /* DERIVED STATE                                                          */
  /* ====================================================================== */

  const deletableIds = useMemo(
    () =>
      items
        .filter((backtest) => {
          const id = getBacktestId(backtest);

          return (
            id !== null &&
            id !== undefined &&
            isDeletableStatus(getBacktestStatus(backtest))
          );
        })
        .map((backtest) => String(getBacktestId(backtest))),
    [items],
  );

  const selectedDeletableIds = useMemo(() => {
    const eligibleIds = new Set(deletableIds);

    return selectedBacktestIds.filter((id) => eligibleIds.has(id));
  }, [deletableIds, selectedBacktestIds]);

  const allDeletableSelected =
    deletableIds.length > 0 &&
    deletableIds.every((id) => selectedBacktestIds.includes(id));

  const handleToggleBacktestSelection = (backtestId, checked) => {
    const normalizedId = String(backtestId);

    setSelectedBacktestIds((current) => {
      if (checked) {
        return current.includes(normalizedId)
          ? current
          : [...current, normalizedId];
      }

      return current.filter((id) => id !== normalizedId);
    });
  };

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
            disabled={loading || detailLoading || bulkDeleting}
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
              setActionNotice(null);
              dispatch(clearSelectedBacktest());
            }}
            disabled={bulkDeleting}
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
        <div className="backtesting-error" role="alert" aria-live="polite">
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

      {actionNotice && (
        <div
          className="backtesting-result-placeholder"
          role="status"
          aria-live="polite"
        >
          <div className="backtesting-result-icon">
            <FaCheckCircle />
          </div>

          <div>
            <strong>Bulk delete complete</strong>
            <span>{actionNotice}</span>
          </div>

          <button type="button" onClick={() => setActionNotice(null)}>
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

          <div
            className="backtesting-bulk-toolbar"
            style={{
              display: "flex",
              flexDirection: "column",
              gap: "0.75rem",
              padding: "0.75rem 1rem",
              borderBottom: "1px solid rgba(128, 128, 128, 0.25)",
            }}
          >
            <label
              style={{
                display: "flex",
                alignItems: "center",
                gap: "0.5rem",
                cursor: deletableIds.length > 0 ? "pointer" : "default",
              }}
            >
              <input
                type="checkbox"
                checked={allDeletableSelected}
                disabled={deletableIds.length === 0 || bulkDeleting}
                onChange={(event) => {
                  setSelectedBacktestIds(
                    event.target.checked ? [...deletableIds] : [],
                  );
                }}
              />

              <span>Select all deletable ({deletableIds.length})</span>
            </label>

            <button
              type="button"
              className="backtesting-button danger-outline"
              onClick={handleDeleteSelectedBacktests}
              disabled={selectedDeletableIds.length === 0 || bulkDeleting}
              style={{
                width: "100%",
                justifyContent: "center",
              }}
            >
              {bulkDeleting ? (
                <>
                  <FaRedo className="backtesting-spin" />
                  Deleting selected...
                </>
              ) : (
                <>
                  <FaTrash />
                  Delete selected ({selectedDeletableIds.length})
                </>
              )}
            </button>
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
              {items.map((backtest, index) => {
                const backtestId = getBacktestId(backtest);
                const backtestIdKey =
                  backtestId !== null && backtestId !== undefined
                    ? String(backtestId)
                    : "";

                const config = getBacktestConfig(backtest);
                const status = getBacktestStatus(backtest);
                const canBulkDelete =
                  Boolean(backtestIdKey) && isDeletableStatus(status);

                const isSelected =
                  selectedBacktestId &&
                  String(selectedBacktestId) === backtestIdKey;

                const isChecked = selectedBacktestIds.includes(backtestIdKey);

                const backtestAccount = accounts.find(
                  (account) =>
                    String(getAccountId(account)) ===
                    String(config.account_id || ""),
                );

                return (
                  <div
                    key={backtestIdKey || `backtest-${index}`}
                    className="backtesting-list-row"
                    style={{
                      display: "flex",
                      alignItems: "stretch",
                      gap: "0.5rem",
                    }}
                  >
                    <label
                      title={
                        canBulkDelete
                          ? "Select this backtest for bulk deletion"
                          : "Only completed, stopped, or failed backtests can be bulk deleted"
                      }
                      style={{
                        display: "flex",
                        alignItems: "center",
                        justifyContent: "center",
                        padding: "0 0.25rem",
                        cursor: canBulkDelete ? "pointer" : "not-allowed",
                        flexShrink: 0,
                      }}
                    >
                      <input
                        type="checkbox"
                        aria-label={`Select backtest ${backtestIdKey || "without an ID"}`}
                        checked={Boolean(backtestIdKey) && isChecked}
                        disabled={!canBulkDelete || bulkDeleting}
                        onChange={(event) =>
                          handleToggleBacktestSelection(
                            backtestIdKey,
                            event.target.checked,
                          )
                        }
                      />
                    </label>

                    <button
                      type="button"
                      className={`backtesting-list-item ${
                        isSelected ? "selected" : ""
                      }`}
                      onClick={() => handleSelectBacktest(backtest)}
                      disabled={bulkDeleting}
                      style={{
                        flex: 1,
                        minWidth: 0,
                      }}
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
                          {backtestIdKey ? backtestIdKey.slice(0, 8) : "—"}
                        </span>
                      </div>
                    </button>
                  </div>
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
                    disabled={startingId === selectedBacktestId || bulkDeleting}
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
                    disabled={stoppingId === selectedBacktestId || bulkDeleting}
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
                    disabled={deletingId === selectedBacktestId || bulkDeleting}
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

      {deleteConfirmation && (
        <div
          className="backtesting-confirm-backdrop"
          role="presentation"
          onClick={(event) => {
            if (event.target === event.currentTarget && !bulkDeleting) {
              setDeleteConfirmation(null);
            }
          }}
          style={{
            position: "fixed",
            inset: 0,
            zIndex: 2000,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            padding: "1.25rem",
            background: "rgba(15, 23, 42, 0.62)",
            backdropFilter: "blur(4px)",
          }}
        >
          <section
            className="backtesting-confirm-modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="backtesting-confirm-title"
            aria-describedby="backtesting-confirm-description"
            onClick={(event) => event.stopPropagation()}
            style={{
              width: "100%",
              maxWidth: "440px",
              border: "1px solid rgba(148, 163, 184, 0.25)",
              borderRadius: "18px",
              padding: "1.5rem",
              background: "var(--backtesting-card-bg, #ffffff)",
              color: "var(--backtesting-text, #0f172a)",
              boxShadow: "0 24px 80px rgba(0, 0, 0, 0.3)",
            }}
          >
            <div
              style={{
                display: "flex",
                alignItems: "flex-start",
                gap: "1rem",
                marginBottom: "1.25rem",
              }}
            >
              <div
                aria-hidden="true"
                style={{
                  display: "grid",
                  placeItems: "center",
                  flexShrink: 0,
                  width: "46px",
                  height: "46px",
                  borderRadius: "14px",
                  color: "#b91c1c",
                  background: "#fee2e2",
                  fontSize: "1.15rem",
                }}
              >
                <FaTrash />
              </div>

              <div style={{ minWidth: 0, flex: 1 }}>
                <h2
                  id="backtesting-confirm-title"
                  style={{
                    margin: "0 0 0.45rem",
                    fontSize: "1.2rem",
                    lineHeight: 1.35,
                    fontWeight: 700,
                  }}
                >
                  {deleteConfirmation.type === "bulk"
                    ? `Delete ${deleteConfirmation.count} backtests?`
                    : "Delete this backtest?"}
                </h2>

                <p
                  id="backtesting-confirm-description"
                  style={{
                    margin: 0,
                    color: "var(--backtesting-muted, #64748b)",
                    fontSize: "0.95rem",
                    lineHeight: 1.6,
                  }}
                >
                  {deleteConfirmation.type === "bulk"
                    ? `You are about to permanently delete ${deleteConfirmation.count} selected backtest${deleteConfirmation.count === 1 ? "" : "s"}.`
                    : `You are about to permanently delete backtest ${String(
                        deleteConfirmation.backtestId || "",
                      ).slice(0, 8)}.`}{" "}
                  This action cannot be undone.
                </p>
              </div>
            </div>

            <div
              style={{
                display: "flex",
                justifyContent: "flex-end",
                gap: "0.75rem",
                paddingTop: "0.25rem",
              }}
            >
              <button
                type="button"
                className="backtesting-button secondary"
                onClick={() => setDeleteConfirmation(null)}
                disabled={bulkDeleting}
              >
                Cancel
              </button>

              <button
                type="button"
                className="backtesting-button"
                onClick={handleConfirmDelete}
                disabled={bulkDeleting}
                style={{
                  display: "inline-flex",
                  alignItems: "center",
                  justifyContent: "center",
                  gap: "0.5rem",
                  border: "1px solid #b91c1c",
                  borderRadius: "9px",
                  padding: "0.65rem 1rem",
                  color: "#ffffff",
                  background: "#b91c1c",
                  fontWeight: 700,
                  cursor: bulkDeleting ? "wait" : "pointer",
                }}
              >
                <FaTrash />
                {deleteConfirmation.type === "bulk"
                  ? `Delete ${deleteConfirmation.count}`
                  : "Delete backtest"}
              </button>
            </div>
          </section>
        </div>
      )}
    </div>
  );
};

export default Backtesting;
