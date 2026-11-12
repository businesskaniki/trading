import {
  FaPlus,
  FaSearch,
  FaSyncAlt,
  FaWallet,
  FaCheckCircle,
  FaGlobe,
  FaDesktop,
  FaEdit,
  FaTrash,
  FaEye,
} from "react-icons/fa";

import { useEffect, useMemo, useRef, useState } from "react";

import { useDispatch, useSelector } from "react-redux";

import AccountForm from "./AccountForm";
import ConfirmModal from "../../../components/common/ConfirmModal";

import {
  fetchAccounts,
  createTradingAccount,
  updateTradingAccount,
  connectTradingAccount,
  disconnectTradingAccount,
  removeTradingAccount,
} from "../../../redux/dashboard/accounts/accountsThunks";

import {
  clearAccountsError,
  clearAccountOperationState,
} from "../../../redux/dashboard/accounts/accountsSlice";

import "../../../css/accounts.css";
import "../../../css/accountDetails.css";

const Accounts = () => {
  const dispatch = useDispatch();

  const {
    accounts = [],
    loading,
    creating,
    updating,
    connecting,
    disconnecting,
    deleting,
    error,
  } = useSelector((state) => state.accounts);

  /*
   * Global Redux flags prevent other account operations while a
   * connection operation is running.
   *
   * connectionOperation identifies the particular account whose
   * Connect or Disconnect operation is currently in progress.
   */
  const [connectionOperation, setConnectionOperation] = useState(null);

  /*
   * A ref provides an immediate synchronous lock. This prevents two
   * rapid clicks from dispatching duplicate connection requests before
   * React has completed the next render.
   */
  const connectionOperationRef = useRef(false);

  const connectionBusy =
    Boolean(connectionOperation) || connecting || disconnecting;

  // Show the loading screen only when there is no account data yet.
  const isInitialLoading = loading && accounts.length === 0;

  const [isCreateOpen, setIsCreateOpen] = useState(false);
  const [editingAccount, setEditingAccount] = useState(null);
  const [viewingAccount, setViewingAccount] = useState(null);
  const [accountToDelete, setAccountToDelete] = useState(null);

  const [searchTerm, setSearchTerm] = useState("");
  const [environmentFilter, setEnvironmentFilter] = useState("ALL");
  const [statusFilter, setStatusFilter] = useState("ALL");

  // ---------------------------------------------------------
  // FETCH ACCOUNTS
  // ---------------------------------------------------------

  useEffect(() => {
    dispatch(fetchAccounts());
  }, [dispatch]);

  // ---------------------------------------------------------
  // ACCOUNT-SPECIFIC CONNECTION STATUS
  // ---------------------------------------------------------

  const isConnectingAccount = (accountId) =>
    connectionOperation?.type === "CONNECT" &&
    String(connectionOperation.accountId) === String(accountId);

  const isDisconnectingAccount = (accountId) =>
    connectionOperation?.type === "DISCONNECT" &&
    String(connectionOperation.accountId) === String(accountId);

  // ---------------------------------------------------------
  // STATISTICS
  // ---------------------------------------------------------

  const totalAccounts = accounts.length;

  const activeAccounts = accounts.filter(
    (account) => account.active === true,
  ).length;

  const liveAccounts = accounts.filter(
    (account) => account.is_demo === false,
  ).length;

  const demoAccounts = accounts.filter(
    (account) => account.is_demo === true,
  ).length;

  // ---------------------------------------------------------
  // FILTER ACCOUNTS
  // ---------------------------------------------------------

  const filteredAccounts = useMemo(() => {
    const search = searchTerm.trim().toLowerCase();

    return accounts.filter((account) => {
      const matchesSearch =
        !search ||
        String(account.login ?? "")
          .toLowerCase()
          .includes(search) ||
        String(account.account_name ?? "")
          .toLowerCase()
          .includes(search) ||
        String(account.broker ?? "")
          .toLowerCase()
          .includes(search) ||
        String(account.server ?? "")
          .toLowerCase()
          .includes(search);

      const matchesEnvironment =
        environmentFilter === "ALL" ||
        (environmentFilter === "LIVE" && account.is_demo === false) ||
        (environmentFilter === "DEMO" && account.is_demo === true);

      const matchesStatus =
        statusFilter === "ALL" ||
        (statusFilter === "ACTIVE" && account.active === true) ||
        (statusFilter === "INACTIVE" && account.active === false);

      return matchesSearch && matchesEnvironment && matchesStatus;
    });
  }, [accounts, searchTerm, environmentFilter, statusFilter]);

  // ---------------------------------------------------------
  // REFRESH
  // ---------------------------------------------------------

  const handleRefresh = () => {
    dispatch(fetchAccounts());
  };

  // ---------------------------------------------------------
  // CREATE / UPDATE
  // ---------------------------------------------------------

  const handleCreateAccount = async (data) => {
    const result = await dispatch(createTradingAccount(data));

    if (createTradingAccount.fulfilled.match(result)) {
      setIsCreateOpen(false);
      dispatch(clearAccountOperationState());
    }
  };

  const handleAccountSubmit = async (data) => {
    if (!editingAccount) {
      return handleCreateAccount(data);
    }

    const result = await dispatch(
      updateTradingAccount({
        accountId: editingAccount.id,
        accountData: data,
      }),
    );

    if (updateTradingAccount.fulfilled.match(result)) {
      setEditingAccount(null);
      dispatch(clearAccountOperationState());
    }
  };

  // ---------------------------------------------------------
  // CONNECTION OPERATION LOCK
  // ---------------------------------------------------------

  const beginConnectionOperation = (accountId, type) => {
    if (
      !accountId ||
      connectionOperationRef.current ||
      connecting ||
      disconnecting
    ) {
      return false;
    }

    connectionOperationRef.current = true;

    setConnectionOperation({
      accountId: String(accountId),
      type,
    });

    return true;
  };

  const endConnectionOperation = () => {
    connectionOperationRef.current = false;
    setConnectionOperation(null);
  };

  // ---------------------------------------------------------
  // CONNECT
  // ---------------------------------------------------------

  const handleConnectAccount = async (account) => {
    if (!account?.id || !account.active) {
      return;
    }

    /*
     * Acquire the lock before dispatching. Only one connection
     * operation can start at a time.
     */
    if (!beginConnectionOperation(account.id, "CONNECT")) {
      return;
    }

    try {
      const result = await dispatch(connectTradingAccount(account.id));

      if (connectTradingAccount.fulfilled.match(result)) {
        dispatch(clearAccountOperationState());
      }

      // The Redux thunk handles and stores rejected-request errors.
    } catch (connectError) {
      console.error(`Failed to connect account ${account.id}:`, connectError);
    } finally {
      endConnectionOperation();
    }
  };

  // ---------------------------------------------------------
  // DISCONNECT
  // ---------------------------------------------------------

  const handleDisconnectAccount = async (account) => {
    if (!account?.id) {
      return;
    }

    if (!beginConnectionOperation(account.id, "DISCONNECT")) {
      return;
    }

    try {
      const result = await dispatch(disconnectTradingAccount(account.id));

      if (disconnectTradingAccount.fulfilled.match(result)) {
        dispatch(clearAccountOperationState());
      }
    } catch (disconnectError) {
      console.error(
        `Failed to disconnect account ${account.id}:`,
        disconnectError,
      );
    } finally {
      endConnectionOperation();
    }
  };

  // ---------------------------------------------------------
  // DELETE
  // ---------------------------------------------------------

  const handleDeleteAccount = async () => {
    if (!accountToDelete?.id) {
      return;
    }

    const result = await dispatch(removeTradingAccount(accountToDelete.id));

    if (removeTradingAccount.fulfilled.match(result)) {
      setAccountToDelete(null);
      dispatch(clearAccountOperationState());
    }
  };

  // ---------------------------------------------------------
  // FORMAT MONEY
  // ---------------------------------------------------------

  const formatMoney = (value, currency = "USD") => {
    const number = Number(value);

    if (!Number.isFinite(number)) {
      return `0.00 ${currency}`;
    }

    return new Intl.NumberFormat("en-US", {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    }).format(number);
  };

  // ---------------------------------------------------------
  // ERROR MESSAGE
  // ---------------------------------------------------------

  const getErrorMessage = () => {
    if (typeof error === "string") {
      return error;
    }

    if (error?.detail) {
      return typeof error.detail === "string"
        ? error.detail
        : JSON.stringify(error.detail);
    }

    return "Unable to process account request.";
  };

  // ---------------------------------------------------------
  // RENDER
  // ---------------------------------------------------------

  return (
    <main className="accounts-page">
      {/* HEADER */}

      <section className="accounts-header">
        <div>
          <span className="accounts-eyebrow">TRADING INFRASTRUCTURE</span>

          <h1>Trading Accounts</h1>

          <p>
            Manage broker connections, trading environments and account
            configurations.
          </p>
        </div>

        {error && (
          <div className="accounts-error">
            <span>{getErrorMessage()}</span>

            <button
              type="button"
              onClick={() => dispatch(clearAccountsError())}
              aria-label="Dismiss error"
            >
              ×
            </button>
          </div>
        )}

        <button
          type="button"
          className="accounts-primary-button"
          onClick={() => setIsCreateOpen(true)}
          disabled={creating || connectionBusy}
          title="Add trading account"
        >
          <FaPlus />
          <span>Add Account</span>
        </button>
      </section>

      {/* STATISTICS */}

      <section className="accounts-stats">
        <div className="account-stat">
          <div className="account-stat-icon">
            <FaWallet />
          </div>

          <div>
            <span>Total Accounts</span>
            <strong>{totalAccounts}</strong>
          </div>
        </div>

        <div className="account-stat">
          <div className="account-stat-icon">
            <FaCheckCircle />
          </div>

          <div>
            <span>Active Accounts</span>
            <strong>{activeAccounts}</strong>
          </div>
        </div>

        <div className="account-stat">
          <div className="account-stat-icon">
            <FaGlobe />
          </div>

          <div>
            <span>Live Accounts</span>
            <strong>{liveAccounts}</strong>
          </div>
        </div>

        <div className="account-stat">
          <div className="account-stat-icon">
            <FaDesktop />
          </div>

          <div>
            <span>Demo Accounts</span>
            <strong>{demoAccounts}</strong>
          </div>
        </div>
      </section>

      {/* TOOLBAR */}

      <section className="accounts-toolbar">
        <div className="accounts-search">
          <FaSearch />

          <input
            type="text"
            placeholder="Search trading accounts..."
            value={searchTerm}
            onChange={(event) => setSearchTerm(event.target.value)}
          />
        </div>

        <div className="accounts-filters">
          <select
            value={environmentFilter}
            onChange={(event) => setEnvironmentFilter(event.target.value)}
          >
            <option value="ALL">All Accounts</option>
            <option value="LIVE">Live</option>
            <option value="DEMO">Demo</option>
          </select>

          <select
            value={statusFilter}
            onChange={(event) => setStatusFilter(event.target.value)}
          >
            <option value="ALL">All Status</option>
            <option value="ACTIVE">Active</option>
            <option value="INACTIVE">Inactive</option>
          </select>

          <button
            type="button"
            className="accounts-refresh"
            title="Refresh accounts"
            onClick={handleRefresh}
            disabled={loading || connectionBusy}
          >
            <FaSyncAlt className={loading ? "accounts-spin" : ""} />
          </button>
        </div>
      </section>

      {/* ACCOUNTS TABLE */}

      <section className="accounts-card">
        <div className="accounts-card-header">
          <div>
            <span>ACCOUNT REGISTRY</span>
            <h2>Trading Accounts</h2>
          </div>

          <span className="accounts-count">
            {filteredAccounts.length}{" "}
            {filteredAccounts.length === 1 ? "account" : "accounts"}
          </span>
        </div>

        <div className="accounts-table-wrapper">
          <table className="accounts-table">
            <thead>
              <tr>
                <th>Account</th>
                <th>Broker</th>
                <th>Server</th>
                <th>Environment</th>
                <th>Balance</th>
                <th>Equity</th>
                <th>Status</th>
                <th>Actions</th>
              </tr>
            </thead>

            <tbody>
              {isInitialLoading ? (
                <tr>
                  <td colSpan={8} className="accounts-empty">
                    <FaSyncAlt className="accounts-spin" />

                    <strong>Loading trading accounts...</strong>

                    <span>Fetching your account registry.</span>
                  </td>
                </tr>
              ) : filteredAccounts.length === 0 ? (
                <tr>
                  <td colSpan={8} className="accounts-empty">
                    <FaWallet />

                    <strong>
                      {accounts.length === 0
                        ? "No trading accounts"
                        : "No matching accounts"}
                    </strong>

                    <span>
                      {accounts.length === 0
                        ? "Add your first trading account to get started."
                        : "Try changing your search or filters."}
                    </span>

                    {accounts.length === 0 && (
                      <button
                        type="button"
                        onClick={() => setIsCreateOpen(true)}
                        disabled={connectionBusy}
                      >
                        <FaPlus />
                        Add Account
                      </button>
                    )}
                  </td>
                </tr>
              ) : (
                filteredAccounts.map((account) => {
                  const accountConnecting = isConnectingAccount(account.id);
                  const accountDisconnecting = isDisconnectingAccount(
                    account.id,
                  );

                  return (
                    <tr key={account.id}>
                      {/* ACCOUNT */}

                      <td>
                        <div className="account-table-name">
                          <div className="account-table-icon">
                            <FaWallet />
                          </div>

                          <div>
                            <strong>
                              {account.account_name || "Trading Account"}
                            </strong>

                            <span>#{account.login ?? "—"}</span>
                          </div>
                        </div>
                      </td>

                      {/* BROKER */}

                      <td>
                        <div className="account-table-broker">
                          <strong>{account.broker || "—"}</strong>
                        </div>
                      </td>

                      {/* SERVER */}

                      <td>
                        <div className="account-table-server">
                          <span>{account.server || "—"}</span>
                        </div>
                      </td>

                      {/* ENVIRONMENT */}

                      <td>
                        <span
                          className={
                            account.is_demo
                              ? "account-environment demo"
                              : "account-environment live"
                          }
                        >
                          {account.is_demo ? "DEMO" : "LIVE"}
                        </span>
                      </td>

                      {/* BALANCE */}

                      <td>
                        <strong>
                          {formatMoney(account.balance, account.currency)}
                        </strong>
                      </td>

                      {/* EQUITY */}

                      <td>
                        <strong>
                          {formatMoney(account.equity, account.currency)}
                        </strong>
                      </td>

                      {/* STATUS */}

                      <td>
                        <div className="account-status-cell">
                          <span
                            className={
                              account.active
                                ? "account-status active"
                                : "account-status inactive"
                            }
                          >
                            <span className="account-status-dot" />
                            {account.active ? "Active" : "Inactive"}
                          </span>

                          <span
                            className={`account-connection-status ${
                              account.status?.toLowerCase() || "disconnected"
                            }`}
                          >
                            {account.status || "DISCONNECTED"}
                          </span>

                          {accountConnecting && (
                            <span className="account-connection-status">
                              Connecting...
                            </span>
                          )}

                          {accountDisconnecting && (
                            <span className="account-connection-status">
                              Disconnecting...
                            </span>
                          )}
                        </div>
                      </td>

                      {/* ACTIONS */}

                      <td>
                        <div className="account-actions">
                          <button
                            type="button"
                            className="account-action-view"
                            title="View account"
                            onClick={() => setViewingAccount(account)}
                            disabled={connectionBusy}
                          >
                            <FaEye />
                          </button>

                          <button
                            type="button"
                            className="account-action-edit"
                            title="Edit account"
                            onClick={() => setEditingAccount(account)}
                            disabled={connectionBusy}
                          >
                            <FaEdit />
                          </button>

                          {account.status === "CONNECTED" ? (
                            <button
                              type="button"
                              className="account-action-connect"
                              title={
                                accountDisconnecting
                                  ? "Disconnecting account"
                                  : "Disconnect account"
                              }
                              onClick={() => handleDisconnectAccount(account)}
                              disabled={connectionBusy}
                            >
                              {accountDisconnecting ? (
                                <FaSyncAlt className="accounts-spin" />
                              ) : (
                                <FaCheckCircle />
                              )}
                            </button>
                          ) : (
                            <button
                              type="button"
                              className="account-action-connect"
                              title={
                                !account.active
                                  ? "Activate account before connecting"
                                  : accountConnecting
                                    ? "Connecting account"
                                    : connectionBusy
                                      ? "Another account connection operation is in progress"
                                      : "Connect account"
                              }
                              onClick={() => handleConnectAccount(account)}
                              disabled={connectionBusy || !account.active}
                            >
                              {accountConnecting ? (
                                <FaSyncAlt className="accounts-spin" />
                              ) : (
                                <FaGlobe />
                              )}
                            </button>
                          )}

                          <button
                            type="button"
                            className="account-action-delete"
                            title="Delete account"
                            onClick={() => setAccountToDelete(account)}
                            disabled={deleting || connectionBusy}
                          >
                            <FaTrash />
                          </button>
                        </div>
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      </section>

      {/* CREATE / EDIT ACCOUNT */}

      <AccountForm
        isOpen={isCreateOpen || Boolean(editingAccount)}
        onClose={() => {
          if (!creating && !updating && !connectionBusy) {
            setIsCreateOpen(false);
            setEditingAccount(null);
          }
        }}
        loading={creating || updating}
        onSubmit={handleAccountSubmit}
        account={editingAccount}
      />

      {/* ACCOUNT DETAILS */}

      {viewingAccount && (
        <div
          className="account-detail-overlay"
          onMouseDown={(event) => {
            if (event.target === event.currentTarget && !connectionBusy) {
              setViewingAccount(null);
            }
          }}
        >
          <div className="account-detail-modal" role="dialog" aria-modal="true">
            <button
              type="button"
              className="account-detail-close"
              onClick={() => setViewingAccount(null)}
              aria-label="Close"
              disabled={connectionBusy}
            >
              ×
            </button>

            <span className="accounts-eyebrow">ACCOUNT PROFILE</span>

            <h2>{viewingAccount.account_name || "Trading Account"}</h2>

            <p className="account-detail-number">
              #{viewingAccount.login ?? "—"} ·{" "}
              {viewingAccount.broker || "Unknown broker"}
            </p>

            <div className="account-detail-grid">
              <div>
                <span>Server</span>
                <strong>{viewingAccount.server || "-"}</strong>
              </div>

              <div>
                <span>Environment</span>
                <strong>{viewingAccount.is_demo ? "DEMO" : "LIVE"}</strong>
              </div>

              <div>
                <span>Balance</span>
                <strong>
                  {formatMoney(viewingAccount.balance, viewingAccount.currency)}
                </strong>
              </div>

              <div>
                <span>Equity</span>
                <strong>
                  {formatMoney(viewingAccount.equity, viewingAccount.currency)}
                </strong>
              </div>

              <div>
                <span>Margin</span>
                <strong>
                  {formatMoney(viewingAccount.margin, viewingAccount.currency)}
                </strong>
              </div>

              <div>
                <span>Connection</span>
                <strong>{viewingAccount.status || "DISCONNECTED"}</strong>
              </div>

              <div>
                <span>Currency</span>
                <strong>{viewingAccount.currency || "-"}</strong>
              </div>

              <div>
                <span>Leverage</span>
                <strong>
                  {viewingAccount.leverage
                    ? `1:${viewingAccount.leverage}`
                    : "-"}
                </strong>
              </div>

              <div>
                <span>AQE Status</span>
                <strong>{viewingAccount.active ? "ACTIVE" : "INACTIVE"}</strong>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* DELETE CONFIRMATION */}

      <ConfirmModal
        isOpen={Boolean(accountToDelete)}
        title="Delete trading account?"
        message={`${
          accountToDelete?.account_name || "This account"
        } will be permanently removed from the account registry.`}
        confirmLabel="Delete Account"
        danger={true}
        loading={deleting}
        onConfirm={handleDeleteAccount}
        onClose={() => !deleting && setAccountToDelete(null)}
      />
    </main>
  );
};

export default Accounts;
