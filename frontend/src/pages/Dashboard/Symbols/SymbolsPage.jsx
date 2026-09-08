import { useEffect, useMemo, useState } from "react";
import { useDispatch, useSelector } from "react-redux";

import { FaCheckCircle, FaCoins, FaSearch, FaSyncAlt } from "react-icons/fa";

import SymbolForm from "./SymbolForm";

import { selectAccount } from "../../../redux/dashboard/accounts/accountsSlice";
import { fetchAccounts } from "../../../redux/dashboard/accounts/accountsThunks";

import {
  syncSymbols,
  fetchAccountSymbols,
  setSymbolSelection,
} from "../../../redux/dashboard/symbols/symbolsThunks";

import { clearSymbolsError } from "../../../redux/dashboard/symbols/symbolsSlice";

import "../../../css/symbols.css";

const SymbolsPage = () => {
  const dispatch = useDispatch();

  // ====================================================================
  // ACCOUNTS
  // ====================================================================

  const { accounts, selectedAccount } = useSelector((state) => state.accounts);

  // ====================================================================
  // SYMBOLS
  // ====================================================================

  const { symbols, loading, syncing, selecting, error, syncResult } =
    useSelector((state) => state.symbols);

  // ====================================================================
  // LOCAL UI STATE
  // ====================================================================

  const [searchTerm, setSearchTerm] = useState("");
  const [assetFilter, setAssetFilter] = useState("ALL");
  const [selectionFilter, setSelectionFilter] = useState("ALL");
  const [modalOpen, setModalOpen] = useState(false);

  // ====================================================================
  // CURRENT ACCOUNT
  // ====================================================================

  const accountId = selectedAccount?.id || null;

  // ====================================================================
  // LOAD ACCOUNTS
  // ====================================================================

  useEffect(() => {
    dispatch(fetchAccounts());
  }, [dispatch]);

  // ====================================================================
  // LOAD SYMBOLS WHEN ACCOUNT CHANGES
  // ====================================================================

  useEffect(() => {
    if (!accountId) {
      return;
    }

    setSearchTerm("");
    setAssetFilter("ALL");
    setSelectionFilter("ALL");

    dispatch(fetchAccountSymbols(accountId));
  }, [dispatch, accountId]);

  // ====================================================================
  // ASSET CLASSES
  // ====================================================================

  const assetClasses = useMemo(() => {
    return [
      ...new Set(
        symbols
          .map(
            (symbol) => symbol.asset_class || symbol.symbol?.asset_class || "",
          )
          .filter(Boolean),
      ),
    ].sort();
  }, [symbols]);

  // ====================================================================
  // SELECTED COUNT
  // ====================================================================

  const selectedCount = useMemo(() => {
    return symbols.filter((symbol) => Boolean(symbol.enabled)).length;
  }, [symbols]);

  // ====================================================================
  // UNSELECTED COUNT
  // ====================================================================

  const unselectedCount = useMemo(() => {
    return symbols.length - selectedCount;
  }, [symbols.length, selectedCount]);

  // ====================================================================
  // FILTER SYMBOLS
  // ====================================================================

  const filteredSymbols = useMemo(() => {
    const query = searchTerm.trim().toLowerCase();

    return symbols.filter((symbol) => {
      const name = (
        symbol.symbol_name ||
        symbol.name ||
        symbol.symbol?.name ||
        ""
      ).toLowerCase();

      const brokerSymbol = (symbol.broker_symbol || "").toLowerCase();

      const description = (
        symbol.description ||
        symbol.symbol?.description ||
        ""
      ).toLowerCase();

      const symbolAssetClass =
        symbol.asset_class || symbol.symbol?.asset_class || "";

      const isSelected = Boolean(symbol.enabled);

      // --------------------------------------------------------------
      // SEARCH
      // --------------------------------------------------------------

      const matchesSearch =
        !query ||
        name.includes(query) ||
        brokerSymbol.includes(query) ||
        description.includes(query);

      // --------------------------------------------------------------
      // ASSET CLASS
      // --------------------------------------------------------------

      const matchesAssetClass =
        assetFilter === "ALL" || symbolAssetClass === assetFilter;

      // --------------------------------------------------------------
      // SELECTION STATUS
      // --------------------------------------------------------------

      const matchesSelection =
        selectionFilter === "ALL" ||
        (selectionFilter === "SELECTED" && isSelected) ||
        (selectionFilter === "UNSELECTED" && !isSelected);

      return matchesSearch && matchesAssetClass && matchesSelection;
    });
  }, [symbols, searchTerm, assetFilter, selectionFilter]);

  // ====================================================================
  // ACCOUNT CHANGE
  // ====================================================================

  const handleAccountChange = (event) => {
    const nextAccountId = event.target.value;

    if (!nextAccountId) {
      return;
    }

    dispatch(selectAccount(nextAccountId));
  };

  // ====================================================================
  // SYNC MT5 SYMBOLS
  // ====================================================================

  const handleSync = async () => {
    if (!accountId || syncing) {
      return;
    }

    const result = await dispatch(syncSymbols(accountId));

    if (syncSymbols.fulfilled.match(result)) {
      await dispatch(fetchAccountSymbols(accountId));
    }
  };

  // ====================================================================
  // SAVE MODAL SELECTION
  // ====================================================================

  const handleSelectionChange = async (changes) => {
    if (!accountId || selecting) {
      return;
    }

    if (!changes.length) {
      setModalOpen(false);
      return;
    }

    for (const change of changes) {
      const result = await dispatch(
        setSymbolSelection({
          accountId,
          accountSymbolId: change.accountSymbolId,
          enabled: change.enabled,
        }),
      );

      if (setSymbolSelection.rejected.match(result)) {
        return;
      }
    }

    await dispatch(fetchAccountSymbols(accountId));

    setModalOpen(false);
  };

  // ====================================================================
  // DIRECT TABLE SELECTION
  // ====================================================================

  const handleToggleSelection = async (accountSymbol) => {
    if (!accountId || selecting) {
      return;
    }

    await dispatch(
      setSymbolSelection({
        accountId,
        accountSymbolId: accountSymbol.id,
        enabled: !Boolean(accountSymbol.enabled),
      }),
    );
  };

  // ====================================================================
  // REFRESH
  // ====================================================================

  const handleRefresh = () => {
    if (!accountId || loading) {
      return;
    }

    dispatch(fetchAccountSymbols(accountId));
  };

  // ====================================================================
  // RESET FILTERS
  // ====================================================================

  const handleResetFilters = () => {
    setSearchTerm("");
    setAssetFilter("ALL");
    setSelectionFilter("ALL");
  };

  // ====================================================================
  // NO ACCOUNTS
  // ====================================================================

  if (!accounts || accounts.length === 0) {
    return (
      <main className="symbols-page">
        <section className="symbols-header">
          <div>
            <span className="symbols-eyebrow">TRADING INSTRUMENTS</span>

            <h1>Symbols</h1>

            <p>
              Select the MT5 instruments available to your trading strategies.
            </p>
          </div>
        </section>

        <section className="symbols-card symbols-card--empty">
          <div className="symbols-empty">
            <FaCoins />

            <strong>No trading accounts</strong>

            <span>
              Create a trading account before managing trading symbols.
            </span>
          </div>
        </section>
      </main>
    );
  }

  // ====================================================================
  // MAIN PAGE
  // ====================================================================

  return (
    <main className="symbols-page">
      {/* ================================================================
          HEADER
      ================================================================ */}

      <section className="symbols-header">
        <div>
          <span className="symbols-eyebrow">TRADING INSTRUMENTS</span>

          <h1>Symbols</h1>

          <p>
            Select the MT5 instruments that AQE is permitted to trade on this
            account.
          </p>
        </div>

        <div className="symbols-header__actions">
          <button
            type="button"
            className="symbol-button symbol-button--muted"
            onClick={handleSync}
            disabled={syncing || loading || !selectedAccount}
            title="Synchronize symbols from MT5"
          >
            <FaSyncAlt className={syncing ? "symbols-spin" : ""} />

            {syncing ? "Syncing MT5..." : "Sync MT5 Symbols"}
          </button>

          <button
            type="button"
            className="symbol-button symbol-button--primary"
            onClick={() => setModalOpen(true)}
            disabled={loading || symbols.length === 0}
          >
            <FaCheckCircle />
            Select Symbols
          </button>
        </div>
      </section>

      {/* ================================================================
          ACCOUNT SELECTOR
      ================================================================ */}

      <section className="symbols-account-bar">
        <div className="symbols-account-selector">
          <label htmlFor="symbols-account">Trading Account</label>

          <select
            id="symbols-account"
            value={selectedAccount?.id || ""}
            onChange={handleAccountChange}
            disabled={loading || syncing}
          >
            <option value="" disabled>
              Select trading account
            </option>

            {accounts.map((account) => (
              <option key={account.id} value={account.id}>
                {account.account_name || "Trading Account"} — Login{" "}
                {account.login}
                {account.is_demo ? " · DEMO" : " · LIVE"}
              </option>
            ))}
          </select>
        </div>

        {selectedAccount && (
          <div className="symbols-account-info">
            <span>Broker</span>

            <strong>{selectedAccount.broker || "MT5"}</strong>

            <span>Server</span>

            <strong>{selectedAccount.server || "—"}</strong>

            <span>Status</span>

            <strong
              className={
                selectedAccount.status === "CONNECTED"
                  ? "symbols-status--connected"
                  : ""
              }
            >
              {selectedAccount.status || "UNKNOWN"}
            </strong>
          </div>
        )}
      </section>

      {/* ================================================================
          ERROR
      ================================================================ */}

      {error && (
        <div className="symbols-error">
          <span>
            {typeof error === "string"
              ? error
              : "Unable to process symbol request."}
          </span>

          <button
            type="button"
            onClick={() => dispatch(clearSymbolsError())}
            aria-label="Dismiss error"
          >
            ×
          </button>
        </div>
      )}

      {/* ================================================================
          SYNC SUCCESS
      ================================================================ */}

      {syncResult && (
        <div className="symbols-success">
          <FaCheckCircle />

          <span>
            MT5 synchronization completed.{" "}
            {syncResult.total_broker_symbols ?? 0} broker symbols processed.
          </span>
        </div>
      )}

      {/* ================================================================
          STATISTICS
      ================================================================ */}

      <section className="symbols-stats">
        <div className="symbol-stat">
          <FaCoins />

          <div>
            <span>Total Symbols</span>

            <strong>{symbols.length}</strong>
          </div>
        </div>

        <div className="symbol-stat symbol-stat--selected">
          <FaCheckCircle />

          <div>
            <span>Selected</span>

            <strong>{selectedCount}</strong>
          </div>
        </div>

        <div className="symbol-stat">
          <FaCoins />

          <div>
            <span>Unselected</span>

            <strong>{unselectedCount}</strong>
          </div>
        </div>

        <div className="symbol-stat">
          <FaCoins />

          <div>
            <span>Asset Classes</span>

            <strong>{assetClasses.length}</strong>
          </div>
        </div>
      </section>

      {/* ================================================================
          SEARCH / FILTER
      ================================================================ */}

      <section className="symbols-toolbar">
        <div className="symbols-toolbar__left">
          <div className="symbols-search">
            <FaSearch />

            <input
              type="text"
              value={searchTerm}
              onChange={(event) => setSearchTerm(event.target.value)}
              placeholder="Search symbols..."
              disabled={loading || !accountId}
            />
          </div>
        </div>

        <div className="symbols-filters">
          {/* ------------------------------------------------------------
              ASSET CLASS
          ------------------------------------------------------------ */}

          <select
            value={assetFilter}
            onChange={(event) => setAssetFilter(event.target.value)}
            disabled={loading || !accountId}
          >
            <option value="ALL">All asset classes</option>

            {assetClasses.map((assetClass) => (
              <option key={assetClass} value={assetClass}>
                {assetClass}
              </option>
            ))}
          </select>

          {/* ------------------------------------------------------------
              SELECTION STATUS
          ------------------------------------------------------------ */}

          <select
            value={selectionFilter}
            onChange={(event) => setSelectionFilter(event.target.value)}
            disabled={loading || !accountId}
          >
            <option value="ALL">All symbols</option>

            <option value="SELECTED">Selected ({selectedCount})</option>

            <option value="UNSELECTED">Unselected ({unselectedCount})</option>
          </select>

          {/* ------------------------------------------------------------
              RESET
          ------------------------------------------------------------ */}

          {(searchTerm ||
            assetFilter !== "ALL" ||
            selectionFilter !== "ALL") && (
            <button
              type="button"
              className="symbols-filter-reset"
              onClick={handleResetFilters}
              disabled={loading}
            >
              Reset
            </button>
          )}

          {/* ------------------------------------------------------------
              REFRESH
          ------------------------------------------------------------ */}

          <button
            type="button"
            className="symbols-refresh"
            onClick={handleRefresh}
            disabled={loading || !accountId}
            title="Refresh symbols"
          >
            <FaSyncAlt className={loading ? "symbols-spin" : ""} />
          </button>
        </div>
      </section>

      {/* ================================================================
          ACTIVE FILTER SUMMARY
      ================================================================ */}

      <div className="symbols-view-summary">
        <div>
          <span>VIEWING</span>

          <strong>
            {selectionFilter === "SELECTED"
              ? "Selected Symbols"
              : selectionFilter === "UNSELECTED"
                ? "Unselected Symbols"
                : "All Symbols"}
          </strong>
        </div>

        <span>
          Showing <strong>{filteredSymbols.length}</strong> of{" "}
          <strong>{symbols.length}</strong>
        </span>
      </div>

      {/* ================================================================
          SYMBOL TABLE
      ================================================================ */}

      <section className="symbols-card symbols-card--table">
        <header className="symbols-card__header">
          <div>
            <span>ACCOUNT SYMBOL UNIVERSE</span>

            <h2>Trading Symbols</h2>
          </div>

          <div className="symbols-card__header-meta">
            <span className="symbols-selected-badge">
              <FaCheckCircle />
              {selectedCount} selected
            </span>

            <span className="symbols-count">
              {filteredSymbols.length}{" "}
              {filteredSymbols.length === 1 ? "symbol" : "symbols"}
            </span>
          </div>
        </header>

        <div className="symbols-table-wrapper">
          <table className="symbols-table">
            <thead>
              <tr>
                <th>Symbol</th>

                <th>Broker Symbol</th>

                <th>Asset Class</th>

                <th>Precision</th>

                <th>Contract</th>

                <th>Volume Range</th>

                <th>Selection</th>
              </tr>
            </thead>

            <tbody>
              {loading && (
                <tr>
                  <td colSpan="7" className="symbols-empty">
                    <FaSyncAlt className="symbols-spin" />

                    <strong>Loading symbols...</strong>

                    <span>Loading the trading universe for this account.</span>
                  </td>
                </tr>
              )}

              {!loading && filteredSymbols.length === 0 && (
                <tr>
                  <td colSpan="7" className="symbols-empty">
                    <FaCoins />

                    <strong>
                      {symbols.length
                        ? "No matching symbols"
                        : "No symbols synchronized"}
                    </strong>

                    <span>
                      {symbols.length
                        ? "Try changing your search, asset class, or selection filter."
                        : "Synchronize this trading account with MT5 to import its available instruments."}
                    </span>

                    {symbols.length > 0 && (
                      <button
                        type="button"
                        className="symbol-button symbol-button--muted"
                        onClick={handleResetFilters}
                      >
                        Clear Filters
                      </button>
                    )}

                    {!symbols.length && (
                      <button
                        type="button"
                        className="symbol-button symbol-button--primary"
                        onClick={handleSync}
                        disabled={syncing}
                      >
                        <FaSyncAlt className={syncing ? "symbols-spin" : ""} />

                        {syncing ? "Syncing..." : "Sync MT5 Symbols"}
                      </button>
                    )}
                  </td>
                </tr>
              )}

              {!loading &&
                filteredSymbols.map((accountSymbol) => {
                  const symbolName =
                    accountSymbol.symbol_name ||
                    accountSymbol.name ||
                    accountSymbol.symbol?.name ||
                    accountSymbol.broker_symbol ||
                    "Unknown";

                  const assetClass =
                    accountSymbol.asset_class ||
                    accountSymbol.symbol?.asset_class ||
                    "OTHER";

                  const enabled = Boolean(accountSymbol.enabled);

                  return (
                    <tr
                      key={accountSymbol.id}
                      className={enabled ? "symbol-row--selected" : ""}
                    >
                      {/* ------------------------------------------------
                            SYMBOL
                        ------------------------------------------------ */}

                      <td>
                        <div className="symbol-name">
                          <div className="symbol-icon">
                            <FaCoins />
                          </div>

                          <div>
                            <strong>{symbolName}</strong>

                            <span>
                              {accountSymbol.path || "MT5 instrument"}
                            </span>
                          </div>
                        </div>
                      </td>

                      {/* ------------------------------------------------
                            BROKER SYMBOL
                        ------------------------------------------------ */}

                      <td>
                        <strong>{accountSymbol.broker_symbol || "—"}</strong>
                      </td>

                      {/* ------------------------------------------------
                            ASSET CLASS
                        ------------------------------------------------ */}

                      <td>
                        <span className="symbol-asset">{assetClass}</span>
                      </td>

                      {/* ------------------------------------------------
                            PRECISION
                        ------------------------------------------------ */}

                      <td>
                        <strong>{accountSymbol.digits ?? "—"}</strong>

                        <span className="symbol-subvalue">digits</span>
                      </td>

                      {/* ------------------------------------------------
                            CONTRACT
                        ------------------------------------------------ */}

                      <td>{accountSymbol.contract_size ?? "—"}</td>

                      {/* ------------------------------------------------
                            VOLUME
                        ------------------------------------------------ */}

                      <td>
                        {accountSymbol.min_volume ?? "—"} -{" "}
                        {accountSymbol.max_volume ?? "—"}
                        <span className="symbol-subvalue">
                          step {accountSymbol.volume_step ?? "—"}
                        </span>
                      </td>

                      {/* ------------------------------------------------
                            SELECTION
                        ------------------------------------------------ */}

                      <td>
                        <button
                          type="button"
                          className={`symbol-selection ${
                            enabled ? "symbol-selection--enabled" : ""
                          }`}
                          onClick={() => handleToggleSelection(accountSymbol)}
                          disabled={selecting}
                          title={enabled ? "Disable symbol" : "Enable symbol"}
                        >
                          <span className="symbol-selection__indicator">
                            {enabled && <FaCheckCircle />}
                          </span>

                          <span>{enabled ? "Enabled" : "Disabled"}</span>
                        </button>
                      </td>
                    </tr>
                  );
                })}
            </tbody>
          </table>
        </div>
      </section>

      {/* ================================================================
          SYMBOL SELECTION MODAL
      ================================================================ */}

      <SymbolForm
        isOpen={modalOpen}
        onClose={() => !selecting && setModalOpen(false)}
        symbols={symbols}
        onSelectionChange={handleSelectionChange}
        loading={selecting}
      />
    </main>
  );
};

export default SymbolsPage;
