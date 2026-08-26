import { useEffect, useMemo, useState } from "react";
import { useDispatch, useSelector } from "react-redux";
import { FaCheckCircle, FaCoins, FaEdit, FaPlus, FaSearch, FaSyncAlt, FaTrash } from "react-icons/fa";
import SymbolForm from "./SymbolForm";
import { createSymbol, fetchSymbols, removeSymbol, updateSymbol } from "../../../redux/dashboard/symbols/symbolsThunks";
import { clearSymbolsError } from "../../../redux/dashboard/symbols/symbolsSlice";
import "../../../css/symbols.css";

const SymbolsPage = () => {
  const dispatch = useDispatch();
  const { symbols, loading, saving, deleting, error } = useSelector((state) => state.symbols);
  const [searchTerm, setSearchTerm] = useState("");
  const [assetFilter, setAssetFilter] = useState("ALL");
  const [modalOpen, setModalOpen] = useState(false);
  const [editingSymbol, setEditingSymbol] = useState(null);

  useEffect(() => { dispatch(fetchSymbols()); }, [dispatch]);

  const assetClasses = useMemo(
    () => [...new Set(symbols.map((symbol) => symbol.asset_class).filter(Boolean))].sort(),
    [symbols],
  );

  const filteredSymbols = useMemo(() => symbols.filter((symbol) => {
    const query = searchTerm.trim().toLowerCase();
    const matchesSearch = !query || [symbol.name, symbol.broker_symbol, symbol.description]
      .some((value) => String(value || "").toLowerCase().includes(query));
    return matchesSearch && (assetFilter === "ALL" || symbol.asset_class === assetFilter);
  }), [symbols, searchTerm, assetFilter]);

  const openCreate = () => { setEditingSymbol(null); setModalOpen(true); };
  const openEdit = (symbol) => { setEditingSymbol(symbol); setModalOpen(true); };
  const handleSubmit = async (symbolData) => {
    const result = editingSymbol
      ? await dispatch(updateSymbol({ symbolId: editingSymbol.id, symbolData }))
      : await dispatch(createSymbol(symbolData));
    if (createSymbol.fulfilled.match(result) || updateSymbol.fulfilled.match(result)) setModalOpen(false);
  };
  const handleDelete = async (symbol) => {
    if (window.confirm(`Delete ${symbol.name}? This cannot be undone.`)) await dispatch(removeSymbol(symbol.id));
  };

  return (
    <main className="symbols-page">
      <section className="symbols-header">
        <div><span className="symbols-eyebrow">TRADING INSTRUMENTS</span><h1>Symbols</h1><p>Manage the market instruments available to your trading strategies.</p></div>
        <button className="symbol-button symbol-button--primary" onClick={openCreate} disabled={saving}><FaPlus /> Add Symbol</button>
      </section>
      {error && <div className="symbols-error"><span>{typeof error === "string" ? error : "Unable to process symbol request."}</span><button onClick={() => dispatch(clearSymbolsError())} aria-label="Dismiss error">x</button></div>}
      <section className="symbols-stats">
        <div className="symbol-stat"><FaCoins /><div><span>Total Symbols</span><strong>{symbols.length}</strong></div></div>
        <div className="symbol-stat"><FaCheckCircle /><div><span>Active Symbols</span><strong>{symbols.filter((symbol) => symbol.active).length}</strong></div></div>
        <div className="symbol-stat"><FaCoins /><div><span>Asset Classes</span><strong>{assetClasses.length}</strong></div></div>
      </section>
      <section className="symbols-toolbar">
        <div className="symbols-search"><FaSearch /><input value={searchTerm} onChange={(event) => setSearchTerm(event.target.value)} placeholder="Search symbols..." /></div>
        <div className="symbols-filters"><select value={assetFilter} onChange={(event) => setAssetFilter(event.target.value)}><option value="ALL">All asset classes</option>{assetClasses.map((assetClass) => <option key={assetClass}>{assetClass}</option>)}</select><button className="symbols-refresh" onClick={() => dispatch(fetchSymbols())} disabled={loading} title="Refresh symbols"><FaSyncAlt className={loading ? "symbols-spin" : ""} /></button></div>
      </section>
      <section className="symbols-card">
        <header className="symbols-card__header"><div><span>INSTRUMENT REGISTRY</span><h2>Market Symbols</h2></div><span className="symbols-count">{filteredSymbols.length} {filteredSymbols.length === 1 ? "symbol" : "symbols"}</span></header>
        <div className="symbols-table-wrapper">
          <table className="symbols-table"><thead><tr><th>Symbol</th><th>Asset Class</th><th>Precision</th><th>Contract</th><th>Volume Range</th><th>Status</th><th>Actions</th></tr></thead>
            <tbody>
              {loading && <tr><td colSpan="7" className="symbols-empty"><FaSyncAlt className="symbols-spin" /><strong>Loading symbols...</strong></td></tr>}
              {!loading && filteredSymbols.length === 0 && <tr><td colSpan="7" className="symbols-empty"><FaCoins /><strong>{symbols.length ? "No matching symbols" : "No symbols configured"}</strong><span>{symbols.length ? "Try changing your search or filter." : "Add your first market instrument to get started."}</span><button className="symbol-button symbol-button--primary" onClick={openCreate}><FaPlus /> Add Symbol</button></td></tr>}
              {!loading && filteredSymbols.map((symbol) => <tr key={symbol.id}><td><div className="symbol-name"><div className="symbol-icon"><FaCoins /></div><div><strong>{symbol.name}</strong><span>{symbol.broker_symbol || "No broker mapping"}</span></div></div></td><td><span className="symbol-asset">{symbol.asset_class || "OTHER"}</span></td><td><strong>{symbol.digits ?? "-"}</strong><span className="symbol-subvalue">digits</span></td><td>{symbol.contract_size ?? "-"}</td><td>{symbol.min_volume ?? "-"} - {symbol.max_volume ?? "-"}<span className="symbol-subvalue">step {symbol.volume_step ?? "-"}</span></td><td><span className={symbol.active ? "symbol-status active" : "symbol-status"}><span />{symbol.active ? "Active" : "Inactive"}</span></td><td><div className="symbol-actions"><button title="Edit symbol" onClick={() => openEdit(symbol)}><FaEdit /></button><button title="Delete symbol" onClick={() => handleDelete(symbol)} disabled={deleting}><FaTrash /></button></div></td></tr>)}
            </tbody>
          </table>
        </div>
      </section>
      <SymbolForm isOpen={modalOpen} onClose={() => !saving && setModalOpen(false)} onSubmit={handleSubmit} symbol={editingSymbol} loading={saving} />
    </main>
  );
};

export default SymbolsPage;
