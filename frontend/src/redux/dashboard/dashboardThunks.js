import { createAsyncThunk } from "@reduxjs/toolkit";

import dashboardAPI from "./dashboardAPI";

// ==========================================================
// Load Entire Dashboard
// ==========================================================

export const loadDashboard = createAsyncThunk(
  "dashboard/loadDashboard",

  async (_, thunkAPI) => {
    try {
      const [
        accounts,
        activeAccounts,
        positions,
        trades,
        latestTrade,
        symbols,
        strategyRuns,
        latestPerformance,
        brokerAccount,
      ] = await Promise.all([
        dashboardAPI.getAccounts(),
        dashboardAPI.getActiveAccounts(),
        dashboardAPI.getPositions(),
        dashboardAPI.getTrades(),
        dashboardAPI.getLatestTrade(),
        dashboardAPI.getSymbols(),
        dashboardAPI.getStrategyRuns(),
        dashboardAPI.getLatestPerformance(),
        dashboardAPI.getBrokerAccount(),
      ]);

      return {
        accounts,
        activeAccounts,
        positions,
        trades,
        latestTrade,
        symbols,
        strategyRuns,
        latestPerformance,
        brokerAccount,
      };
    } catch (error) {
      return thunkAPI.rejectWithValue(
        error.response?.data?.detail ||
          error.response?.data ||
          error.message ||
          "Failed to load dashboard.",
      );
    }
  },
);

// ==========================================================
// Trading Accounts
// ==========================================================

export const fetchAccounts = createAsyncThunk(
  "dashboard/fetchAccounts",

  async (_, thunkAPI) => {
    try {
      return await dashboardAPI.getAccounts();
    } catch (error) {
      return thunkAPI.rejectWithValue(
        error.response?.data?.detail ||
          error.response?.data ||
          error.message ||
          "Failed to load trading accounts.",
      );
    }
  },
);

// ==========================================================
// Active Accounts
// ==========================================================

export const fetchActiveAccounts = createAsyncThunk(
  "dashboard/fetchActiveAccounts",

  async (_, thunkAPI) => {
    try {
      return await dashboardAPI.getActiveAccounts();
    } catch (error) {
      return thunkAPI.rejectWithValue(
        error.response?.data?.detail ||
          error.response?.data ||
          error.message ||
          "Failed to load active accounts.",
      );
    }
  },
);

// ==========================================================
// Positions
// ==========================================================

export const fetchPositions = createAsyncThunk(
  "dashboard/fetchPositions",

  async (_, thunkAPI) => {
    try {
      return await dashboardAPI.getPositions();
    } catch (error) {
      return thunkAPI.rejectWithValue(
        error.response?.data?.detail ||
          error.response?.data ||
          error.message ||
          "Failed to load positions.",
      );
    }
  },
);

// ==========================================================
// Trades
// ==========================================================

export const fetchTrades = createAsyncThunk(
  "dashboard/fetchTrades",

  async (_, thunkAPI) => {
    try {
      return await dashboardAPI.getTrades();
    } catch (error) {
      return thunkAPI.rejectWithValue(
        error.response?.data?.detail ||
          error.response?.data ||
          error.message ||
          "Failed to load trades.",
      );
    }
  },
);

// ==========================================================
// Latest Trade
// ==========================================================

export const fetchLatestTrade = createAsyncThunk(
  "dashboard/fetchLatestTrade",

  async (_, thunkAPI) => {
    try {
      return await dashboardAPI.getLatestTrade();
    } catch (error) {
      return thunkAPI.rejectWithValue(
        error.response?.data?.detail ||
          error.response?.data ||
          error.message ||
          "Failed to load latest trade.",
      );
    }
  },
);

// ==========================================================
// Symbols
// ==========================================================

export const fetchSymbols = createAsyncThunk(
  "dashboard/fetchSymbols",

  async (_, thunkAPI) => {
    try {
      return await dashboardAPI.getSymbols();
    } catch (error) {
      return thunkAPI.rejectWithValue(
        error.response?.data?.detail ||
          error.response?.data ||
          error.message ||
          "Failed to load symbols.",
      );
    }
  },
);

// ==========================================================
// Strategy Runs
// ==========================================================

export const fetchStrategyRuns = createAsyncThunk(
  "dashboard/fetchStrategyRuns",

  async (_, thunkAPI) => {
    try {
      return await dashboardAPI.getStrategyRuns();
    } catch (error) {
      return thunkAPI.rejectWithValue(
        error.response?.data?.detail ||
          error.response?.data ||
          error.message ||
          "Failed to load strategy runs.",
      );
    }
  },
);

// ==========================================================
// Latest Performance
// ==========================================================

export const fetchLatestPerformance = createAsyncThunk(
  "dashboard/fetchLatestPerformance",

  async (_, thunkAPI) => {
    try {
      return await dashboardAPI.getLatestPerformance();
    } catch (error) {
      return thunkAPI.rejectWithValue(
        error.response?.data?.detail ||
          error.response?.data ||
          error.message ||
          "Failed to load performance.",
      );
    }
  },
);

// ==========================================================
// Broker Account
// ==========================================================

export const fetchBrokerAccount = createAsyncThunk(
  "dashboard/fetchBrokerAccount",

  async (_, thunkAPI) => {
    try {
      return await dashboardAPI.getBrokerAccount();
    } catch (error) {
      return thunkAPI.rejectWithValue(
        error.response?.data?.detail ||
          error.response?.data ||
          error.message ||
          "Failed to load broker account.",
      );
    }
  },
);
