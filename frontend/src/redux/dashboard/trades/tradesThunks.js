import { createAsyncThunk } from "@reduxjs/toolkit";
import tradesAPI from "./tradesAPI";
export const fetchTrades = createAsyncThunk(
  "trades/fetchTrades",
  async (accountId, { rejectWithValue }) => {
    try {
      if (!accountId) {
        return rejectWithValue("Select a trading account first.");
      }

      return await tradesAPI.getTrades(accountId);
    } catch (error) {
      return rejectWithValue(
        error.response?.data?.detail ||
          error.message ||
          "Failed to load trades.",
      );
    }
  },
);
