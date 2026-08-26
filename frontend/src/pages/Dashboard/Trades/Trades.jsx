import { useEffect, useMemo, useState } from "react";
import { FaHistory, FaSearch, FaSyncAlt } from "react-icons/fa";
import { useDispatch, useSelector } from "react-redux";
import { fetchTrades } from "../../../redux/dashboard/trades/tradesThunks";
import "../../../css/trades.css";

const Trades = () => {
  const dispatch = useDispatch();
  const { trades, loading, error } = useSelector((state) => state.trades);
  const [query, setQuery] = useState("");
  useEffect(() => { dispatch(fetchTrades()); }, [dispatch]);
  const visibleTrades = useMemo(() => trades.filter((trade) => `${trade.strategy} ${trade.ticket} ${trade.result}`.toLowerCase().includes(query.toLowerCase())), [trades, query]);
  return <main className="trades-page"><header className="trades-header"><div><span className="trades-eyebrow">EXECUTION HISTORY</span><h1>Trades</h1><p>Review completed trades generated from closed positions.</p></div><button className="trades-refresh" onClick={() => dispatch(fetchTrades())} disabled={loading}><FaSyncAlt className={loading ? "trades-spin" : ""} /> Refresh</button></header>{error && <div className="trades-error">{error}</div>}<section className="trades-toolbar"><div className="trades-search"><FaSearch /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search strategy, ticket or result..." /></div><span>{visibleTrades.length} completed trade{visibleTrades.length === 1 ? "" : "s"}</span></section><section className="trades-table-wrap"><table className="trades-table"><thead><tr><th>Trade</th><th>Direction</th><th>Volume</th><th>Entry / Exit</th><th>Net P/L</th><th>Result</th><th>Closed</th></tr></thead><tbody>{loading && <tr><td colSpan="7" className="trades-empty">Loading trade history...</td></tr>}{!loading && visibleTrades.length === 0 && <tr><td colSpan="7" className="trades-empty"><FaHistory /><strong>No completed trades</strong><span>Closed positions will appear here automatically.</span></td></tr>}{!loading && visibleTrades.map((trade) => <tr key={trade.id}><td><strong>#{trade.ticket}</strong><span>{trade.strategy}</span></td><td>{trade.direction}</td><td>{trade.volume}</td><td>{trade.entry_price} / {trade.exit_price}</td><td className={Number(trade.net_profit) >= 0 ? "positive" : "negative"}>{trade.net_profit}</td><td>{trade.result}</td><td>{trade.closed_at ? new Date(trade.closed_at).toLocaleDateString() : "-"}</td></tr>)}</tbody></table></section></main>;
};

export default Trades;