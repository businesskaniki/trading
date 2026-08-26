import { createSlice } from "@reduxjs/toolkit";
import { fetchTrades } from "./tradesThunks";

const tradesSlice = createSlice({
  name: "trades",
  initialState: { trades: [], loading: false, error: null },
  reducers: {
    clearTradesError: (state) => {
      state.error = null;
    },
  },
  extraReducers: (builder) => {
    builder
      .addCase(fetchTrades.pending, (state) => {
        state.loading = true;
        state.error = null;
      })
      .addCase(fetchTrades.fulfilled, (state, action) => {
        state.loading = false;
        state.trades = Array.isArray(action.payload)
          ? action.payload
          : action.payload?.items || [];
      })
      .addCase(fetchTrades.rejected, (state, action) => {
        state.loading = false;
        state.error = action.payload || "Failed to load trades.";
      });
  },
});

export const { clearTradesError } = tradesSlice.actions;
export default tradesSlice.reducer;