import { createAsyncThunk } from "@reduxjs/toolkit";
import tradesAPI from "./tradesAPI";

export const fetchTrades = createAsyncThunk(
  "trades/fetchTrades",
  async (_, { rejectWithValue }) => {
    try {
      return await tradesAPI.getTrades();
    } catch (error) {
      return rejectWithValue(
        error.response?.data?.detail || error.message || "Failed to load trades.",
      );
    }
  },
);