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

import {
  fetchAccounts,
  createTradingAccount,
} from "../../../redux/dashboard/accounts/accountsThunks";

import {
  clearAccountsError,
  clearAccountOperationState,
} from "../../../redux/dashboard/accounts/accountsSlice";

import "../../../css/accounts.css";

const Accounts = () => {
  // =====================================================
  // REDUX
  // =====================================================

  const dispatch = useDispatch();

  const { accounts, loading, creating, error } = useSelector(
    (state) => state.accounts,
  );

  // =====================================================
  // LOCAL STATE
  // =====================================================

  const [isCreateOpen, setIsCreateOpen] = useState(false);

  const [searchTerm, setSearchTerm] = useState("");

  const [environmentFilter, setEnvironmentFilter] = useState("ALL");

  const [statusFilter, setStatusFilter] = useState("ALL");

  // =====================================================
  // LOAD ACCOUNTS
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
  // FILTERED ACCOUNTS
  // =====================================================

  const filteredAccounts = useMemo(() => {
    return accounts.filter((account) => {
      // -------------------------------------------------
      // SEARCH
      // -------------------------------------------------

      const search = searchTerm.trim().toLowerCase();

      const matchesSearch =
        !search ||
        String(account.account_number || "")
          .toLowerCase()
          .includes(search) ||
        String(account.account_name || "")
          .toLowerCase()
          .includes(search) ||
        String(account.broker || "")
          .toLowerCase()
          .includes(search) ||
        String(account.server || "")
          .toLowerCase()
          .includes(search);

      // -------------------------------------------------
      // ENVIRONMENT
      // -------------------------------------------------

      const matchesEnvironment =
        environmentFilter === "ALL" ||
        (environmentFilter === "LIVE" && account.is_demo === false) ||
        (environmentFilter === "DEMO" && account.is_demo === true);

      // -------------------------------------------------
      // STATUS
      // -------------------------------------------------

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
    const payload = {
      broker: data.broker,

      account_number: Number(data.account_number),

      server: data.server,

      account_name: data.account_name,

      currency: data.currency,

      leverage: Number(data.leverage),

      balance: Number(data.balance),

      equity: Number(data.equity),

      margin: Number(data.margin),

      free_margin: Number(data.free_margin),

      margin_level: Number(data.margin_level),

      is_demo: Boolean(data.is_demo),

      status: data.status,

      active: Boolean(data.active),
    };

    console.log("CREATE ACCOUNT PAYLOAD:", payload);

    const result = await dispatch(createTradingAccount(payload));

    if (createTradingAccount.fulfilled.match(result)) {
      setIsCreateOpen(false);

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
      {/* =================================================
          PAGE HEADER
      ================================================= */}

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
          className="accounts-primary-button"
          onClick={() => setIsCreateOpen(true)}
          disabled={creating}
          title="Add trading account"
        >
          <FaPlus />

          <span>Add Account</span>
        </button>
      </section>

      {/* =================================================
          STATISTICS
      ================================================= */}

      <section className="accounts-stats">
        {/* TOTAL */}

        <div className="account-stat">
          <div className="account-stat-icon">
            <FaWallet />
          </div>

          <div>
            <span>Total Accounts</span>

            <strong>{totalAccounts}</strong>
          </div>
        </div>

        {/* ACTIVE */}

        <div className="account-stat">
          <div className="account-stat-icon">
            <FaCheckCircle />
          </div>

          <div>
            <span>Active Accounts</span>

            <strong>{activeAccounts}</strong>
          </div>
        </div>

        {/* LIVE */}

        <div className="account-stat">
          <div className="account-stat-icon">
            <FaGlobe />
          </div>

          <div>
            <span>Live Accounts</span>

            <strong>{liveAccounts}</strong>
          </div>
        </div>

        {/* DEMO */}

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

      {/* =================================================
          TOOLBAR
      ================================================= */}

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

        <div className="accounts-filters">
          {/* ENVIRONMENT */}

          <select
            value={environmentFilter}
            onChange={(event) => setEnvironmentFilter(event.target.value)}
          >
            <option value="ALL">All Accounts</option>

            <option value="LIVE">Live</option>

            <option value="DEMO">Demo</option>
          </select>

          {/* STATUS */}

          <select
            value={statusFilter}
            onChange={(event) => setStatusFilter(event.target.value)}
          >
            <option value="ALL">All Status</option>

            <option value="ACTIVE">Active</option>

            <option value="INACTIVE">Inactive</option>
          </select>

          {/* REFRESH */}

          <button
            className="accounts-refresh"
            title="Refresh accounts"
            onClick={handleRefresh}
            disabled={loading}
          >
            <FaSyncAlt className={loading ? "accounts-spin" : ""} />
          </button>
        </div>
      </section>

      {/* =================================================
          ACCOUNTS TABLE
      ================================================= */}

      <section className="accounts-card">
        {/* CARD HEADER */}

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

        {/* TABLE */}

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
              {/* =========================================
                  LOADING
              ========================================= */}

              {loading ? (
                <tr>
                  <td colSpan="7" className="accounts-empty">
                    <FaSyncAlt className="accounts-spin" />

                    <strong>Loading trading accounts...</strong>

                    <span>Fetching your account registry.</span>
                  </td>
                </tr>
              ) : filteredAccounts.length === 0 ? (
                /* =======================================
                   EMPTY
                ======================================= */

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
                      <button onClick={() => setIsCreateOpen(true)}>
                        <FaPlus />
                        Add Account
                      </button>
                    )}
                  </td>
                </tr>
              ) : (
                /* =======================================
                   ACCOUNT ROWS
                ======================================= */

                filteredAccounts.map((account) => (
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

                          <span>#{account.account_number}</span>
                        </div>
                      </div>
                    </td>

                    {/* BROKER */}

                    <td>
                      <div className="account-table-broker">
                        <strong>{account.broker || "—"}</strong>

                        <span>{account.server || "No server"}</span>
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

                        <small>{account.status || "DISCONNECTED"}</small>
                      </div>
                    </td>

                    {/* ACTIONS */}

                    <td>
                      <div className="account-actions">
                        {/* VIEW */}

                        <button
                          type="button"
                          title="View account"
                          onClick={() =>
                            console.log("View account:", account.id)
                          }
                        >
                          <FaEye />
                        </button>

                        {/* EDIT */}

                        <button
                          type="button"
                          title="Edit account"
                          onClick={() =>
                            console.log("Edit account:", account.id)
                          }
                        >
                          <FaEdit />
                        </button>

                        {/* DELETE */}

                        <button
                          type="button"
                          title="Delete account"
                          onClick={() =>
                            console.log("Delete account:", account.id)
                          }
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

      {/* =================================================
          CREATE ACCOUNT MODAL
      ================================================= */}

      <AccountForm
        isOpen={isCreateOpen}
        onClose={() => {
          if (!creating) {
            setIsCreateOpen(false);
          }
        }}
        loading={creating}
        onSubmit={handleCreateAccount}
      />
    </main>
  );
};

export default Accounts;
