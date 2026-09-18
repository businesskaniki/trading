import { useEffect, useMemo, useState } from "react";
import { useDispatch, useSelector } from "react-redux";
import {
  FaArrowDown,
  FaArrowUp,
  FaClipboardList,
  FaEdit,
  FaPlay,
  FaPlus,
  FaSearch,
  FaSyncAlt,
  FaTrash,
} from "react-icons/fa";

import OrderForm from "./OrderForm";
import ConfirmModal from "../../../components/common/ConfirmModal";

import { fetchAccounts } from "../../../redux/dashboard/accounts/accountsThunks";

import { fetchAccountSymbols } from "../../../redux/dashboard/symbols/symbolsThunks";

import { clearOrdersError } from "../../../redux/dashboard/orders/ordersSlice";

import {
  createOrder,
  executeOrder,
  fetchOrders,
  removeOrder,
  updateOrder,
  updateOrderStatus,
} from "../../../redux/dashboard/orders/ordersThunks";

import "../../../css/orders.css";

const terminalStatuses = ["FILLED", "CANCELLED", "REJECTED", "EXPIRED"];

const Orders = () => {
  const dispatch = useDispatch();

  const { orders, loading, saving, acting, error } = useSelector(
    (state) => state.orders,
  );

  const accounts = useSelector((state) => state.accounts?.accounts || []);

  const symbolsByAccount = useSelector(
    (state) => state.symbols?.symbolsByAccount || {},
  );

  /*
   * Account-specific symbols are loaded based on the accounts
   * represented in the order registry.
   *
   * We keep track of the account IDs that currently exist
   * in the order list and request their symbol universes.
   */
  const orderAccountIds = useMemo(() => {
    return [
      ...new Set(orders.map((order) => order.account_id).filter(Boolean)),
    ];
  }, [orders]);

  const [query, setQuery] = useState("");
  const [status, setStatus] = useState("ALL");
  const [modalOpen, setModalOpen] = useState(false);
  const [editingOrder, setEditingOrder] = useState(null);
  const [confirmation, setConfirmation] = useState(null);

  /*
   * Load orders and trading accounts.
   */
  useEffect(() => {
    dispatch(fetchOrders());
    dispatch(fetchAccounts());
  }, [dispatch]);

  /*
   * Load account-specific symbols for the accounts represented
   * by the order registry.
   *
   * This replaces the old global fetchSymbols().
   */
  useEffect(() => {
    if (!orderAccountIds.length) {
      return;
    }

    orderAccountIds.forEach((accountId) => {
      dispatch(fetchAccountSymbols(accountId));
    });
  }, [dispatch, orderAccountIds]);

  /*
   * Find an account by ID.
   */
  const accountName = (id) => {
    const account = accounts.find((item) => item.id === id);

    return (
      account?.account_name ||
      account?.account_number ||
      String(id || "-").slice(0, 8)
    );
  };

  /*
   * Find a symbol by canonical symbol ID.
   */
  const symbolName = (id, accountId) => {
    const accountSymbol = (symbolsByAccount[String(accountId)] || []).find(
      (item) => item.symbol_id === id || item.symbol?.id === id,
    );

    return (
      accountSymbol?.symbol_name ||
      accountSymbol?.name ||
      accountSymbol?.symbol?.name ||
      accountSymbol?.broker_symbol ||
      String(id || "-").slice(0, 8)
    );
  };

  /*
   * Status filter options.
   */
  const statuses = useMemo(
    () =>
      [...new Set(orders.map((order) => order.status).filter(Boolean))].sort(),
    [orders],
  );

  /*
   * Filter orders.
   */
  const filteredOrders = useMemo(
    () =>
      orders.filter((order) => {
        const symbol = (symbolsByAccount[String(order.account_id)] || []).find(
          (item) =>
            item.symbol_id === order.symbol_id ||
            item.symbol?.id === order.symbol_id,
        );

        const symbolDisplayName =
          symbol?.symbol_name ||
          symbol?.name ||
          symbol?.symbol?.name ||
          symbol?.broker_symbol ||
          "";

        const text = `
          ${order.strategy || ""}
          ${order.comment || ""}
          ${symbolDisplayName}
          ${order.ticket || ""}
        `.toLowerCase();

        return (
          (!query || text.includes(query.toLowerCase())) &&
          (status === "ALL" || order.status === status)
        );
      }),
    [orders, query, status, symbolsByAccount],
  );

  /*
   * Create / update order.
   *
   * account_id and symbol_id are only removed when updating
   * because changing the account or instrument of an existing
   * order should not be allowed through this form.
   */
  const handleSubmit = async (data) => {
    let result;

    if (editingOrder) {
      const updateData = Object.fromEntries(
        Object.entries(data).filter(
          ([key]) => !["account_id", "symbol_id"].includes(key),
        ),
      );

      result = await dispatch(
        updateOrder({
          orderId: editingOrder.id,
          orderData: updateData,
        }),
      );
    } else {
      result = await dispatch(createOrder(data));
    }

    if (
      createOrder.fulfilled.match(result) ||
      updateOrder.fulfilled.match(result)
    ) {
      setModalOpen(false);
      setEditingOrder(null);
    }
  };

  /*
   * Delete an order.
   */
  const handleDelete = (order) => {
    setConfirmation({
      title: "Delete order?",
      message: `Order ${
        order.ticket || order.id?.slice(0, 8)
      } will be permanently removed.`,
      confirmLabel: "Delete Order",
      danger: true,
      action: () => dispatch(removeOrder(order.id)),
    });
  };

  /*
   * Execute an order.
   */
  const handleExecute = (order) => {
    setConfirmation({
      title: "Execute order?",
      message: `Submit ${order.side} ${order.volume} ${symbolName(
        order.symbol_id,
        order.account_id,
      )} to the execution pipeline.`,
      confirmLabel: "Execute Order",
      action: () => dispatch(executeOrder(order.id)),
    });
  };

  /*
   * Cancel an order.
   */
  const handleCancel = (order) => {
    setConfirmation({
      title: "Cancel order?",
      message:
        "This order will be marked as cancelled and can no longer be executed.",
      confirmLabel: "Cancel Order",
      danger: true,
      action: () =>
        dispatch(
          updateOrderStatus({
            orderId: order.id,
            statusValue: "CANCELLED",
          }),
        ),
    });
  };

  /*
   * Execute confirmation action.
   */
  const confirmAction = async () => {
    if (!confirmation?.action) {
      return;
    }

    await confirmation.action();
    setConfirmation(null);
  };

  /*
   * Open create modal.
   */
  const openCreate = () => {
    setEditingOrder(null);
    setModalOpen(true);
  };

  /*
   * Open edit modal.
   */
  const openEdit = (order) => {
    setEditingOrder(order);
    setModalOpen(true);
  };

  /*
   * Refresh orders.
   */
  const refreshOrders = () => {
    dispatch(fetchOrders());

    /*
     * Also refresh account symbols for all accounts currently
     * represented in the order registry.
     */
    orderAccountIds.forEach((accountId) => {
      dispatch(fetchAccountSymbols(accountId));
    });
  };

  return (
    <main className="orders-page">
      {/* =====================================================
          HEADER
      ====================================================== */}

      <section className="orders-header">
        <div>
          <span className="orders-eyebrow">EXECUTION PIPELINE</span>

          <h1>Orders</h1>

          <p>
            Create, monitor and execute trading instructions across your
            accounts.
          </p>
        </div>

        <button
          type="button"
          className="order-button order-button--primary"
          onClick={openCreate}
          disabled={saving || accounts.length === 0}
        >
          <FaPlus />
          Create Order
        </button>
      </section>

      {/* =====================================================
          ERROR
      ====================================================== */}

      {error && (
        <div className="orders-error">
          <span>
            {typeof error === "string"
              ? error
              : "Unable to process order request."}
          </span>

          <button
            type="button"
            onClick={() => dispatch(clearOrdersError())}
            aria-label="Dismiss error"
          >
            x
          </button>
        </div>
      )}

      {/* =====================================================
          STATISTICS
      ====================================================== */}

      <section className="orders-stats">
        <div className="order-stat">
          <FaClipboardList />

          <div>
            <span>Total Orders</span>
            <strong>{orders.length}</strong>
          </div>
        </div>

        <div className="order-stat">
          <FaPlay />

          <div>
            <span>Pending Work</span>

            <strong>
              {
                orders.filter((order) =>
                  ["CREATED", "SUBMITTED", "PENDING"].includes(order.status),
                ).length
              }
            </strong>
          </div>
        </div>

        <div className="order-stat">
          <FaArrowUp />

          <div>
            <span>Filled Orders</span>

            <strong>
              {orders.filter((order) => order.status === "FILLED").length}
            </strong>
          </div>
        </div>

        <div className="order-stat">
          <FaArrowDown />

          <div>
            <span>Sell Orders</span>

            <strong>
              {orders.filter((order) => order.side === "SELL").length}
            </strong>
          </div>
        </div>
      </section>

      {/* =====================================================
          SEARCH / FILTER
      ====================================================== */}

      <section className="orders-toolbar">
        <div className="orders-search">
          <FaSearch />

          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Search strategy, symbol or ticket..."
          />
        </div>

        <div className="orders-filters">
          <select
            value={status}
            onChange={(event) => setStatus(event.target.value)}
          >
            <option value="ALL">All statuses</option>

            {statuses.map((item) => (
              <option key={item} value={item}>
                {item}
              </option>
            ))}
          </select>

          <button
            type="button"
            className="orders-refresh"
            onClick={refreshOrders}
            disabled={loading}
            title="Refresh orders"
          >
            <FaSyncAlt className={loading ? "orders-spin" : ""} />
          </button>
        </div>
      </section>

      {/* =====================================================
          ORDER TABLE
      ====================================================== */}

      <section className="orders-card">
        <header className="orders-card__header">
          <div>
            <span>ORDER REGISTRY</span>

            <h2>Trading Orders</h2>
          </div>

          <span className="orders-count">
            {filteredOrders.length}{" "}
            {filteredOrders.length === 1 ? "order" : "orders"}
          </span>
        </header>

        <div className="orders-table-wrapper">
          <table className="orders-table">
            <thead>
              <tr>
                <th>Order</th>
                <th>Instrument</th>
                <th>Account</th>
                <th>Volume / Price</th>
                <th>Status</th>
                <th>Created</th>
                <th>Actions</th>
              </tr>
            </thead>

            <tbody>
              {loading && (
                <tr>
                  <td colSpan="7" className="orders-empty">
                    <FaSyncAlt className="orders-spin" />

                    <strong>Loading orders...</strong>
                  </td>
                </tr>
              )}

              {!loading && filteredOrders.length === 0 && (
                <tr>
                  <td colSpan="7" className="orders-empty">
                    <FaClipboardList />

                    <strong>
                      {orders.length
                        ? "No matching orders"
                        : "No orders configured"}
                    </strong>

                    <span>
                      {orders.length
                        ? "Try changing your search or filter."
                        : "Create your first trading instruction to get started."}
                    </span>

                    <button
                      type="button"
                      className="order-button order-button--primary"
                      onClick={openCreate}
                      disabled={accounts.length === 0}
                    >
                      <FaPlus />
                      Create Order
                    </button>
                  </td>
                </tr>
              )}

              {!loading &&
                filteredOrders.map((order) => (
                  <tr key={order.id}>
                    {/* ORDER */}
                    <td>
                      <div className="order-name">
                        <span
                          className={
                            order.side === "BUY"
                              ? "order-side buy"
                              : "order-side sell"
                          }
                        >
                          {order.side === "BUY" ? (
                            <FaArrowUp />
                          ) : (
                            <FaArrowDown />
                          )}
                        </span>

                        <div>
                          <strong>{order.strategy || "Manual Order"}</strong>

                          <span>
                            {order.order_type}{" "}
                            {order.ticket
                              ? `#${order.ticket}`
                              : "Pending ticket"}
                          </span>
                        </div>
                      </div>
                    </td>

                    {/* INSTRUMENT */}
                    <td>
                      <strong>
                        {symbolName(order.symbol_id, order.account_id)}
                      </strong>

                      <span className="order-subvalue">
                        {order.comment || "No comment"}
                      </span>
                    </td>

                    {/* ACCOUNT */}
                    <td>{accountName(order.account_id)}</td>

                    {/* VOLUME / PRICE */}
                    <td>
                      <strong>{order.volume}</strong>

                      <span className="order-subvalue">
                        {order.executed_price || order.requested_price
                          ? `@ ${order.executed_price || order.requested_price}`
                          : "Market price"}
                      </span>
                    </td>

                    {/* STATUS */}
                    <td>
                      <span
                        className={`order-status order-status--${String(
                          order.status || "",
                        ).toLowerCase()}`}
                      >
                        {order.status || "UNKNOWN"}
                      </span>
                    </td>

                    {/* CREATED */}
                    <td>
                      {order.created_at
                        ? new Date(order.created_at).toLocaleDateString()
                        : "-"}
                    </td>

                    {/* ACTIONS */}
                    <td>
                      <div className="order-actions">
                        <button
                          type="button"
                          title="Execute order"
                          onClick={() => handleExecute(order)}
                          disabled={
                            acting || terminalStatuses.includes(order.status)
                          }
                        >
                          <FaPlay />
                        </button>

                        <button
                          type="button"
                          title="Cancel order"
                          onClick={() => handleCancel(order)}
                          disabled={
                            acting || terminalStatuses.includes(order.status)
                          }
                        >
                          <FaTrash />
                        </button>

                        <button
                          type="button"
                          title="Edit order"
                          onClick={() => openEdit(order)}
                          disabled={acting}
                        >
                          <FaEdit />
                        </button>

                        <button
                          type="button"
                          title="Delete order"
                          onClick={() => handleDelete(order)}
                          disabled={acting}
                        >
                          <FaTrash />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
            </tbody>
          </table>
        </div>
      </section>

      {/* =====================================================
          ORDER FORM
      ====================================================== */}

      <OrderForm
        isOpen={modalOpen}
        onClose={() => !saving && setModalOpen(false)}
        onSubmit={handleSubmit}
        order={editingOrder}
        accounts={accounts}
        symbols={symbols}
        loading={saving}
      />

      {/* =====================================================
          CONFIRMATION
      ====================================================== */}

      <ConfirmModal
        isOpen={Boolean(confirmation)}
        {...confirmation}
        loading={acting}
        onConfirm={confirmAction}
        onClose={() => !acting && setConfirmation(null)}
      />
    </main>
  );
};

export default Orders;
