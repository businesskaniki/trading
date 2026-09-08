import { createAsyncThunk } from "@reduxjs/toolkit";

import symbolsAPI from "./symbolsAPI";

const getErrorMessage = (error, fallback) => {
  const detail = error.response?.data?.detail;

  if (Array.isArray(detail)) {
    return detail.map((item) => item.msg || "Invalid value.").join(" ");
  }

  if (typeof detail === "string") {
    return detail;
  }

  return error.message || fallback;
};

/**
 * Synchronize symbols from MT5 for the selected trading account.
 */
export const syncSymbols = createAsyncThunk(
  "symbols/syncSymbols",
  async (accountId, { rejectWithValue }) => {
    try {
      return await symbolsAPI.syncSymbols(accountId);
    } catch (error) {
      return rejectWithValue(
        getErrorMessage(error, "Failed to synchronize symbols from MT5."),
      );
    }
  },
);

/**
 * Load all symbols available for the selected trading account.
 */
export const fetchAccountSymbols = createAsyncThunk(
  "symbols/fetchAccountSymbols",
  async (accountId, { rejectWithValue }) => {
    try {
      return await symbolsAPI.getAccountSymbols(accountId);
    } catch (error) {
      return rejectWithValue(
        getErrorMessage(error, "Failed to load trading account symbols."),
      );
    }
  },
);

/**
 * Load only the symbols currently enabled for trading.
 */
export const fetchTradingUniverse = createAsyncThunk(
  "symbols/fetchTradingUniverse",
  async (accountId, { rejectWithValue }) => {
    try {
      return await symbolsAPI.getTradingUniverse(accountId);
    } catch (error) {
      return rejectWithValue(
        getErrorMessage(error, "Failed to load trading universe."),
      );
    }
  },
);

/**
 * Enable or disable one symbol.
 */
export const setSymbolSelection = createAsyncThunk(
  "symbols/setSymbolSelection",
  async ({ accountId, accountSymbolId, enabled }, { rejectWithValue }) => {
    try {
      return await symbolsAPI.setSymbolSelection(
        accountId,
        accountSymbolId,
        enabled,
      );
    } catch (error) {
      return rejectWithValue(
        getErrorMessage(error, "Failed to update symbol selection."),
      );
    }
  },
);
