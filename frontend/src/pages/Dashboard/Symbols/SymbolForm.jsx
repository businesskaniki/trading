import { useEffect, useState } from "react";
import { FaTimes, FaCoins } from "react-icons/fa";
import "../../../css/symbols.css";

const initialForm = {
  name: "",
  description: "",
  broker_symbol: "",
  asset_class: "FOREX",
  digits: 5,
  tick_size: 0,
  contract_size: 100000,
  min_volume: 0.01,
  max_volume: 100,
  volume_step: 0.01,
  active: true,
};

const numericFields = ["digits", "tick_size", "contract_size", "min_volume", "max_volume", "volume_step"];

const SymbolForm = ({ isOpen, onClose, onSubmit, symbol, loading }) => {
  const [formData, setFormData] = useState(initialForm);
  const [error, setError] = useState("");

  useEffect(() => {
    if (isOpen) {
      setFormData(symbol ? { ...initialForm, ...symbol } : initialForm);
      setError("");
    }
  }, [isOpen, symbol]);

  if (!isOpen) return null;

  const handleChange = (event) => {
    const { name, value, type, checked } = event.target;
    setFormData((previous) => ({ ...previous, [name]: type === "checkbox" ? checked : value }));
  };

  const handleSubmit = (event) => {
    event.preventDefault();
    if (!formData.name.trim() || !formData.broker_symbol.trim()) {
      setError("Name and broker symbol are required.");
      return;
    }
    const payload = Object.fromEntries(Object.entries(formData).map(([key, value]) => [
      key, numericFields.includes(key) ? Number(value) : value,
    ]));
    onSubmit(payload);
  };

  return (
    <div className="symbol-modal-overlay" onMouseDown={(event) => event.target === event.currentTarget && !loading && onClose()}>
      <div className="symbol-modal">
        <header className="symbol-modal__header">
          <div><span className="symbols-eyebrow">MARKET INSTRUMENT</span><h2>{symbol ? "Edit Symbol" : "Create Symbol"}</h2><p>Configure the instrument used by your trading infrastructure.</p></div>
          <button type="button" className="symbol-modal__close" onClick={onClose} disabled={loading} aria-label="Close"><FaTimes /></button>
        </header>
        {error && <div className="symbol-form-error">{error}</div>}
        <form className="symbol-form" onSubmit={handleSubmit}>
          <div className="symbol-form__grid">
            <label>Name<input name="name" value={formData.name} onChange={handleChange} placeholder="BTCUSD" /></label>
            <label>Broker Symbol<input name="broker_symbol" value={formData.broker_symbol} onChange={handleChange} placeholder="BTCUSD" /></label>
            <label>Asset Class<select name="asset_class" value={formData.asset_class} onChange={handleChange}><option>FOREX</option><option>CRYPTO</option><option>STOCK</option><option>INDEX</option><option>COMMODITY</option><option>FUTURES</option></select></label>
            <label>Digits<input type="number" name="digits" min="0" value={formData.digits} onChange={handleChange} /></label>
            <label className="symbol-form__wide">Description<textarea name="description" value={formData.description} onChange={handleChange} placeholder="Optional instrument description" rows="2" /></label>
            <label>Tick Size<input type="number" step="any" name="tick_size" value={formData.tick_size} onChange={handleChange} /></label>
            <label>Contract Size<input type="number" step="any" name="contract_size" value={formData.contract_size} onChange={handleChange} /></label>
            <label>Min Volume<input type="number" step="any" name="min_volume" value={formData.min_volume} onChange={handleChange} /></label>
            <label>Max Volume<input type="number" step="any" name="max_volume" value={formData.max_volume} onChange={handleChange} /></label>
            <label>Volume Step<input type="number" step="any" name="volume_step" value={formData.volume_step} onChange={handleChange} /></label>
            <label className="symbol-checkbox"><input type="checkbox" name="active" checked={formData.active} onChange={handleChange} /> Active symbol</label>
          </div>
          <footer className="symbol-form__footer"><button type="button" className="symbol-button symbol-button--muted" onClick={onClose} disabled={loading}>Cancel</button><button type="submit" className="symbol-button symbol-button--primary" disabled={loading}><FaCoins />{loading ? "Saving..." : symbol ? "Save Changes" : "Create Symbol"}</button></footer>
        </form>
      </div>
    </div>
  );
};

export default SymbolForm;
