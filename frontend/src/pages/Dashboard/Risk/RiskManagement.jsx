import { useEffect, useState } from "react";
import { useDispatch, useSelector } from "react-redux";
import { FaShieldAlt, FaSave } from "react-icons/fa";

import { fetchAccounts } from "../../../redux/dashboard/accounts/accountsThunks";
import { fetchRiskProfile, updateRiskProfile } from "../../../redux/dashboard/riskThunks";
import "../../../css/risk.css";

const fields = [
  ["min_risk_percent", "Minimum risk per trade (%)"],
  ["base_risk_percent", "Base risk per trade (%)"],
  ["max_risk_percent", "Maximum risk per trade (%)"],
  ["risk_multiplier", "Risk multiplier"],
  ["max_daily_loss_percent", "Maximum daily loss (%)"],
  ["max_drawdown_percent", "Maximum drawdown (%)"],
  ["max_open_risk_percent", "Maximum open risk (%)"],
  ["max_open_positions", "Maximum open positions"],
  ["max_symbol_exposure_percent", "Maximum symbol exposure (%)"],
  ["max_strategy_exposure_percent", "Maximum strategy exposure (%)"],
];

const RiskManagement = () => {
  const dispatch = useDispatch();
  const { accounts } = useSelector((state) => state.accounts);
  const { profile, loading, saving, saved, error } = useSelector((state) => state.risk);
  const [accountId, setAccountId] = useState("");
  const [form, setForm] = useState({});

  useEffect(() => { dispatch(fetchAccounts()); }, [dispatch]);
  useEffect(() => {
    if (!accountId && accounts.length) setAccountId(accounts[0].id);
  }, [accounts, accountId]);
  useEffect(() => {
    if (accountId) dispatch(fetchRiskProfile(accountId));
  }, [dispatch, accountId]);
  useEffect(() => {
    if (profile) setForm(Object.fromEntries(fields.map(([key]) => [key, profile[key] ?? ""])));
  }, [profile]);

  const updateField = (key, value) => setForm((current) => ({ ...current, [key]: value }));
  const submit = (event) => {
    event.preventDefault();
    const data = Object.fromEntries(Object.entries(form).filter(([, value]) => value !== "").map(([key, value]) => [key, key === "enabled" ? Boolean(value) : Number(value)]));
    dispatch(updateRiskProfile({ accountId, data }));
  };

  return <main className="risk-page">
    <header className="risk-page__header"><div><span className="dashboard-eyebrow">RISK ENGINE</span><h1>Risk Management</h1><p>Adjust limits applied before every automated trade.</p></div><FaShieldAlt /></header>
    <div className="risk-page__toolbar"><label>Trading account<select value={accountId} onChange={(event) => setAccountId(event.target.value)}><option value="">Select account</option>{accounts.map((account) => <option key={account.id} value={account.id}>{account.account_name || account.account_number}</option>)}</select></label>{profile && <span className={profile.enabled ? "risk-enabled" : "risk-disabled"}>{profile.enabled ? "Risk checks enabled" : "Risk checks disabled"}</span>}</div>
    {error && <div className="dashboard-error">{error}</div>}
    {loading && <div className="risk-empty">Loading risk profile...</div>}
    {!loading && accountId && profile && <form className="risk-form" onSubmit={submit}><label className="risk-toggle"><input type="checkbox" checked={Boolean(form.enabled ?? profile.enabled)} onChange={(event) => updateField("enabled", event.target.checked)} /> Enable risk checks</label><div className="risk-form__grid">{fields.map(([key, label]) => <label key={key}>{label}<input type="number" min="0.01" step="0.01" value={form[key] ?? ""} onChange={(event) => updateField(key, event.target.value)} /></label>)}</div><div className="risk-form__footer"><span>{saved ? "Risk profile saved" : "Changes apply to future trades."}</span><button type="submit" disabled={saving}><FaSave /> {saving ? "Saving..." : "Save risk settings"}</button></div></form>}
    {!loading && !profile && accountId && <div className="risk-empty">No risk profile exists for this account.</div>}
  </main>;
};

export default RiskManagement;