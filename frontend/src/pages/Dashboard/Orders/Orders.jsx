
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

const belongsToAccount = (order, accountId) =>
  accountId != null &&
  order?.account_id != null &&
  String(order.account_id) === String(accountId);

const Orders = () => {
  const dispatch = useDispatch();

  const {
    orders: reduxOrders = [],
    loading,
    saving,
    acting,
    error,
  } = useSelector((state) => state.orders);

  const accounts = useSelector(
    (state) => state.accounts?.accounts || [],
  );

  const selectedAccount = useSelector(
    (state) => state.accounts?.selectedAccount ?? null,
  );

  const selectedAccountId = selectedAccount?.id ?? null;

  const symbolsByAccount = useSelector(
    (state) => state.symbols?.symbolsByAccount || {},
  );

  const [query, setQuery] = useState("");
  const [status, setStatus] = useState("ALL");
  const [modalOpen, setModalOpen] = useState(false);
  const [editingOrder, setEditingOrder] = useState(null);
  const [confirmation, setConfirmation] = useState(null);

  /*
   * Account-scoped order registry.
   *
   * Filter locally as an additional safeguard against stale Redux data
   * when the selected account changes.
   */
  const orders = useMemo(() => {
    if (!selectedAccountId) {
      return [];
    }

    const source = Array.isArray(reduxOrders) ? reduxOrders : [];

    return source.filter((order) =>
      belongsToAccount(order, selectedAccountId),
    );
  }, [reduxOrders, selectedAccountId]);

  /*
   * The order form uses only the selected account and its symbols.
   * This prevents accidentally creating an order against another
   * account while viewing the current account's order registry.
   */
  const formAccounts = useMemo(
    () => (selectedAccount ? [selectedAccount] : []),
    [selectedAccount],
  );

  const symbols = useMemo(() => {
    if (!selectedAccountId) {
      return [];
    }

    const accountSymbols =
      symbolsByAccount[String(selectedAccountId)] || [];

    if (!Array.isArray(accountSymbols)) {
      return [];
    }

    return accountSymbols.map((symbol) => ({
      ...symbol,
      account_id: symbol.account_id || selectedAccountId,
    }));
  }, [symbolsByAccount, selectedAccountId]);

  /*
   * Load accounts first. The selected-account effect below will load
   * orders once the account slice establishes the active selection.
   */
  useEffect(() => {
    dispatch(fetchAccounts());
  }, [dispatch]);

  /*
   * Load only the selected account's orders and symbol mapping.
   * Re-run these requests whenever the selected account changes.
   */
  useEffect(() => {
    if (!selectedAccountId) {
      return;
    }

    dispatch(fetchOrders(selectedAccountId));
    dispatch(fetchAccountSymbols(selectedAccountId));
  }, [dispatch, selectedAccountId]);

  /*
   * Resolve an account name.
   */
  const accountName = (id) => {
    const account = accounts.find(
      (item) => String(item.id) === String(id),
    );

    return (
      account?.account_name ||
      account?.account_number ||
      String(id || "-").slice(0, 8)
    );
  };

  /*
   * Resolve a symbol against the relevant account's symbol mapping.
   */
  const symbolName = (id, accountId) => {
    const accountSymbols =
      symbolsByAccount[String(accountId)] || [];

    const accountSymbol = accountSymbols.find(
      (item) =>
        (item.symbol_id != null &&
          String(item.symbol_id) === String(id)) ||
        (item.symbol?.id != null &&
          String(item.symbol.id) === String(id)),
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
   * Status options are derived from the selected account's orders only.
   */
  const statuses = useMemo(
    () =>
      [
        ...new Set(
          orders
            .map((order) => order.status)
            .filter(Boolean),
        ),
      ].sort(),
    [orders],
  );

  /*
   * Search and status filtering, applied after account scoping.
   */
  const filteredOrders = useMemo(() => {
    const normalizedQuery = query.trim().toLowerCase();

    return orders.filter((order) => {
      const accountSymbols =
        symbolsByAccount[String(selectedAccountId)] || [];

      const symbol = accountSymbols.find(
        (item) =>
          (item.symbol_id != null &&
            String(item.symbol_id) === String(order.symbol_id)) ||
          (item.symbol?.id != null &&
            String(item.symbol.id) === String(order.symbol_id)),
      );

      const symbolDisplayName =
        symbol?.symbol_name ||
        symbol?.name ||
        symbol?.symbol?.name ||
        symbol?.broker_symbol ||
        "";

      const searchableText = [
        order.strategy,
        order.comment,
        symbolDisplayName,
        order.ticket,
        order.side,
        order.order_type,
      ]
        .filter(Boolean)
        .join(" ")
        .toLowerCase();

      return (
        (!normalizedQuery ||
          searchableText.includes(normalizedQuery)) &&
        (status === "ALL" || order.status === status)
      );
    });
  }, [orders, query, status, symbolsByAccount, selectedAccountId]);

  /*
   * Create or update an order.
   */
  const handleSubmit = async (data) => {
    if (!selectedAccountId) {
      return;
    }

    let result;

    if (editingOrder) {
      // Do not permit edits to move the order to a different account
      // or symbol through the update payload.
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
      // Ensure new orders belong to the currently selected account.
      result = await dispatch(
        createOrder({
          ...data,
          account_id: selectedAccountId,
        }),
      );
    }

    if (
      createOrder.fulfilled.match(result) ||
      updateOrder.fulfilled.match(result)
    ) {
      setModalOpen(false);
      setEditingOrder(null);

      // Reload the scoped registry to reflect the persisted result.
      dispatch(fetchOrders(selectedAccountId));
    }
  };

  /*
   * Delete an order.
   */
  const handleDelete = (order) => {
    if (!belongsToAccount(order, selectedAccountId)) {
      return;
    }

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
    if (!belongsToAccount(order, selectedAccountId)) {
      return;
    }

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
    if (!belongsToAccount(order, selectedAccountId)) {
      return;
    }

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
   * Execute a confirmation action and reload the current account's
   * orders after a successful mutation.
   */
  const confirmAction = async () => {
    if (!confirmation?.action) {
      return;
    }

    try {
      const result = await confirmation.action();

      // Redux Toolkit rejected async thunks resolve to rejected actions
      // unless unwrap() is used. Detect those responses here.
      if (result?.meta?.requestStatus === "rejected") {
        return;
      }

      if (selectedAccountId) {
        dispatch(fetchOrders(selectedAccountId));
      }

      setConfirmation(null);
    } catch (actionError) {
      console.error("Order action failed:", actionError);
    }
  };

  /*
   * Open the create modal.
   */
  const openCreate = () => {
    if (!selectedAccountId) {
      return;
    }

    setEditingOrder(null);
    setModalOpen(true);
  };

  /*
   * Open the edit modal only for an order in the selected account.
   */
  const openEdit = (order) => {
    if (!belongsToAccount(order, selectedAccountId)) {
      return;
    }

    setEditingOrder(order);
    setModalOpen(true);
  };

  /*
   * Refresh only the selected account's orders and symbols.
   */
  const refreshOrders = () => {
    if (!selectedAccountId) {
      return;
    }

    dispatch(fetchOrders(selectedAccountId));
    dispatch(fetchAccountSymbols(selectedAccountId));
  };

  return (
    <main className="orders-page">
      {/* HEADER */}
      <section className="orders-header">
        <div>
          <span className="orders-eyebrow">
            EXECUTION PIPELINE
            {selectedAccountId
              ? ` · ${accountName(selectedAccountId)}`
              : ""}
          </span>

          <h1>Orders</h1>

          <p>
            Create, monitor and execute trading instructions for
            the selected trading account.
          </p>
        </div>

        <button
          type="button"
          className="order-button order-button--primary"
          onClick={openCreate}
          disabled={saving || !selectedAccountId}
        >
          <FaPlus />
          Create Order
        </button>
      </section>

      {/* ERROR */}
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

      {/* STATISTICS — SELECTED ACCOUNT ONLY */}
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
                  ["CREATED", "SUBMITTED", "PENDING"].includes(
                    order.status,
                  ),
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
              {
                orders.filter(
                  (order) => order.status === "FILLED",
                ).length
              }
            </strong>
          </div>
        </div>

        <div className="order-stat">
          <FaArrowDown />

          <div>
            <span>Sell Orders</span>

            <strong>
              {
                orders.filter(
                  (order) => order.side === "SELL",
                ).length
              }
            </strong>
          </div>
        </div>
      </section>

      {/* SEARCH / FILTER */}
      <section className="orders-toolbar">
        <div className="orders-search">
          <FaSearch />

          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Search strategy, symbol or ticket..."
            aria-label="Search orders"
            disabled={!selectedAccountId}
          />
        </div>

        <div className="orders-filters">
          <select
            value={status}
            onChange={(event) => setStatus(event.target.value)}
            aria-label="Filter orders by status"
            disabled={!selectedAccountId}
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
            disabled={loading || !selectedAccountId}
            title="Refresh orders"
          >
            <FaSyncAlt
              className={loading ? "orders-spin" : ""}
            />
          </button>
        </div>
      </section>

      {/* ORDER TABLE */}
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
              {!selectedAccountId && (
                <tr>
                  <td colSpan={7} className="orders-empty">
                    <FaClipboardList />
                    <strong>No trading account selected</strong>
                    <span>
                      Select a trading account to view and manage
                      its orders.
                    </span>
                  </td>
                </tr>
              )}

              {selectedAccountId &&
                loading &&
                orders.length === 0 && (
                  <tr>
                    <td colSpan={7} className="orders-empty">
                      <FaSyncAlt className="orders-spin" />
                      <strong>Loading orders...</strong>
                    </td>
                  </tr>
                )}

              {selectedAccountId &&
                !loading &&
                filteredOrders.length === 0 && (
                  <tr>
                    <td colSpan={7} className="orders-empty">
                      <FaClipboardList />

                      <strong>
                        {orders.length
                          ? "No matching orders"
                          : "No orders configured"}
                      </strong>

                      <span>
                        {orders.length
                          ? "Try changing your search or status filter."
                          : "Create your first trading instruction for this account."}
                      </span>

                      {!orders.length && (
                        <button
                          type="button"
                          className="order-button order-button--primary"
                          onClick={openCreate}
                          disabled={!selectedAccountId || saving}
                        >
                          <FaPlus />
                          Create Order
                        </button>
                      )}
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
                          <strong>
                            {order.strategy || "Manual Order"}
                          </strong>

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
                        {symbolName(
                          order.symbol_id,
                          order.account_id,
                        )}
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
                        {order.executed_price ||
                        order.requested_price
                          ? `@ ${
                              order.executed_price ||
                              order.requested_price
                            }`
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
                        ? new Date(
                            order.created_at,
                          ).toLocaleDateString()
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
                            acting ||
                            terminalStatuses.includes(order.status)
                          }
                        >
                          <FaPlay />
                        </button>

                        <button
                          type="button"
                          title="Cancel order"
                          onClick={() => handleCancel(order)}
                          disabled={
                            acting ||
                            terminalStatuses.includes(order.status)
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

      {/* ORDER FORM — SELECTED ACCOUNT */}
      <OrderForm
        isOpen={modalOpen}
        onClose={() => !saving && setModalOpen(false)}
        onSubmit={handleSubmit}
        order={editingOrder}
        accounts={formAccounts}
        symbols={symbols}
        loading={saving}
      />

      {/* CONFIRMATION */}
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
