import { useEffect } from "react";
import { FaRobot, FaSyncAlt } from "react-icons/fa";
import { useDispatch, useSelector } from "react-redux";

import { fetchStrategyRuns } from "../../../redux/dashboard/dashboardThunks";
import "../../../css/strategyRuns.css";

const StrategyRuns = () => {
  const dispatch = useDispatch();
  const { strategyRuns, loading, error } = useSelector((state) => state.dashboard);
  useEffect(() => { dispatch(fetchStrategyRuns()); }, [dispatch]);
  return <main className="strategy-runs-page"><header className="strategy-runs-header"><div><span className="dashboard-eyebrow">AUTOMATION MONITOR</span><h1>Strategy Runs</h1><p>See which strategies are active and review their trading run history.</p></div><button onClick={() => dispatch(fetchStrategyRuns())} disabled={loading}><FaSyncAlt className={loading ? "strategy-spin" : ""} /> Refresh</button></header>{error && <div className="dashboard-error">{error}</div>}<section className="strategy-runs-table-wrap"><table><thead><tr><th>Strategy</th><th>Type</th><th>Status</th><th>Symbols</th><th>Timeframe</th><th>Trades</th><th>Started</th><th>Ended</th></tr></thead><tbody>{loading && <tr><td colSpan="8" className="strategy-empty">Loading strategy runs...</td></tr>}{!loading && strategyRuns.length === 0 && <tr><td colSpan="8" className="strategy-empty"><FaRobot /><strong>No strategy runs</strong><span>Start a bot from the dashboard to see it here.</span></td></tr>}{!loading && strategyRuns.map((run) => <tr key={run.id}><td><strong>{run.strategy_name}</strong><span>{run.run_name}</span></td><td>{run.run_type}</td><td><span className={`strategy-status strategy-status--${String(run.status).toLowerCase()}`}>{run.status}</span></td><td>{(run.symbols || []).join(", ") || "-"}</td><td>{run.timeframe}</td><td>{run.total_trades}</td><td>{run.started_at ? new Date(run.started_at).toLocaleString() : "-"}</td><td>{run.ended_at ? new Date(run.ended_at).toLocaleString() : "-"}</td></tr>)}</tbody></table></section></main>;
};

export default StrategyRuns;