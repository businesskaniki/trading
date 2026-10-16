import { useEffect, useMemo, useState } from "react";
import { FaExchangeAlt, FaSearch, FaSyncAlt } from "react-icons/fa";
import { useDispatch, useSelector } from "react-redux";

import {
  fetchPositions,
  syncPositions,
} from "../../../redux/dashboard/positions/positionsThunks";

import { fetchAccounts } from "../../../redux/dashboard/accounts/accountsThunks";

import { fetchAccountSymbols } from "../../../redux/dashboard/symbols/symbolsThunks";

import { usePositionWebSocket } from "../../../hooks/usePositionWebSocket";
import { getAccessToken } from "../../../api/axios";

import "../../../css/positions.css";

const Positions = () => {
  const dispatch = useDispatch();

  const {
    positions: reduxPositions = [],
    loading,
    syncing,
    error,
  } = useSelector((state) => state.positions);

  const accounts = useSelector((state) => state.accounts?.accounts || []);

  const symbolsByAccount = useSelector(
    (state) => state.symbols?.symbolsByAccount || {},
  );

  const [query, setQuery] = useState("");

  /*
   * Live broker positions.
   *
   * The hook owns the WebSocket lifecycle and receives
   * authenticated positions.snapshot messages.
   */
  const {
    positions: livePositions,
    status: liveStatus,
    error: liveError,
    lastUpdatedAt,
  } = usePositionWebSocket({
    getAccessToken,
    initialPositions: reduxPositions,
  });

  /*
   * Prefer live snapshots after the first snapshot arrives.
   * Before that, display the REST-loaded Redux positions.
   */
  const positions = livePositions;

  /*
   * Build a stable key so symbol mappings are not fetched
   * repeatedly on every render or every live price update.
   */
  const positionAccountKey = useMemo(
    () =>
      [
        ...new Set(
          positions.map((position) => position.account_id).filter(Boolean),
        ),
      ]
        .sort()
        .join("|"),
    [positions],
  );

  const positionAccountIds = useMemo(
    () => (positionAccountKey ? positionAccountKey.split("|") : []),
    [positionAccountKey],
  );

  /*
   * Initial REST loading.
   */
  useEffect(() => {
    dispatch(fetchPositions());
    dispatch(fetchAccounts());
  }, [dispatch]);

  /*
   * Load account-specific symbol mappings.
   */
  useEffect(() => {
    positionAccountIds.forEach((accountId) => {
      dispatch(fetchAccountSymbols(accountId));
    });
  }, [dispatch, positionAccountIds]);

  /*
   * Resolve account name.
   */
  const accountName = (id) => {
    const account = accounts.find((item) => String(item.id) === String(id));

    return (
      account?.account_name ||
      account?.account_number ||
      String(id || "-").slice(0, 8)
    );
  };

  /*
   * Resolve the broker symbol for a position.
   */
  const getAccountSymbol = (position) => {
    const accountSymbols = symbolsByAccount[String(position.account_id)] || [];

    return accountSymbols.find(
      (item) =>
        String(item.symbol_id) === String(position.symbol_id) ||
        String(item.symbol?.id) === String(position.symbol_id),
    );
  };

  /*
   * Filter visible positions.
   */
  const visiblePositions = useMemo(() => {
    const normalizedQuery = query.trim().toLowerCase();

    return positions.filter((position) => {
      const accountSymbols =
        symbolsByAccount[String(position.account_id)] || [];

      const accountSymbol = accountSymbols.find(
        (item) =>
          String(item.symbol_id) === String(position.symbol_id) ||
          String(item.symbol?.id) === String(position.symbol_id),
      );

      const symbol =
        accountSymbol?.symbol_name ||
        accountSymbol?.name ||
        accountSymbol?.symbol?.name ||
        accountSymbol?.broker_symbol ||
        String(position.symbol_id || "-").slice(0, 8);

      const brokerSymbol = accountSymbol?.broker_symbol || "";

      const searchableText = [
        position.strategy,
        symbol,
        brokerSymbol,
        position.ticket,
        position.direction,
        position.comment,
      ]
        .filter(Boolean)
        .join(" ")
        .toLowerCase();

      return !normalizedQuery || searchableText.includes(normalizedQuery);
    });
  }, [positions, query, symbolsByAccount]);

  /*
   * Manually synchronize broker state.
   */
  const handleSync = async () => {
    try {
      await dispatch(syncPositions()).unwrap();

      const latestPositions = await dispatch(fetchPositions()).unwrap();

      const accountIds = [
        ...new Set(
          (Array.isArray(latestPositions) ? latestPositions : [])
            .map((position) => position.account_id)
            .filter(Boolean),
        ),
      ];

      accountIds.forEach((accountId) => {
        dispatch(fetchAccountSymbols(accountId));
      });
    } catch {
      /*
       * Redux thunk errors are reflected by the existing
       * positions slice.
       */
    }
  };

  const connectionLabel =
    {
      connected: "CONNECTED",
      connecting: "CONNECTING",
      reconnecting: "RECONNECTING",
      disconnected: "DISCONNECTED",
    }[liveStatus] || "DISCONNECTED";

  return (
    <main className="positions-page">
      {/* HEADER */}
      <header className="positions-header">
        <div>
          <span className="positions-eyebrow">
            LIVE BROKER STATE · {connectionLabel}
            {lastUpdatedAt
              ? ` · ${new Date(lastUpdatedAt).toLocaleTimeString()}`
              : ""}
          </span>

          <h1>Positions</h1>

          <p>Monitor positions created and updated by the execution system.</p>
        </div>

        <button
          type="button"
          className="positions-refresh"
          onClick={handleSync}
          disabled={syncing}
        >
          <FaSyncAlt className={syncing ? "positions-spin" : ""} />

          {syncing ? "Syncing..." : "Sync broker"}
        </button>
      </header>

      {/* ERROR */}
      {(liveError || error) && (
        <div className="positions-error">
          {liveError ||
            (typeof error === "string"
              ? error
              : "Unable to load or synchronize broker positions.")}
        </div>
      )}

      {/* TOOLBAR */}
      <section className="positions-toolbar">
        <div className="positions-search">
          <FaSearch />

          <input
            type="search"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Search strategy, symbol or ticket..."
            aria-label="Search positions"
          />
        </div>

        <span>
          {visiblePositions.length} open position
          {visiblePositions.length === 1 ? "" : "s"}
        </span>
      </section>

      {/* POSITIONS TABLE */}
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
            {loading && positions.length === 0 && (
              <tr>
                <td colSpan={7} className="positions-empty">
                  <FaSyncAlt className="positions-spin" />
                  <strong>Loading positions...</strong>
                </td>
              </tr>
            )}

            {!loading && visiblePositions.length === 0 && (
              <tr>
                <td colSpan={7} className="positions-empty">
                  <FaExchangeAlt />

                  <strong>No broker positions</strong>

                  <span>
                    Positions will appear here after an order is filled or a
                    broker position is synchronized.
                  </span>
                </td>
              </tr>
            )}

            {visiblePositions.map((position) => {
              const accountSymbol = getAccountSymbol(position);

              const symbol =
                accountSymbol?.symbol_name ||
                accountSymbol?.name ||
                accountSymbol?.symbol?.name ||
                accountSymbol?.broker_symbol ||
                String(position.symbol_id || "-").slice(0, 8);

              const brokerSymbol = accountSymbol?.broker_symbol || "";

              const floatingProfit = Number(position.floating_profit ?? 0);

              return (
                <tr key={position.id || position.ticket}>
                  {/* POSITION */}
                  <td>
                    <strong>#{position.ticket || "—"}</strong>

                    <span>
                      {position.direction || "—"}
                      {" · "}
                      {position.strategy || "Manual"}
                    </span>
                  </td>

                  {/* INSTRUMENT */}
                  <td>
                    <strong>{symbol}</strong>

                    <span>
                      {brokerSymbol || position.comment || "Broker position"}
                    </span>
                  </td>

                  {/* ACCOUNT */}
                  <td>{accountName(position.account_id)}</td>

                  {/* VOLUME */}
                  <td>{position.current_volume ?? position.volume ?? "—"}</td>

                  {/* ENTRY / CURRENT */}
                  <td>
                    {position.entry_price ?? "—"}
                    {" / "}
                    {position.current_price ?? "—"}
                  </td>

                  {/* FLOATING P/L */}
                  <td className={floatingProfit >= 0 ? "positive" : "negative"}>
                    {position.floating_profit ?? "0"}
                  </td>

                  {/* STOPS */}
                  <td>
                    SL {position.stop_loss ?? "-"}
                    <br />
                    TP {position.take_profit ?? "-"}
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
