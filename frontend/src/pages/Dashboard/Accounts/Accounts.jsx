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

import { useEffect, useMemo, useState } from "react";
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
    accounts,
    loading,
    creating,
    updating,
    connecting,
    disconnecting,
    deleting,
    error,
  } = useSelector((state) => state.accounts);

  const [isCreateOpen, setIsCreateOpen] = useState(false);
  const [editingAccount, setEditingAccount] = useState(null);
  const [viewingAccount, setViewingAccount] = useState(null);
  const [accountToDelete, setAccountToDelete] = useState(null);

  const [searchTerm, setSearchTerm] = useState("");
  const [environmentFilter, setEnvironmentFilter] = useState("ALL");
  const [statusFilter, setStatusFilter] = useState("ALL");

  // =====================================================
  // FETCH ACCOUNTS
  // =====================================================

  useEffect(() => {
    dispatch(fetchAccounts());
  }, [dispatch]);

  // =====================================================
  // ACCOUNT STATISTICS
  // =====================================================

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

  // =====================================================
  // FILTER ACCOUNTS
  // =====================================================

  const filteredAccounts = useMemo(() => {
    return accounts.filter((account) => {
      const search = searchTerm.trim().toLowerCase();

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

  // =====================================================
  // REFRESH
  // =====================================================

  const handleRefresh = () => {
    dispatch(fetchAccounts());
  };

  // =====================================================
  // CREATE ACCOUNT
  // =====================================================

  const handleCreateAccount = async (data) => {
    console.log("CREATE ACCOUNT PAYLOAD:", data);

    const result = await dispatch(createTradingAccount(data));

    if (createTradingAccount.fulfilled.match(result)) {
      setIsCreateOpen(false);

      dispatch(clearAccountOperationState());
    }
  };

  // =====================================================
  // CREATE / UPDATE ACCOUNT
  // =====================================================

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

  // =====================================================
  // CONNECT ACCOUNT
  // =====================================================

  const handleConnectAccount = async (account) => {
    if (!account?.id) {
      return;
    }

    if (connecting || disconnecting) {
      return;
    }

    if (!account.active) {
      return;
    }

    const result = await dispatch(connectTradingAccount(account.id));

    if (connectTradingAccount.fulfilled.match(result)) {
      dispatch(clearAccountOperationState());
    }
  };

  // =====================================================
  // DISCONNECT ACCOUNT
  // =====================================================

  const handleDisconnectAccount = async (account) => {
    if (!account?.id) {
      return;
    }

    if (connecting || disconnecting) {
      return;
    }

    const result = await dispatch(disconnectTradingAccount(account.id));

    if (disconnectTradingAccount.fulfilled.match(result)) {
      dispatch(clearAccountOperationState());
    }
  };

  // =====================================================
  // DELETE ACCOUNT
  // =====================================================

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

  // =====================================================
  // FORMAT MONEY
  // =====================================================

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

  // =====================================================
  // RENDER
  // =====================================================

  return (
    <main className="accounts-page">
      {/* =====================================================
          HEADER
      ===================================================== */}

      <section className="accounts-header">
        <div>
          <span className="accounts-eyebrow">TRADING INFRASTRUCTURE</span>

          <h1>Trading Accounts</h1>

          <p>
            Manage broker connections, trading environments and account
            configurations.
          </p>
        </div>

        {/* ERROR */}

        {error && (
          <div className="accounts-error">
            <span>
              {typeof error === "string"
                ? error
                : error?.detail
                  ? typeof error.detail === "string"
                    ? error.detail
                    : JSON.stringify(error.detail)
                  : "Unable to process account request."}
            </span>

            <button
              type="button"
              onClick={() => dispatch(clearAccountsError())}
            >
              ×
            </button>
          </div>
        )}

        {/* ADD ACCOUNT */}

        <button
          type="button"
          className="accounts-primary-button"
          onClick={() => setIsCreateOpen(true)}
          disabled={creating}
          title="Add trading account"
        >
          <FaPlus />

          <span>Add Account</span>
        </button>
      </section>

      {/* =====================================================
          STATISTICS
      ===================================================== */}

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

      {/* =====================================================
          TOOLBAR
      ===================================================== */}

      <section className="accounts-toolbar">
        {/* SEARCH */}

        <div className="accounts-search">
          <FaSearch />

          <input
            type="text"
            placeholder="Search trading accounts..."
            value={searchTerm}
            onChange={(event) => setSearchTerm(event.target.value)}
          />
        </div>

        {/* FILTERS */}

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
            disabled={loading}
          >
            <FaSyncAlt className={loading ? "accounts-spin" : ""} />
          </button>
        </div>
      </section>

      {/* =====================================================
          ACCOUNTS TABLE
      ===================================================== */}

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

                <th>Environment</th>

                <th>Balance</th>

                <th>Equity</th>

                <th>Status</th>

                <th>Actions</th>
              </tr>
            </thead>

            <tbody>
              {/* =================================================
                  LOADING
              ================================================= */}

              {loading ? (
                <tr>
                  <td colSpan="7" className="accounts-empty">
                    <FaSyncAlt className="accounts-spin" />

                    <strong>Loading trading accounts...</strong>

                    <span>Fetching your account registry.</span>
                  </td>
                </tr>
              ) : filteredAccounts.length === 0 ? (
                /* =================================================
                   EMPTY
                ================================================= */

                <tr>
                  <td colSpan="7" className="accounts-empty">
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
                      >
                        <FaPlus />
                        Add Account
                      </button>
                    )}
                  </td>
                </tr>
              ) : (
                /* =================================================
                   ACCOUNTS
                ================================================= */

                filteredAccounts.map((account) => (
                  <tr key={account.id}>
                    {/* =========================================
                        ACCOUNT
                    ========================================= */}

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

                    {/* =========================================
                        BROKER
                    ========================================= */}

                    <td>
                      <div className="account-table-broker">
                        <strong>{account.broker || "—"}</strong>

                        <span>{account.server || "No server"}</span>
                      </div>
                    </td>

                    {/* =========================================
                        ENVIRONMENT
                    ========================================= */}

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

                    {/* =========================================
                        BALANCE
                    ========================================= */}

                    <td>
                      <strong>
                        {formatMoney(account.balance, account.currency)}
                      </strong>
                    </td>

                    {/* =========================================
                        EQUITY
                    ========================================= */}

                    <td>
                      <strong>
                        {formatMoney(account.equity, account.currency)}
                      </strong>
                    </td>

                    {/* =========================================
                        STATUS
                    ========================================= */}

                    <td>
                      <div className="account-status-cell">
                        {/* AQE ACTIVE STATUS */}

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

                        {/* BROKER CONNECTION STATUS */}

                        <small
                          className={`account-connection-status ${
                            account.status?.toLowerCase() || "disconnected"
                          }`}
                        >
                          {account.status || "DISCONNECTED"}
                        </small>
                      </div>
                    </td>

                    {/* =========================================
                        ACTIONS
                    ========================================= */}

                    <td>
                      <div className="account-actions">
                        {/* VIEW */}

                        <button
                          type="button"
                          title="View account"
                          onClick={() => setViewingAccount(account)}
                          disabled={connecting || disconnecting}
                        >
                          <FaEye />
                        </button>

                        {/* EDIT */}

                        <button
                          type="button"
                          title="Edit account"
                          onClick={() => setEditingAccount(account)}
                          disabled={connecting || disconnecting}
                        >
                          <FaEdit />
                        </button>

                        {/* CONNECT / DISCONNECT */}

                        {account.status === "CONNECTED" ? (
                          <button
                            type="button"
                            title="Disconnect account"
                            onClick={() => handleDisconnectAccount(account)}
                            disabled={disconnecting || connecting}
                          >
                            {disconnecting ? (
                              <FaSyncAlt className="accounts-spin" />
                            ) : (
                              <FaCheckCircle />
                            )}
                          </button>
                        ) : (
                          <button
                            type="button"
                            title={
                              account.active
                                ? "Connect account"
                                : "Activate account before connecting"
                            }
                            onClick={() => handleConnectAccount(account)}
                            disabled={
                              connecting || disconnecting || !account.active
                            }
                          >
                            {connecting ? (
                              <FaSyncAlt className="accounts-spin" />
                            ) : (
                              <FaGlobe />
                            )}
                          </button>
                        )}

                        {/* DELETE */}

                        <button
                          type="button"
                          title="Delete account"
                          onClick={() => setAccountToDelete(account)}
                          disabled={deleting || connecting || disconnecting}
                        >
                          <FaTrash />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </section>

      {/* =====================================================
          CREATE / EDIT ACCOUNT FORM
      ===================================================== */}

      <AccountForm
        isOpen={isCreateOpen || Boolean(editingAccount)}
        onClose={() => {
          if (!creating && !updating) {
            setIsCreateOpen(false);

            setEditingAccount(null);
          }
        }}
        loading={creating || updating}
        onSubmit={handleAccountSubmit}
        account={editingAccount}
      />

      {/* =====================================================
          ACCOUNT DETAILS MODAL
      ===================================================== */}

      {viewingAccount && (
        <div
          className="account-detail-overlay"
          onMouseDown={(event) => {
            if (event.target === event.currentTarget) {
              setViewingAccount(null);
            }
          }}
        >
          <div className="account-detail-modal" role="dialog" aria-modal="true">
            {/* CLOSE */}

            <button
              type="button"
              className="account-detail-close"
              onClick={() => setViewingAccount(null)}
              aria-label="Close"
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
                <span>Status</span>

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

      {/* =====================================================
          DELETE CONFIRMATION
      ===================================================== */}

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
