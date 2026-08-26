import { configureStore } from "@reduxjs/toolkit";

import authReducer from "./auth/authSlice";
import dashboardReducer from "./dashboard/dashboardSlice";
import accountsReducer from "./dashboard/accounts/accountsSlice"
import symbolsReducer from "./dashboard/symbols/symbolsSlice";
import ordersReducer from "./dashboard/orders/ordersSlice";
import positionsReducer from "./dashboard/positions/positionsSlice";
import tradesReducer from "./dashboard/trades/tradesSlice";

export const store = configureStore({
  reducer: {
    auth: authReducer,
    dashboard: dashboardReducer,
    accounts: accountsReducer,
    symbols: symbolsReducer,
    orders: ordersReducer,
    positions: positionsReducer,
    trades: tradesReducer,
  },

  middleware: (getDefaultMiddleware) =>
    getDefaultMiddleware({
      serializableCheck: false,
    }),

  devTools: import.meta.env.DEV,
});

export default store;
