import { useEffect, useMemo, useState } from "react";
import { FaHistory, FaSearch, FaSyncAlt } from "react-icons/fa";
import { useDispatch, useSelector } from "react-redux";
import { fetchTrades } from "../../../redux/dashboard/trades/tradesThunks";
import "../../../css/trades.css";

const Trades = () => {
  const dispatch = useDispatch();

  const { trades = [], loading, error } = useSelector((state) => state.trades);

  const selectedAccountId = useSelector(
    (state) => state.accounts.selectedAccount?.id ?? null,
  );

  const [query, setQuery] = useState("");

  // Fetch trades for the selected account only.
  useEffect(() => {
    if (!selectedAccountId) {
      return;
    }

    dispatch(fetchTrades(selectedAccountId));
  }, [dispatch, selectedAccountId]);

  const visibleTrades = useMemo(() => {
    if (!selectedAccountId) {
      return [];
    }

    const search = query.trim().toLowerCase();

    return trades.filter((trade) => {
      // Prevent stale records from another account appearing.
      if (
        trade.account_id != null &&
        String(trade.account_id) !== String(selectedAccountId)
      ) {
        return false;
      }

      return `${trade.strategy ?? ""} ${trade.ticket ?? ""} ${
        trade.result ?? ""
      }`
        .toLowerCase()
        .includes(search);
    });
  }, [trades, query, selectedAccountId]);

  const handleRefresh = () => {
    if (!selectedAccountId || loading) {
      return;
    }

    dispatch(fetchTrades(selectedAccountId));
  };

  return (
    <main className="trades-page">
      <header className="trades-header">
        <div>
          <span className="trades-eyebrow">EXECUTION HISTORY</span>
          <h1>Trades</h1>
          <p>Review completed trades generated from closed positions.</p>
        </div>

        <button
          type="button"
          className="trades-refresh"
          onClick={handleRefresh}
          disabled={!selectedAccountId || loading}
        >
          <FaSyncAlt className={loading ? "trades-spin" : ""} />
          Refresh
        </button>
      </header>

      {error && selectedAccountId && (
        <div className="trades-error">{error}</div>
      )}

      <section className="trades-toolbar">
        <div className="trades-search">
          <FaSearch />
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Search strategy, ticket or result..."
            disabled={!selectedAccountId}
          />
        </div>

        <span>
          {visibleTrades.length} completed trade
          {visibleTrades.length === 1 ? "" : "s"}
        </span>
      </section>

      <section className="trades-table-wrap">
        <table className="trades-table">
          <thead>
            <tr>
              <th>Trade</th>
              <th>Direction</th>
              <th>Volume</th>
              <th>Entry / Exit</th>
              <th>Net P/L</th>
              <th>Result</th>
              <th>Closed</th>
            </tr>
          </thead>

          <tbody>
            {!selectedAccountId && (
              <tr>
                <td colSpan={7} className="trades-empty">
                  <FaHistory />
                  <strong>Select a trading account first</strong>
                  <span>
                    Choose an account to view its completed trade history.
                  </span>
                </td>
              </tr>
            )}

            {selectedAccountId && loading && (
              <tr>
                <td colSpan={7} className="trades-empty">
                  Loading trade history...
                </td>
              </tr>
            )}

            {selectedAccountId &&
              !loading &&
              !error &&
              visibleTrades.length === 0 && (
                <tr>
                  <td colSpan={7} className="trades-empty">
                    <FaHistory />
                    <strong>No completed trades</strong>
                    <span>
                      Closed positions for this account will appear here.
                    </span>
                  </td>
                </tr>
              )}

            {selectedAccountId &&
              !loading &&
              visibleTrades.map((trade) => (
                <tr key={trade.id}>
                  <td>
                    <strong>#{trade.ticket}</strong>
                    <span>{trade.strategy}</span>
                  </td>

                  <td>{trade.direction}</td>
                  <td>{trade.volume}</td>

                  <td>
                    {trade.entry_price} / {trade.exit_price}
                  </td>

                  <td
                    className={
                      Number(trade.net_profit) >= 0 ? "positive" : "negative"
                    }
                  >
                    {trade.net_profit}
                  </td>

                  <td>{trade.result}</td>

                  <td>
                    {trade.closed_at
                      ? new Date(trade.closed_at).toLocaleDateString()
                      : "-"}
                  </td>
                </tr>
              ))}
          </tbody>
        </table>
      </section>
    </main>
  );
};

export default Trades;
