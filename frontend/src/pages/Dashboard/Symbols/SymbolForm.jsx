import { useEffect, useMemo, useState } from "react";

import { FaCheck, FaCheckCircle, FaSearch, FaTimes } from "react-icons/fa";

import "../../../css/symbols.css";

const SymbolForm = ({
  isOpen,
  onClose,
  symbols = [],
  onSelectionChange,
  loading = false,
}) => {
  // ====================================================================
  // LOCAL STATE
  // ====================================================================

  const [search, setSearch] = useState("");
  const [assetClass, setAssetClass] = useState("ALL");
  const [selectionFilter, setSelectionFilter] = useState("ALL");

  const [localSelection, setLocalSelection] = useState({});

  // ====================================================================
  // INITIALIZE LOCAL SELECTION
  // ====================================================================

  useEffect(() => {
    if (!isOpen) {
      return;
    }

    const selection = {};

    symbols.forEach((symbol) => {
      selection[symbol.id] = Boolean(symbol.enabled);
    });

    setLocalSelection(selection);
    setSearch("");
    setAssetClass("ALL");
    setSelectionFilter("ALL");
  }, [isOpen, symbols]);

  // ====================================================================
  // ASSET CLASSES
  // ====================================================================

  const assetClasses = useMemo(() => {
    const classes = new Set();

    symbols.forEach((symbol) => {
      const value = symbol.asset_class || symbol.symbol?.asset_class;

      if (value) {
        classes.add(value);
      }
    });

    return Array.from(classes).sort();
  }, [symbols]);

  // ====================================================================
  // COUNTS
  // ====================================================================

  const selectedCount = useMemo(() => {
    return Object.values(localSelection).filter(Boolean).length;
  }, [localSelection]);

  const unselectedCount = symbols.length - selectedCount;

  // ====================================================================
  // FILTER SYMBOLS
  // ====================================================================

  const filteredSymbols = useMemo(() => {
    const normalizedSearch = search.trim().toLowerCase();

    return symbols.filter((symbol) => {
      const name = (
        symbol.symbol_name ||
        symbol.name ||
        symbol.symbol?.name ||
        ""
      ).toLowerCase();

      const brokerSymbol = (symbol.broker_symbol || "").toLowerCase();

      const currentAssetClass =
        symbol.asset_class || symbol.symbol?.asset_class || "";

      const isSelected = Boolean(localSelection[symbol.id]);

      // --------------------------------------------------------------
      // SEARCH
      // --------------------------------------------------------------

      const matchesSearch =
        !normalizedSearch ||
        name.includes(normalizedSearch) ||
        brokerSymbol.includes(normalizedSearch);

      // --------------------------------------------------------------
      // ASSET CLASS
      // --------------------------------------------------------------

      const matchesAssetClass =
        assetClass === "ALL" || currentAssetClass === assetClass;

      // --------------------------------------------------------------
      // SELECTION
      // --------------------------------------------------------------

      const matchesSelection =
        selectionFilter === "ALL" ||
        (selectionFilter === "SELECTED" && isSelected) ||
        (selectionFilter === "UNSELECTED" && !isSelected);

      return matchesSearch && matchesAssetClass && matchesSelection;
    });
  }, [symbols, search, assetClass, selectionFilter, localSelection]);

  // ====================================================================
  // HELPERS
  // ====================================================================

  const getSymbolName = (symbol) =>
    symbol.symbol_name ||
    symbol.name ||
    symbol.symbol?.name ||
    symbol.broker_symbol ||
    "Unknown";

  const getAssetClass = (symbol) =>
    symbol.asset_class || symbol.symbol?.asset_class || "—";

  // ====================================================================
  // TOGGLE SYMBOL
  // ====================================================================

  const handleToggle = (symbolId) => {
    setLocalSelection((previous) => ({
      ...previous,
      [symbolId]: !previous[symbolId],
    }));
  };

  // ====================================================================
  // SELECT VISIBLE
  // ====================================================================

  const handleSelectVisible = () => {
    setLocalSelection((previous) => {
      const next = { ...previous };

      filteredSymbols.forEach((symbol) => {
        next[symbol.id] = true;
      });

      return next;
    });
  };

  // ====================================================================
  // DESELECT VISIBLE
  // ====================================================================

  const handleDeselectVisible = () => {
    setLocalSelection((previous) => {
      const next = { ...previous };

      filteredSymbols.forEach((symbol) => {
        next[symbol.id] = false;
      });

      return next;
    });
  };

  // ====================================================================
  // SELECT ALL SYMBOLS
  // ====================================================================

  const handleSelectAllSymbols = () => {
    setLocalSelection((previous) => {
      const next = { ...previous };

      symbols.forEach((symbol) => {
        next[symbol.id] = true;
      });

      return next;
    });
  };

  // ====================================================================
  // DESELECT ALL SYMBOLS
  // ====================================================================

  const handleDeselectAllSymbols = () => {
    setLocalSelection((previous) => {
      const next = { ...previous };

      symbols.forEach((symbol) => {
        next[symbol.id] = false;
      });

      return next;
    });
  };

  // ====================================================================
  // RESET FILTERS
  // ====================================================================

  const handleResetFilters = () => {
    setSearch("");
    setAssetClass("ALL");
    setSelectionFilter("ALL");
  };

  // ====================================================================
  // SAVE
  // ====================================================================

  const handleSave = async () => {
    if (loading) {
      return;
    }

    const changes = symbols
      .filter(
        (symbol) =>
          Boolean(symbol.enabled) !== Boolean(localSelection[symbol.id]),
      )
      .map((symbol) => ({
        accountSymbolId: symbol.id,
        enabled: Boolean(localSelection[symbol.id]),
      }));

    await onSelectionChange(changes);
  };

  // ====================================================================
  // CLOSED
  // ====================================================================

  if (!isOpen) {
    return null;
  }

  // ====================================================================
  // RENDER
  // ====================================================================

  return (
    <div
      className="symbol-modal-overlay"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget && !loading) {
          onClose();
        }
      }}
    >
      <div
        className="symbol-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="symbol-selector-title"
      >
        {/* ============================================================
            HEADER
        ============================================================ */}

        <header className="symbol-modal__header">
          <div>
            <span className="symbols-eyebrow">TRADING UNIVERSE</span>

            <h2 id="symbol-selector-title">Select Trading Symbols</h2>

            <p>
              Select the MT5 instruments that AQE is allowed to trade on this
              account.
            </p>
          </div>

          <button
            type="button"
            className="symbol-modal__close"
            onClick={onClose}
            disabled={loading}
            aria-label="Close"
          >
            <FaTimes />
          </button>
        </header>

        {/* ============================================================
            TOOLBAR
        ============================================================ */}

        <div className="symbol-selector__toolbar">
          <div className="symbol-selector__search">
            <FaSearch />

            <input
              type="text"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="Search symbols..."
              disabled={loading}
            />
          </div>

          <div className="symbol-selector__filter">
            <select
              value={assetClass}
              onChange={(event) => setAssetClass(event.target.value)}
              disabled={loading}
            >
              <option value="ALL">All Asset Classes</option>

              {assetClasses.map((value) => (
                <option key={value} value={value}>
                  {value}
                </option>
              ))}
            </select>
          </div>

          <div className="symbol-selector__filter">
            <select
              value={selectionFilter}
              onChange={(event) => setSelectionFilter(event.target.value)}
              disabled={loading}
            >
              <option value="ALL">All Symbols</option>

              <option value="SELECTED">Selected</option>

              <option value="UNSELECTED">Unselected</option>
            </select>
          </div>

          <div className="symbol-selector__count">
            <span>Selected</span>

            <strong>{selectedCount}</strong>

            <small>/ {symbols.length}</small>
          </div>
        </div>

        {/* ============================================================
            FILTER SUMMARY
        ============================================================ */}

        <div className="symbol-selector__summary">
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
            {filteredSymbols.length}{" "}
            {filteredSymbols.length === 1 ? "symbol" : "symbols"}
          </span>
        </div>

        {/* ============================================================
            BULK ACTIONS
        ============================================================ */}

        <div className="symbol-selector__actions">
          <button
            type="button"
            onClick={handleSelectVisible}
            disabled={loading || filteredSymbols.length === 0}
          >
            Select Visible
          </button>

          <button
            type="button"
            onClick={handleDeselectVisible}
            disabled={loading || filteredSymbols.length === 0}
          >
            Deselect Visible
          </button>

          <span className="symbol-selector__actions-divider" />

          <button
            type="button"
            onClick={handleSelectAllSymbols}
            disabled={loading || symbols.length === 0}
          >
            Select All
          </button>

          <button
            type="button"
            onClick={handleDeselectAllSymbols}
            disabled={loading || symbols.length === 0}
          >
            Deselect All
          </button>

          {(search || assetClass !== "ALL" || selectionFilter !== "ALL") && (
            <button
              type="button"
              className="symbol-selector__reset"
              onClick={handleResetFilters}
              disabled={loading}
            >
              Reset Filters
            </button>
          )}
        </div>

        {/* ============================================================
            SYMBOL LIST
        ============================================================ */}

        <div className="symbol-selector__list">
          {loading && symbols.length === 0 ? (
            <div className="symbol-selector__empty">Loading MT5 symbols...</div>
          ) : filteredSymbols.length === 0 ? (
            <div className="symbol-selector__empty">
              <FaSearch />

              <strong>
                {symbols.length === 0
                  ? "No MT5 symbols synchronized"
                  : "No matching symbols"}
              </strong>

              <span>
                {symbols.length === 0
                  ? "Synchronize this account with MT5 first."
                  : "Try changing your search or filters."}
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
            </div>
          ) : (
            filteredSymbols.map((symbol) => {
              const enabled = Boolean(localSelection[symbol.id]);

              return (
                <button
                  type="button"
                  key={symbol.id}
                  className={`symbol-selector__row ${
                    enabled ? "symbol-selector__row--selected" : ""
                  }`}
                  onClick={() => handleToggle(symbol.id)}
                  disabled={loading}
                >
                  {/* CHECKBOX */}

                  <span
                    className={`symbol-selector__checkbox ${
                      enabled ? "symbol-selector__checkbox--checked" : ""
                    }`}
                  >
                    {enabled && <FaCheck />}
                  </span>

                  {/* IDENTITY */}

                  <span className="symbol-selector__identity">
                    <strong>{getSymbolName(symbol)}</strong>

                    <small>{symbol.broker_symbol || "—"}</small>
                  </span>

                  {/* ASSET */}

                  <span className="symbol-selector__asset">
                    {getAssetClass(symbol)}
                  </span>

                  {/* STATUS */}

                  <span
                    className={`symbol-selector__status ${
                      enabled ? "symbol-selector__status--enabled" : ""
                    }`}
                  >
                    {enabled ? (
                      <>
                        <FaCheckCircle />
                        Enabled
                      </>
                    ) : (
                      "Disabled"
                    )}
                  </span>
                </button>
              );
            })
          )}
        </div>

        {/* ============================================================
            FOOTER
        ============================================================ */}

        <footer className="symbol-form__footer">
          <div className="symbol-form__footer-info">
            <span>{selectedCount}</span> of {symbols.length} symbols selected
          </div>

          <div className="symbol-form__footer-actions">
            <button
              type="button"
              className="symbol-button symbol-button--muted"
              onClick={onClose}
              disabled={loading}
            >
              Cancel
            </button>

            <button
              type="button"
              className="symbol-button symbol-button--primary"
              onClick={handleSave}
              disabled={loading}
            >
              {loading ? "Saving..." : "Save Selection"}
            </button>
          </div>
        </footer>
      </div>
    </div>
  );
};

export default SymbolForm;
