import { createSlice } from "@reduxjs/toolkit";
import { createOrder, executeOrder, fetchOrders, removeOrder, updateOrder, updateOrderStatus } from "./ordersThunks";

const initialState = { orders: [], loading: false, saving: false, acting: false, error: null };
const replaceOrder = (state, order) => { const index = state.orders.findIndex((item) => item.id === order?.id); if (index !== -1) state.orders[index] = order; };
const ordersSlice = createSlice({
  name: "orders",
  initialState,
  reducers: { clearOrdersError: (state) => { state.error = null; } },
  extraReducers: (builder) => {
    builder
      .addCase(fetchOrders.pending, (state) => { state.loading = true; state.error = null; })
      .addCase(fetchOrders.fulfilled, (state, action) => { state.loading = false; state.orders = Array.isArray(action.payload) ? action.payload : action.payload?.items || []; })
      .addCase(fetchOrders.rejected, (state, action) => { state.loading = false; state.error = action.payload; })
      .addCase(createOrder.pending, (state) => { state.saving = true; state.error = null; })
      .addCase(createOrder.fulfilled, (state, action) => { state.saving = false; state.orders.unshift(action.payload); })
      .addCase(createOrder.rejected, (state, action) => { state.saving = false; state.error = action.payload; })
      .addCase(updateOrder.pending, (state) => { state.saving = true; state.error = null; })
      .addCase(updateOrder.fulfilled, (state, action) => { state.saving = false; replaceOrder(state, action.payload); })
      .addCase(updateOrder.rejected, (state, action) => { state.saving = false; state.error = action.payload; })
      .addCase(updateOrderStatus.pending, (state) => { state.acting = true; state.error = null; })
      .addCase(updateOrderStatus.fulfilled, (state, action) => { state.acting = false; replaceOrder(state, action.payload); })
      .addCase(updateOrderStatus.rejected, (state, action) => { state.acting = false; state.error = action.payload; })
      .addCase(executeOrder.pending, (state) => { state.acting = true; state.error = null; })
      .addCase(executeOrder.fulfilled, (state, action) => { state.acting = false; replaceOrder(state, action.payload); })
      .addCase(executeOrder.rejected, (state, action) => { state.acting = false; state.error = action.payload; })
      .addCase(removeOrder.pending, (state) => { state.acting = true; state.error = null; })
      .addCase(removeOrder.fulfilled, (state, action) => { state.acting = false; state.orders = state.orders.filter((order) => order.id !== action.payload); })
      .addCase(removeOrder.rejected, (state, action) => { state.acting = false; state.error = action.payload; });
  },
});

export const { clearOrdersError } = ordersSlice.actions;
export default ordersSlice.reducer;
