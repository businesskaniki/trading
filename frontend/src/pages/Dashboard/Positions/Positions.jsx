import { useEffect, useMemo, useState } from "react";
import { FaExchangeAlt, FaSearch, FaSyncAlt } from "react-icons/fa";
import { useDispatch, useSelector } from "react-redux";
import { fetchPositions, syncPositions } from "../../../redux/dashboard/positions/positionsThunks";
import { fetchAccounts } from "../../../redux/dashboard/accounts/accountsThunks";
import { fetchSymbols } from "../../../redux/dashboard/symbols/symbolsThunks";
import "../../../css/positions.css";

const Positions = () => {
  const dispatch = useDispatch();
  const { positions, loading, syncing, error } = useSelector((state) => state.positions);
  const accounts = useSelector((state) => state.accounts.accounts);
  const symbols = useSelector((state) => state.symbols.symbols);
  const [query, setQuery] = useState("");

  useEffect(() => {
    dispatch(fetchPositions());
    dispatch(fetchAccounts());
    dispatch(fetchSymbols());
  }, [dispatch]);

  const accountName = (id) => accounts.find((item) => item.id === id)?.account_name || String(id || "-").slice(0, 8);
  const symbolName = (id) => symbols.find((item) => item.id === id)?.name || String(id || "-").slice(0, 8);
  const visiblePositions = useMemo(() => positions.filter((position) => {
    const symbol = symbols.find((item) => item.id === position.symbol_id)?.name || String(position.symbol_id || "-").slice(0, 8);
    const text = `${position.strategy} ${symbol} ${position.ticket}`.toLowerCase();
    return !query || text.includes(query.toLowerCase());
  }), [positions, query, symbols]);

  return (
    <main className="positions-page">
      <header className="positions-header">
        <div><span className="positions-eyebrow">LIVE BROKER STATE</span><h1>Positions</h1><p>Monitor positions created and updated by the execution system.</p></div>
        <button className="positions-refresh" onClick={() => dispatch(syncPositions())} disabled={syncing}><FaSyncAlt className={syncing ? "positions-spin" : ""} /> {syncing ? "Syncing..." : "Sync broker"}</button>
      </header>
      {error && <div className="positions-error">{error}</div>}
      <section className="positions-toolbar"><div className="positions-search"><FaSearch /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search strategy, symbol or ticket..." /></div><span>{visiblePositions.length} open position{visiblePositions.length === 1 ? "" : "s"}</span></section>
      <section className="positions-table-wrap"><table className="positions-table"><thead><tr><th>Position</th><th>Instrument</th><th>Account</th><th>Volume</th><th>Entry / Current</th><th>P/L</th><th>Stops</th></tr></thead><tbody>
        {loading && <tr><td colSpan="7" className="positions-empty">Loading positions...</td></tr>}
        {!loading && visiblePositions.length === 0 && <tr><td colSpan="7" className="positions-empty"><FaExchangeAlt /><strong>No broker positions</strong><span>Positions will appear here after an order is filled.</span></td></tr>}
        {!loading && visiblePositions.map((position) => <tr key={position.id}><td><strong>#{position.ticket}</strong><span>{position.direction} · {position.strategy}</span></td><td><strong>{symbolName(position.symbol_id)}</strong><span>{position.comment || "Broker position"}</span></td><td>{accountName(position.account_id)}</td><td>{position.current_volume || position.volume}</td><td>{position.entry_price} / {position.current_price}</td><td className={Number(position.floating_profit) >= 0 ? "positive" : "negative"}>{position.floating_profit}</td><td>SL {position.stop_loss || "-"}<br />TP {position.take_profit || "-"}</td></tr>)}
      </tbody></table></section>
    </main>
  );
};

export default Positions;