import { createAsyncThunk } from "@reduxjs/toolkit";

import dashboardAPI from "./dashboardAPI";

// =====================================================
// ERROR HANDLING
// =====================================================

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

// =====================================================
// LOAD DASHBOARD CORE DATA
// =====================================================
//
// Only load data that is actually required by the
// Dashboard itself.
//
// Accounts are owned by accountsSlice.
// Engine status is owned by engineSlice.
// Trading universe is owned by symbolsSlice.
// Broker account is loaded separately once an account
// has been selected.
//
// This thunk therefore only loads:
//   - positions
//   - recent trades
//
// Both requests execute concurrently.
// =====================================================

export const loadDashboard = createAsyncThunk(
  "dashboard/loadDashboard",
  async (_, thunkAPI) => {
    try {
      const [positions, trades] = await Promise.all([
        dashboardAPI.getPositions(),
        dashboardAPI.getTrades(),
      ]);

      return {
        positions,
        trades,
      };
    } catch (error) {
      return thunkAPI.rejectWithValue(
        getErrorMessage(error, "Failed to load dashboard data."),
      );
    }
  },
);

// =====================================================
// BROKER ACCOUNT
// =====================================================
//
// This is intentionally separate from loadDashboard.
// The broker account requires a selected account ID.
// =====================================================

export const fetchBrokerAccount = createAsyncThunk(
  "dashboard/fetchBrokerAccount",
  async (accountId, thunkAPI) => {
    try {
      if (!accountId) {
        return thunkAPI.rejectWithValue("A trading account must be selected.");
      }

      return await dashboardAPI.getBrokerAccount(accountId);
    } catch (error) {
      return thunkAPI.rejectWithValue(
        getErrorMessage(error, "Failed to load broker account information."),
      );
    }
  },
);

// =====================================================
// INDIVIDUAL DASHBOARD REQUESTS
// =====================================================

export const fetchAccounts = createAsyncThunk(
  "dashboard/fetchAccounts",
  async (_, thunkAPI) => {
    try {
      return await dashboardAPI.getAccounts();
    } catch (error) {
      return thunkAPI.rejectWithValue(
        getErrorMessage(error, "Failed to load accounts."),
      );
    }
  },
);

export const fetchActiveAccounts = createAsyncThunk(
  "dashboard/fetchActiveAccounts",
  async (_, thunkAPI) => {
    try {
      return await dashboardAPI.getActiveAccounts();
    } catch (error) {
      return thunkAPI.rejectWithValue(
        getErrorMessage(error, "Failed to load active accounts."),
      );
    }
  },
);

export const fetchPositions = createAsyncThunk(
  "dashboard/fetchPositions",
  async (_, thunkAPI) => {
    try {
      return await dashboardAPI.getPositions();
    } catch (error) {
      return thunkAPI.rejectWithValue(
        getErrorMessage(error, "Failed to load positions."),
      );
    }
  },
);

export const fetchTrades = createAsyncThunk(
  "dashboard/fetchTrades",
  async (_, thunkAPI) => {
    try {
      return await dashboardAPI.getTrades();
    } catch (error) {
      return thunkAPI.rejectWithValue(
        getErrorMessage(error, "Failed to load trades."),
      );
    }
  },
);

export const fetchLatestTrade = createAsyncThunk(
  "dashboard/fetchLatestTrade",
  async (_, thunkAPI) => {
    try {
      return await dashboardAPI.getLatestTrade();
    } catch (error) {
      return thunkAPI.rejectWithValue(
        getErrorMessage(error, "Failed to load latest trade."),
      );
    }
  },
);

export const fetchSymbols = createAsyncThunk(
  "dashboard/fetchSymbols",
  async (_, thunkAPI) => {
    try {
      return await dashboardAPI.getSymbols();
    } catch (error) {
      return thunkAPI.rejectWithValue(
        getErrorMessage(error, "Failed to load symbols."),
      );
    }
  },
);

export const fetchStrategyRuns = createAsyncThunk(
  "dashboard/fetchStrategyRuns",
  async (_, thunkAPI) => {
    try {
      return await dashboardAPI.getStrategyRuns();
    } catch (error) {
      return thunkAPI.rejectWithValue(
        getErrorMessage(error, "Failed to load strategy runs."),
      );
    }
  },
);

export const fetchLatestPerformance = createAsyncThunk(
  "dashboard/fetchLatestPerformance",
  async (_, thunkAPI) => {
    try {
      return await dashboardAPI.getLatestPerformance();
    } catch (error) {
      return thunkAPI.rejectWithValue(
        getErrorMessage(error, "Failed to load latest performance."),
      );
    }
  },
);

export const fetchAccountSummary = createAsyncThunk(
  "dashboard/fetchAccountSummary",
  async (accountId, thunkAPI) => {
    try {
      return await dashboardAPI.getAccountSummary(accountId);
    } catch (error) {
      return thunkAPI.rejectWithValue(
        getErrorMessage(error, "Failed to load account summary."),
      );
    }
  },
);

export const fetchStrategyPerformance = createAsyncThunk(
  "dashboard/fetchStrategyPerformance",
  async (accountId, thunkAPI) => {
    try {
      return await dashboardAPI.getStrategyPerformance(accountId);
    } catch (error) {
      return thunkAPI.rejectWithValue(
        getErrorMessage(error, "Failed to load strategy performance."),
      );
    }
  },
);

export const fetchRiskProfile = createAsyncThunk(
  "dashboard/fetchRiskProfile",
  async (accountId, thunkAPI) => {
    try {
      return await dashboardAPI.getRiskProfile(accountId);
    } catch (error) {
      return thunkAPI.rejectWithValue(
        getErrorMessage(error, "Failed to load risk profile."),
      );
    }
  },
);

export const fetchEffectiveRisk = createAsyncThunk(
  "dashboard/fetchEffectiveRisk",
  async (accountId, thunkAPI) => {
    try {
      return await dashboardAPI.getEffectiveRisk(accountId);
    } catch (error) {
      return thunkAPI.rejectWithValue(
        getErrorMessage(error, "Failed to load effective risk."),
      );
    }
  },
);
