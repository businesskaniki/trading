import { useEffect, useMemo, useState } from "react";
import { useDispatch, useSelector } from "react-redux";
import { FaArrowDown, FaArrowUp, FaClipboardList, FaEdit, FaPlay, FaPlus, FaSearch, FaSyncAlt, FaTrash } from "react-icons/fa";
import OrderForm from "./OrderForm";
import { fetchAccounts } from "../../../redux/dashboard/accounts/accountsThunks";
import { fetchSymbols } from "../../../redux/dashboard/symbols/symbolsThunks";
import { clearOrdersError } from "../../../redux/dashboard/orders/ordersSlice";
import { createOrder, executeOrder, fetchOrders, removeOrder, updateOrder, updateOrderStatus } from "../../../redux/dashboard/orders/ordersThunks";
import "../../../css/orders.css";

const terminalStatuses = ["FILLED", "CANCELLED", "REJECTED", "EXPIRED"];

const Orders = () => {
  const dispatch = useDispatch();
  const { orders, loading, saving, acting, error } = useSelector((state) => state.orders);
  const accounts = useSelector((state) => state.accounts.accounts);
  const symbols = useSelector((state) => state.symbols.symbols);
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState("ALL");
  const [modalOpen, setModalOpen] = useState(false);
  const [editingOrder, setEditingOrder] = useState(null);

  useEffect(() => {
    dispatch(fetchOrders());
    dispatch(fetchAccounts());
    dispatch(fetchSymbols());
  }, [dispatch]);

  const accountName = (id) => {
    const account = accounts.find((item) => item.id === id);
    return account?.account_name || account?.account_number || String(id || "-").slice(0, 8);
  };
  const symbolName = (id) => symbols.find((item) => item.id === id)?.name || String(id || "-").slice(0, 8);
  const statuses = useMemo(() => [...new Set(orders.map((order) => order.status).filter(Boolean))].sort(), [orders]);
  const filteredOrders = useMemo(() => orders.filter((order) => {
    const symbol = symbols.find((item) => item.id === order.symbol_id);
    const text = `${order.strategy} ${order.comment || ""} ${symbol?.name || ""} ${order.ticket || ""}`.toLowerCase();
    return (!query || text.includes(query.toLowerCase())) && (status === "ALL" || order.status === status);
  }), [orders, query, status, symbols]);

  const handleSubmit = async (data) => {
    const result = editingOrder
      ? await dispatch(updateOrder({ orderId: editingOrder.id, orderData: Object.fromEntries(Object.entries(data).filter(([key]) => !["account_id", "symbol_id"].includes(key))) }))
      : await dispatch(createOrder(data));
    if (createOrder.fulfilled.match(result) || updateOrder.fulfilled.match(result)) setModalOpen(false);
  };
  const handleDelete = async (order) => { if (window.confirm(`Delete order ${order.ticket || order.id.slice(0, 8)}?`)) await dispatch(removeOrder(order.id)); };
  const handleExecute = async (order) => { if (window.confirm(`Execute ${order.side} ${order.volume} ${symbolName(order.symbol_id)} now?`)) await dispatch(executeOrder(order.id)); };
  const handleCancel = async (order) => { if (window.confirm("Cancel this order?")) await dispatch(updateOrderStatus({ orderId: order.id, statusValue: "CANCELLED" })); };

  return (
    <main className="orders-page">
      <section className="orders-header"><div><span className="orders-eyebrow">EXECUTION PIPELINE</span><h1>Orders</h1><p>Create, monitor and execute trading instructions across your accounts.</p></div><button className="order-button order-button--primary" onClick={() => { setEditingOrder(null); setModalOpen(true); }} disabled={saving}><FaPlus /> Create Order</button></section>
      {error && <div className="orders-error"><span>{typeof error === "string" ? error : "Unable to process order request."}</span><button onClick={() => dispatch(clearOrdersError())} aria-label="Dismiss error">x</button></div>}
      <section className="orders-stats"><div className="order-stat"><FaClipboardList /><div><span>Total Orders</span><strong>{orders.length}</strong></div></div><div className="order-stat"><FaPlay /><div><span>Pending Work</span><strong>{orders.filter((order) => ["CREATED", "SUBMITTED", "PENDING"].includes(order.status)).length}</strong></div></div><div className="order-stat"><FaArrowUp /><div><span>Filled Orders</span><strong>{orders.filter((order) => order.status === "FILLED").length}</strong></div></div><div className="order-stat"><FaArrowDown /><div><span>Sell Orders</span><strong>{orders.filter((order) => order.side === "SELL").length}</strong></div></div></section>
      <section className="orders-toolbar"><div className="orders-search"><FaSearch /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search strategy, symbol or ticket..." /></div><div className="orders-filters"><select value={status} onChange={(event) => setStatus(event.target.value)}><option value="ALL">All statuses</option>{statuses.map((item) => <option key={item}>{item}</option>)}</select><button className="orders-refresh" onClick={() => dispatch(fetchOrders())} disabled={loading} title="Refresh orders"><FaSyncAlt className={loading ? "orders-spin" : ""} /></button></div></section>
      <section className="orders-card"><header className="orders-card__header"><div><span>ORDER REGISTRY</span><h2>Trading Orders</h2></div><span className="orders-count">{filteredOrders.length} {filteredOrders.length === 1 ? "order" : "orders"}</span></header><div className="orders-table-wrapper"><table className="orders-table"><thead><tr><th>Order</th><th>Instrument</th><th>Account</th><th>Volume / Price</th><th>Status</th><th>Created</th><th>Actions</th></tr></thead><tbody>
        {loading && <tr><td colSpan="7" className="orders-empty"><FaSyncAlt className="orders-spin" /><strong>Loading orders...</strong></td></tr>}
        {!loading && filteredOrders.length === 0 && <tr><td colSpan="7" className="orders-empty"><FaClipboardList /><strong>{orders.length ? "No matching orders" : "No orders configured"}</strong><span>{orders.length ? "Try changing your search or filter." : "Create your first trading instruction to get started."}</span><button className="order-button order-button--primary" onClick={() => { setEditingOrder(null); setModalOpen(true); }}><FaPlus /> Create Order</button></td></tr>}
        {!loading && filteredOrders.map((order) => <tr key={order.id}><td><div className="order-name"><span className={order.side === "BUY" ? "order-side buy" : "order-side sell"}>{order.side === "BUY" ? <FaArrowUp /> : <FaArrowDown />}</span><div><strong>{order.strategy}</strong><span>{order.order_type} {order.ticket ? `#${order.ticket}` : "Pending ticket"}</span></div></div></td><td><strong>{symbolName(order.symbol_id)}</strong><span className="order-subvalue">{order.comment || "No comment"}</span></td><td>{accountName(order.account_id)}</td><td><strong>{order.volume}</strong><span className="order-subvalue">{order.executed_price || order.requested_price ? `@ ${order.executed_price || order.requested_price}` : "Market price"}</span></td><td><span className={`order-status order-status--${String(order.status || "").toLowerCase()}`}>{order.status || "UNKNOWN"}</span></td><td>{order.created_at ? new Date(order.created_at).toLocaleDateString() : "-"}</td><td><div className="order-actions"><button title="Execute order" onClick={() => handleExecute(order)} disabled={acting || terminalStatuses.includes(order.status)}><FaPlay /></button><button title="Cancel order" onClick={() => handleCancel(order)} disabled={acting || terminalStatuses.includes(order.status)}><FaTrash /></button><button title="Edit order" onClick={() => { setEditingOrder(order); setModalOpen(true); }} disabled={acting}><FaEdit /></button><button title="Delete order" onClick={() => handleDelete(order)} disabled={acting}><FaTrash /></button></div></td></tr>)}
      </tbody></table></div></section>
      <OrderForm isOpen={modalOpen} onClose={() => !saving && setModalOpen(false)} onSubmit={handleSubmit} order={editingOrder} accounts={accounts} symbols={symbols} loading={saving} />
    </main>
  );
};
export default Orders;
