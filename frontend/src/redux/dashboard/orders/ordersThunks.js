import { createAsyncThunk } from "@reduxjs/toolkit";
import ordersAPI from "./ordersAPI";

const getErrorMessage = (error, fallback) => {
  const detail = error.response?.data?.detail;
  if (Array.isArray(detail)) return detail.map((item) => item.msg || "Invalid value.").join(" ");
  if (typeof detail === "string") return detail;
  return error.message || fallback;
};

const thunk = (type, request, fallback) => createAsyncThunk(type, async (payload, { rejectWithValue }) => {
  try { return await request(payload); } catch (error) { return rejectWithValue(getErrorMessage(error, fallback)); }
});

export const fetchOrders = thunk("orders/fetchOrders", () => ordersAPI.getOrders(), "Failed to load orders.");
export const createOrder = thunk("orders/createOrder", (data) => ordersAPI.createOrder(data), "Failed to create order.");
export const updateOrder = thunk("orders/updateOrder", ({ orderId, orderData }) => ordersAPI.updateOrder(orderId, orderData), "Failed to update order.");
export const removeOrder = thunk("orders/removeOrder", (orderId) => ordersAPI.deleteOrder(orderId), "Failed to delete order.");
export const updateOrderStatus = thunk("orders/updateOrderStatus", ({ orderId, statusValue }) => ordersAPI.updateStatus(orderId, statusValue), "Failed to update order status.");
export const executeOrder = thunk("orders/executeOrder", (orderId) => ordersAPI.executeOrder(orderId), "Failed to execute order.");
