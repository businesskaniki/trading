import { useEffect, useMemo, useState } from "react";
import { FaExchangeAlt, FaSearch, FaSyncAlt } from "react-icons/fa";
import { useDispatch, useSelector } from "react-redux";

import {
  fetchPositions,
  syncPositions,
} from "../../../redux/dashboard/positions/positionsThunks";

import { fetchAccounts } from "../../../redux/dashboard/accounts/accountsThunks";

import {
  fetchAccountSymbols,
} from "../../../redux/dashboard/symbols/symbolsThunks";

import "../../../css/positions.css";

const Positions = () => {
  const dispatch = useDispatch();

  const {
    positions,
    loading,
    syncing,
    error,
  } = useSelector((state) => state.positions);

  const accounts = useSelector(
    (state) => state.accounts?.accounts || [],
  );

  const symbols = useSelector(
    (state) => state.symbols?.symbols || [],
  );

  const [query, setQuery] = useState("");

  /*
   * Accounts represented by the current positions.
   *
   * Positions belong to specific trading accounts, so their
   * account-specific symbol mappings must be loaded.
   */
  const positionAccountIds = useMemo(() => {
    return [
      ...new Set(
        positions
          .map((position) => position.account_id)
          .filter(Boolean),
      ),
    ];
  }, [positions]);

  /*
   * Load positions and accounts.
   */
  useEffect(() => {
    dispatch(fetchPositions());
    dispatch(fetchAccounts());
  }, [dispatch]);

  /*
   * Load AccountSymbol records instead of the old global
   * fetchSymbols() endpoint.
   */
  useEffect(() => {
    if (!positionAccountIds.length) {
      return;
    }

    positionAccountIds.forEach((accountId) => {
      dispatch(fetchAccountSymbols(accountId));
    });
  }, [dispatch, positionAccountIds]);

  /*
   * Resolve account name.
   */
  const accountName = (id) => {
    const account = accounts.find(
      (item) => item.id === id,
    );

    return (
      account?.account_name ||
      account?.account_number ||
      String(id || "-").slice(0, 8)
    );
  };

  /*
   * Resolve canonical symbol name from AccountSymbol.
   */
  const symbolName = (id) => {
    const accountSymbol = symbols.find(
      (item) =>
        item.symbol_id === id ||
        item.symbol?.id === id,
    );

    return (
      accountSymbol?.symbol_name ||
      accountSymbol?.name ||
      accountSymbol?.symbol?.name ||
      accountSymbol?.broker_symbol ||
      String(id || "-").slice(0, 8)
    );
  };

  /*
   * Resolve broker-native symbol.
   *
   * Example:
   *
   * EURUSD     -> canonical symbol
   * EURUSD.s   -> broker symbol
   */
  const brokerSymbolName = (position) => {
    const accountSymbol = symbols.find(
      (item) =>
        item.symbol_id === position.symbol_id ||
        item.symbol?.id === position.symbol_id,
    );

    return (
      accountSymbol?.broker_symbol ||
      ""
    );
  };

  /*
   * Filter visible positions.
   */
  const visiblePositions = useMemo(
    () =>
      positions.filter((position) => {
        const symbol = symbolName(
          position.symbol_id,
        );

        const brokerSymbol =
          brokerSymbolName(position);

        const text = `
          ${position.strategy || ""}
          ${symbol}
          ${brokerSymbol}
          ${position.ticket || ""}
          ${position.direction || ""}
          ${position.comment || ""}
        `.toLowerCase();

        return (
          !query ||
          text.includes(query.toLowerCase())
        );
      }),
    [positions, query, symbols],
  );

  /*
   * Refresh broker positions and their associated
   * account-specific symbol mappings.
   */
  const handleSync = async () => {
    await dispatch(syncPositions());

    /*
     * Refresh the account-specific symbol universe after
     * broker synchronization.
     */
    positionAccountIds.forEach((accountId) => {
      dispatch(fetchAccountSymbols(accountId));
    });
  };

  return (
    <main className="positions-page">
      {/* =====================================================
          HEADER
      ====================================================== */}

      <header className="positions-header">
        <div>
          <span className="positions-eyebrow">
            LIVE BROKER STATE
          </span>

          <h1>Positions</h1>

          <p>
            Monitor positions created and updated by the
            execution system.
          </p>
        </div>

        <button
          type="button"
          className="positions-refresh"
          onClick={handleSync}
          disabled={syncing}
        >
          <FaSyncAlt
            className={
              syncing
                ? "positions-spin"
                : ""
            }
          />

          {syncing
            ? "Syncing..."
            : "Sync broker"}
        </button>
      </header>

      {/* =====================================================
          ERROR
      ====================================================== */}

      {error && (
        <div className="positions-error">
          {typeof error === "string"
            ? error
            : "Unable to synchronize broker positions."}
        </div>
      )}

      {/* =====================================================
          TOOLBAR
      ====================================================== */}

      <section className="positions-toolbar">
        <div className="positions-search">
          <FaSearch />

          <input
            value={query}
            onChange={(event) =>
              setQuery(event.target.value)
            }
            placeholder="Search strategy, symbol or ticket..."
          />
        </div>

        <span>
          {visiblePositions.length} open position
          {visiblePositions.length === 1
            ? ""
            : "s"}
        </span>
      </section>

      {/* =====================================================
          POSITIONS TABLE
      ====================================================== */}

      <section className="positions-table-wrap">
        <table className="positions-table">
          <thead>
            <tr>
              <th>Position</th>
              <th>Instrument</th>
              <th>Account</th>
              <th>Volume</th>
              <th>Entry / Current</th>
              <th>P/L</th>
              <th>Stops</th>
            </tr>
          </thead>

          <tbody>
            {/* Loading */}
            {loading && (
              <tr>
                <td
                  colSpan="7"
                  className="positions-empty"
                >
                  <FaSyncAlt className="positions-spin" />

                  <strong>
                    Loading positions...
                  </strong>
                </td>
              </tr>
            )}

            {/* Empty */}
            {!loading &&
              visiblePositions.length === 0 && (
                <tr>
                  <td
                    colSpan="7"
                    className="positions-empty"
                  >
                    <FaExchangeAlt />

                    <strong>
                      No broker positions
                    </strong>

                    <span>
                      Positions will appear here
                      after an order is filled.
                    </span>
                  </td>
                </tr>
              )}

            {/* Positions */}
            {!loading &&
              visiblePositions.map((position) => {
                const symbol =
                  symbolName(
                    position.symbol_id,
                  );

                const brokerSymbol =
                  brokerSymbolName(
                    position,
                  );

                const floatingProfit = Number(
                  position.floating_profit ?? 0,
                );

                return (
                  <tr key={position.id}>
                    {/* POSITION */}
                    <td>
                      <strong>
                        #{position.ticket || "—"}
                      </strong>

                      <span>
                        {position.direction ||
                          "—"}{" "}
                        ·{" "}
                        {position.strategy ||
                          "Manual"}
                      </span>
                    </td>

                    {/* INSTRUMENT */}
                    <td>
                      <strong>
                        {symbol}
                      </strong>

                      <span>
                        {brokerSymbol ||
                          position.comment ||
                          "Broker position"}
                      </span>
                    </td>

                    {/* ACCOUNT */}
                    <td>
                      {accountName(
                        position.account_id,
                      )}
                    </td>

                    {/* VOLUME */}
                    <td>
                      {position.current_volume ??
                        position.volume ??
                        "—"}
                    </td>

                    {/* ENTRY / CURRENT */}
                    <td>
                      {position.entry_price ??
                        "—"}{" "}
                      /{" "}
                      {position.current_price ??
                        "—"}
                    </td>

                    {/* P/L */}
                    <td
                      className={
                        floatingProfit >= 0
                          ? "positive"
                          : "negative"
                      }
                    >
                      {position.floating_profit ??
                        "0"}
                    </td>

                    {/* STOPS */}
                    <td>
                      SL{" "}
                      {position.stop_loss ||
                        "-"}
                      <br />
                      TP{" "}
                      {position.take_profit ||
                        "-"}
                    </td>
                  </tr>
                );
              })}
          </tbody>
        </table>
      </section>
    </main>
  );
};

export default Positions;