import { useEffect, useState } from "react";
import { FaChartLine, FaSyncAlt } from "react-icons/fa";
import { useDispatch, useSelector } from "react-redux";

import { fetchAccounts } from "../../../redux/dashboard/accounts/accountsThunks";
import dashboardAPI from "../../../redux/dashboard/dashboardAPI";
import "../../../css/analytics.css";

const money = (value) => new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" }).format(Number(value || 0));

const Analytics = () => {
  const dispatch = useDispatch();
  const { accounts } = useSelector((state) => state.accounts);
  const [accountId, setAccountId] = useState("");
  const [summary, setSummary] = useState(null);
  const [strategies, setStrategies] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [reload, setReload] = useState(0);

  useEffect(() => { dispatch(fetchAccounts()); }, [dispatch]);
  useEffect(() => { if (!accountId && accounts.length) setAccountId(accounts[0].id); }, [accounts, accountId]);
  useEffect(() => {
    if (!accountId) return;
    let cancelled = false;
    setLoading(true);
    setError(null);
    Promise.all([dashboardAPI.getAccountSummary(accountId), dashboardAPI.getStrategyPerformance(accountId)])
      .then(([nextSummary, nextStrategies]) => { if (!cancelled) { setSummary(nextSummary); setStrategies(nextStrategies); } })
      .catch((requestError) => { if (!cancelled) setError(requestError.response?.data?.detail || requestError.message || "Unable to load analytics."); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [accountId, reload]);

  return <main className="analytics-page">
    <header className="analytics-header"><div><span className="dashboard-eyebrow">PERFORMANCE INTELLIGENCE</span><h1>Analytics</h1><p>Review realized performance and strategy quality for a trading account.</p></div><FaChartLine /></header>
    <section className="analytics-toolbar"><label>Trading account<select value={accountId} onChange={(event) => setAccountId(event.target.value)}><option value="">Select account</option>{accounts.map((account) => <option key={account.id} value={account.id}>{account.account_name || account.account_number}</option>)}</select></label><button onClick={() => setReload((current) => current + 1)} disabled={loading}><FaSyncAlt className={loading ? "analytics-spin" : ""} /> Refresh</button></section>
    {error && <div className="dashboard-error">{error}</div>}
    {loading && <div className="analytics-empty">Loading analytics...</div>}
    {!loading && summary && <><section className="analytics-metrics">{[["Net profit", money(summary.net_profit), Number(summary.net_profit) >= 0], ["Win rate", `${Number(summary.win_rate || 0).toFixed(2)}%`, true], ["Profit factor", summary.profit_factor ?? "-", true], ["Total trades", summary.total_trades, true], ["Gross profit", money(summary.gross_profit), true], ["Gross loss", money(summary.gross_loss), false]].map(([label, value, positive]) => <div className="analytics-metric" key={label}><span>{label}</span><strong className={positive ? "positive" : "negative"}>{value}</strong></div>)}</section><section className="analytics-panel"><div className="analytics-panel__header"><div><span>STRATEGY PERFORMANCE</span><h2>Strategy comparison</h2></div><span>{strategies.length} strateg{strategies.length === 1 ? "y" : "ies"}</span></div>{strategies.length === 0 ? <div className="analytics-empty">No completed strategy performance yet.</div> : <div className="analytics-table-wrap"><table><thead><tr><th>Strategy</th><th>Trades</th><th>Win rate</th><th>Net profit</th><th>Profit factor</th><th>Expectancy</th></tr></thead><tbody>{strategies.map((strategy) => <tr key={strategy.strategy}><td><strong>{strategy.strategy}</strong></td><td>{strategy.total_trades}</td><td>{Number(strategy.win_rate || 0).toFixed(2)}%</td><td className={Number(strategy.net_profit) >= 0 ? "positive" : "negative"}>{money(strategy.net_profit)}</td><td>{strategy.profit_factor ?? "-"}</td><td>{money(strategy.expectancy)}</td></tr>)}</tbody></table></div>}</section></>}
    {!loading && !summary && accountId && <div className="analytics-empty">No analytics available for this account.</div>}
  </main>;
};

export default Analytics;