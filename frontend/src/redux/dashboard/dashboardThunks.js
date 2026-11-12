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
// ACCOUNT VALIDATION
// =====================================================

const requireAccountId = (accountId) => {
  if (typeof accountId !== "string" || accountId.trim().length === 0) {
    throw new Error("Select a trading account first.");
  }

  return accountId;
};

// =====================================================
// LOAD DASHBOARD CORE DATA
// =====================================================
//
// Requires the selected trading account ID.
//
// Positions and trades are fetched concurrently and
// both requests are scoped to that account.
// =====================================================

export const loadDashboard = createAsyncThunk(
  "dashboard/loadDashboard",
  async (accountId, thunkAPI) => {
    try {
      const selectedAccountId = requireAccountId(accountId);

      const [positions, trades] = await Promise.all([
        dashboardAPI.getPositions(selectedAccountId),
        dashboardAPI.getTrades(selectedAccountId),
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

export const fetchBrokerAccount = createAsyncThunk(
  "dashboard/fetchBrokerAccount",
  async (accountId, thunkAPI) => {
    try {
      const selectedAccountId = requireAccountId(accountId);

      return await dashboardAPI.getBrokerAccount(selectedAccountId);
    } catch (error) {
      return thunkAPI.rejectWithValue(
        getErrorMessage(error, "Failed to load broker account information."),
      );
    }
  },
);

// =====================================================
// ACCOUNTS
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

// =====================================================
// INDIVIDUAL DASHBOARD REQUESTS
// =====================================================

export const fetchPositions = createAsyncThunk(
  "dashboard/fetchPositions",
  async (accountId, thunkAPI) => {
    try {
      const selectedAccountId = requireAccountId(accountId);

      return await dashboardAPI.getPositions(selectedAccountId);
    } catch (error) {
      return thunkAPI.rejectWithValue(
        getErrorMessage(error, "Failed to load positions."),
      );
    }
  },
);

export const fetchTrades = createAsyncThunk(
  "dashboard/fetchTrades",
  async (accountId, thunkAPI) => {
    try {
      const selectedAccountId = requireAccountId(accountId);

      return await dashboardAPI.getTrades(selectedAccountId);
    } catch (error) {
      return thunkAPI.rejectWithValue(
        getErrorMessage(error, "Failed to load trades."),
      );
    }
  },
);

// =====================================================
// LATEST TRADE
// =====================================================

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

// =====================================================
// SYMBOLS
// =====================================================

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

// =====================================================
// STRATEGY RUNS
// =====================================================

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

// =====================================================
// PERFORMANCE
// =====================================================

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

// =====================================================
// ACCOUNT SUMMARY
// =====================================================

export const fetchAccountSummary = createAsyncThunk(
  "dashboard/fetchAccountSummary",
  async (accountId, thunkAPI) => {
    try {
      const selectedAccountId = requireAccountId(accountId);

      return await dashboardAPI.getAccountSummary(selectedAccountId);
    } catch (error) {
      return thunkAPI.rejectWithValue(
        getErrorMessage(error, "Failed to load account summary."),
      );
    }
  },
);

// =====================================================
// STRATEGY PERFORMANCE
// =====================================================

export const fetchStrategyPerformance = createAsyncThunk(
  "dashboard/fetchStrategyPerformance",
  async (accountId, thunkAPI) => {
    try {
      const selectedAccountId = requireAccountId(accountId);

      return await dashboardAPI.getStrategyPerformance(selectedAccountId);
    } catch (error) {
      return thunkAPI.rejectWithValue(
        getErrorMessage(error, "Failed to load strategy performance."),
      );
    }
  },
);

// =====================================================
// RISK PROFILE
// =====================================================

export const fetchRiskProfile = createAsyncThunk(
  "dashboard/fetchRiskProfile",
  async (accountId, thunkAPI) => {
    try {
      const selectedAccountId = requireAccountId(accountId);

      return await dashboardAPI.getRiskProfile(selectedAccountId);
    } catch (error) {
      return thunkAPI.rejectWithValue(
        getErrorMessage(error, "Failed to load risk profile."),
      );
    }
  },
);

// =====================================================
// EFFECTIVE RISK
// =====================================================

export const fetchEffectiveRisk = createAsyncThunk(
  "dashboard/fetchEffectiveRisk",
  async (accountId, thunkAPI) => {
    try {
      const selectedAccountId = requireAccountId(accountId);

      return await dashboardAPI.getEffectiveRisk(selectedAccountId);
    } catch (error) {
      return thunkAPI.rejectWithValue(
        getErrorMessage(error, "Failed to load effective risk."),
      );
    }
  },
);
