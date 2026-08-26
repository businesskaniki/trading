import api from "../../../api/axios";

const ordersAPI = {
  getOrders: async () => (await api.get("/orders/")).data,
  createOrder: async (orderData) => (await api.post("/orders/", orderData)).data,
  getOrder: async (orderId) => (await api.get(`/orders/${orderId}`)).data,
  updateOrder: async (orderId, orderData) => (await api.patch(`/orders/${orderId}`, orderData)).data,
  deleteOrder: async (orderId) => { await api.delete(`/orders/${orderId}`); return orderId; },
  updateStatus: async (orderId, statusValue) => (await api.patch(`/orders/${orderId}/status`, null, { params: { status_value: statusValue } })).data,
  executeOrder: async (orderId) => (await api.post(`/orders/${orderId}/execute`)).data,
};

export default ordersAPI;
