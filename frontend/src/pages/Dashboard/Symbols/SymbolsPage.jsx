import { useEffect, useMemo, useRef, useState } from "react";

import { useVirtualizer } from "@tanstack/react-virtual";
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

  const { accounts = [], selectedAccount } = useSelector(
    (state) => state.accounts,
  );

  // ====================================================================
  // SYMBOLS
  // ====================================================================

  const {
    symbolsByAccount = {},
    accountSymbolsLoading = {},
    syncing,
    selecting,
    error,
    syncResult,
  } = useSelector((state) => state.symbols);

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

  const accountId = selectedAccount?.id ?? null;

  const accountKey = accountId == null ? null : String(accountId);

  const accountLoading = Boolean(
    accountKey && accountSymbolsLoading[accountKey],
  );

  const hasCachedSymbols =
    accountKey !== null &&
    Object.prototype.hasOwnProperty.call(symbolsByAccount, accountKey);

  const symbols = useMemo(() => {
    if (!accountKey) {
      return [];
    }

    const accountSymbols = symbolsByAccount[accountKey];

    return Array.isArray(accountSymbols) ? accountSymbols : [];
  }, [symbolsByAccount, accountKey]);

  /*
   * Only show a loading placeholder when there are no existing
   * symbols to display. Cached rows remain visible during refreshes.
   */
  const showSymbolsLoading = accountLoading && symbols.length === 0;

  // ====================================================================
  // VIRTUAL TABLE
  // ====================================================================

  const tableWrapperRef = useRef(null);

  // ====================================================================
  // LOAD ACCOUNTS
  // ====================================================================

  useEffect(() => {
    dispatch(fetchAccounts());
  }, [dispatch]);

  // ====================================================================
  // RESET FILTERS WHEN THE ACCOUNT CHANGES
  // ====================================================================

  useEffect(() => {
    setSearchTerm("");
    setAssetFilter("ALL");
    setSelectionFilter("ALL");
  }, [accountId]);

  // ====================================================================
  // LOAD SYMBOLS ONLY WHEN THEY ARE NOT CACHED
  // ====================================================================

  useEffect(() => {
    if (!accountId || hasCachedSymbols) {
      return;
    }

    dispatch(fetchAccountSymbols(accountId));
  }, [dispatch, accountId, hasCachedSymbols]);

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

      const matchesSearch =
        !query ||
        name.includes(query) ||
        brokerSymbol.includes(query) ||
        description.includes(query);

      const matchesAssetClass =
        assetFilter === "ALL" || symbolAssetClass === assetFilter;

      const matchesSelection =
        selectionFilter === "ALL" ||
        (selectionFilter === "SELECTED" && isSelected) ||
        (selectionFilter === "UNSELECTED" && !isSelected);

      return matchesSearch && matchesAssetClass && matchesSelection;
    });
  }, [symbols, searchTerm, assetFilter, selectionFilter]);

  // ====================================================================
  // VIRTUALIZED ROWS
  // ====================================================================

  const rowVirtualizer = useVirtualizer({
    count: filteredSymbols.length,
    getScrollElement: () => tableWrapperRef.current,
    estimateSize: () => 72,
    overscan: 8,
    measureElement: (element) => element?.getBoundingClientRect().height ?? 72,
  });

  const virtualRows = rowVirtualizer.getVirtualItems();

  const totalVirtualHeight = rowVirtualizer.getTotalSize();

  const firstVirtualRow = virtualRows[0];
  const lastVirtualRow = virtualRows[virtualRows.length - 1];

  const topSpacerHeight = firstVirtualRow?.start ?? 0;

  const bottomSpacerHeight = lastVirtualRow
    ? Math.max(0, totalVirtualHeight - lastVirtualRow.end)
    : 0;

  // ====================================================================
  // RESET TABLE SCROLL POSITION
  // ====================================================================

  useEffect(() => {
    if (!tableWrapperRef.current) {
      return;
    }

    tableWrapperRef.current.scrollTop = 0;
    rowVirtualizer.scrollToIndex(0);
  }, [accountId, searchTerm, assetFilter, selectionFilter, rowVirtualizer]);

  // ====================================================================
  // ACCOUNT CHANGE
  // ====================================================================

  const handleAccountChange = (event) => {
    const nextAccountId = event.target.value;

    if (!nextAccountId) {
      return;
    }

    if (String(nextAccountId) === String(accountId)) {
      return;
    }

    dispatch(selectAccount(nextAccountId));
  };

  // ====================================================================
  // SYNC MT5 SYMBOLS
  // ====================================================================

  const handleSync = async () => {
    if (!accountId || syncing || accountLoading) {
      return;
    }

    dispatch(clearSymbolsError());

    try {
      const result = await dispatch(syncSymbols(accountId));

      if (syncSymbols.fulfilled.match(result)) {
        /*
         * Synchronization can add instruments or update metadata.
         * Reload the account catalogue after a successful sync.
         */
        await dispatch(fetchAccountSymbols(accountId)).unwrap();
      }
    } catch (syncError) {
      console.error("Failed to synchronize MT5 symbols:", syncError);
    }
  };

  // ====================================================================
  // SAVE MODAL SELECTION
  // ====================================================================

  const handleSelectionChange = async (changes) => {
    if (!accountId || selecting) {
      return;
    }

    if (!Array.isArray(changes) || changes.length === 0) {
      setModalOpen(false);
      return;
    }

    /*
     * Preserve the existing API contract. Each changed symbol is
     * updated through the account-specific selection endpoint.
     */
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

    /*
     * Refresh the local account catalogue after all updates.
     */
    try {
      await dispatch(fetchAccountSymbols(accountId)).unwrap();

      setModalOpen(false);
    } catch (refreshError) {
      console.error("Failed to reload account symbols:", refreshError);
    }
  };

  // ====================================================================
  // DIRECT TABLE SELECTION
  // ====================================================================

  const handleToggleSelection = async (accountSymbol) => {
    if (!accountId || selecting || !accountSymbol?.id) {
      return;
    }

    await dispatch(
      setSymbolSelection({
        accountId,
        accountSymbolId: accountSymbol.id,
        enabled: !accountSymbol.enabled,
      }),
    );
  };

  // ====================================================================
  // REFRESH
  // ====================================================================

  const handleRefresh = () => {
    if (!accountId || accountLoading) {
      return;
    }

    dispatch(clearSymbolsError());
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
      {/* HEADER */}

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
            disabled={syncing || accountLoading || !selectedAccount}
            title="Synchronize symbols from MT5"
          >
            <FaSyncAlt className={syncing ? "symbols-spin" : ""} />

            {syncing ? "Syncing MT5..." : "Sync MT5 Symbols"}
          </button>

          <button
            type="button"
            className="symbol-button symbol-button--primary"
            onClick={() => setModalOpen(true)}
            disabled={showSymbolsLoading || !accountId || symbols.length === 0}
          >
            <FaCheckCircle />
            Select Symbols
          </button>
        </div>
      </section>

      {/* ACCOUNT SELECTOR */}

      <section className="symbols-account-bar">
        <div className="symbols-account-selector">
          <label htmlFor="symbols-account">Trading Account</label>

          <select
            id="symbols-account"
            value={selectedAccount?.id || ""}
            onChange={handleAccountChange}
            disabled={syncing}
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

      {/* ERROR */}

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

      {/* SYNC SUCCESS */}

      {syncResult && (
        <div className="symbols-success">
          <FaCheckCircle />

          <span>
            MT5 synchronization completed.{" "}
            {syncResult.total_broker_symbols ?? 0} broker symbols processed.
          </span>
        </div>
      )}

      {/* STATISTICS */}

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

      {/* SEARCH / FILTER */}

      <section className="symbols-toolbar">
        <div className="symbols-toolbar__left">
          <div className="symbols-search">
            <FaSearch />

            <input
              type="text"
              value={searchTerm}
              onChange={(event) => setSearchTerm(event.target.value)}
              placeholder="Search symbols..."
              disabled={showSymbolsLoading || !accountId}
            />
          </div>
        </div>

        <div className="symbols-filters">
          <select
            value={assetFilter}
            onChange={(event) => setAssetFilter(event.target.value)}
            disabled={showSymbolsLoading || !accountId}
          >
            <option value="ALL">All asset classes</option>

            {assetClasses.map((assetClass) => (
              <option key={assetClass} value={assetClass}>
                {assetClass}
              </option>
            ))}
          </select>

          <select
            value={selectionFilter}
            onChange={(event) => setSelectionFilter(event.target.value)}
            disabled={showSymbolsLoading || !accountId}
          >
            <option value="ALL">All symbols</option>

            <option value="SELECTED">Selected ({selectedCount})</option>

            <option value="UNSELECTED">Unselected ({unselectedCount})</option>
          </select>

          {(searchTerm ||
            assetFilter !== "ALL" ||
            selectionFilter !== "ALL") && (
            <button
              type="button"
              className="symbols-filter-reset"
              onClick={handleResetFilters}
              disabled={showSymbolsLoading}
            >
              Reset
            </button>
          )}

          <button
            type="button"
            className="symbols-refresh"
            onClick={handleRefresh}
            disabled={!accountId || accountLoading}
            title="Refresh symbols"
          >
            <FaSyncAlt className={accountLoading ? "symbols-spin" : ""} />
          </button>
        </div>
      </section>

      {/* ACTIVE FILTER SUMMARY */}

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

      {/* SYMBOL TABLE */}

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

        <div ref={tableWrapperRef} className="symbols-table-wrapper">
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
              {/* LOADING */}

              {showSymbolsLoading && (
                <tr>
                  <td colSpan={7} className="symbols-empty">
                    <FaSyncAlt className="symbols-spin" />

                    <strong>Loading symbols...</strong>

                    <span>Loading the trading universe for this account.</span>
                  </td>
                </tr>
              )}

              {/* EMPTY / NO MATCHES */}

              {!showSymbolsLoading && filteredSymbols.length === 0 && (
                <tr>
                  <td colSpan={7} className="symbols-empty">
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

                    {symbols.length === 0 && (
                      <button
                        type="button"
                        className="symbol-button symbol-button--primary"
                        onClick={handleSync}
                        disabled={syncing || accountLoading || !accountId}
                      >
                        <FaSyncAlt className={syncing ? "symbols-spin" : ""} />

                        {syncing ? "Syncing..." : "Sync MT5 Symbols"}
                      </button>
                    )}
                  </td>
                </tr>
              )}

              {/* VIRTUALIZED TABLE */}

              {!showSymbolsLoading && filteredSymbols.length > 0 && (
                <>
                  {topSpacerHeight > 0 && (
                    <tr aria-hidden="true" className="symbols-virtual-spacer">
                      <td
                        colSpan={7}
                        style={{
                          height: topSpacerHeight,
                          padding: 0,
                          border: 0,
                        }}
                      />
                    </tr>
                  )}

                  {virtualRows.map((virtualRow) => {
                    const accountSymbol = filteredSymbols[virtualRow.index];

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
                        ref={rowVirtualizer.measureElement}
                        data-index={virtualRow.index}
                        className={enabled ? "symbol-row--selected" : ""}
                      >
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

                        <td>
                          <strong>{accountSymbol.broker_symbol || "—"}</strong>
                        </td>

                        <td>
                          <span className="symbol-asset">{assetClass}</span>
                        </td>

                        <td>
                          <strong>{accountSymbol.digits ?? "—"}</strong>

                          <span className="symbol-subvalue">digits</span>
                        </td>

                        <td>{accountSymbol.contract_size ?? "—"}</td>

                        <td>
                          {accountSymbol.min_volume ?? "—"} -{" "}
                          {accountSymbol.max_volume ?? "—"}
                          <span className="symbol-subvalue">
                            step {accountSymbol.volume_step ?? "—"}
                          </span>
                        </td>

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

                  {bottomSpacerHeight > 0 && (
                    <tr aria-hidden="true" className="symbols-virtual-spacer">
                      <td
                        colSpan={7}
                        style={{
                          height: bottomSpacerHeight,
                          padding: 0,
                          border: 0,
                        }}
                      />
                    </tr>
                  )}
                </>
              )}
            </tbody>
          </table>
        </div>
      </section>

      {/* SYMBOL SELECTION MODAL */}

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
