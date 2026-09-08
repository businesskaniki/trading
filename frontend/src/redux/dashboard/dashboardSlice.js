import { createSlice } from "@reduxjs/toolkit";

import {
  loadDashboard,
  fetchAccounts,
  fetchActiveAccounts,
  fetchPositions,
  fetchTrades,
  fetchLatestTrade,
  fetchSymbols,
  fetchStrategyRuns,
  fetchLatestPerformance,
  fetchBrokerAccount,
} from "./dashboardThunks";

const normalizeList = (payload) => {
  if (Array.isArray(payload)) {
    return payload;
  }

  if (Array.isArray(payload?.items)) {
    return payload.items;
  }

  if (payload && typeof payload === "object") {
    return [payload];
  }

  return [];
};

const initialState = {
  loading: false,
  error: null,

  accounts: [],
  activeAccounts: [],
  accountsTotal: 0,

  positions: [],

  trades: [],
  latestTrade: null,

  symbols: [],

  strategyRuns: [],

  latestPerformance: null,

  brokerAccount: null,

  lastUpdated: null,
};

const dashboardSlice = createSlice({
  name: "dashboard",

  initialState,

  reducers: {
    clearDashboardError: (state) => {
      state.error = null;
    },

    resetDashboard: () => initialState,
  },

  extraReducers: (builder) => {
    // ==================================================
    // LOAD ENTIRE DASHBOARD
    // ==================================================

    builder
      .addCase(loadDashboard.pending, (state) => {
        state.loading = true;
        state.error = null;
      })

      .addCase(loadDashboard.fulfilled, (state, action) => {
        state.loading = false;
        state.error = null;

        const payload = action.payload || {};

        // ----------------------------------------------
        // Accounts
        // ----------------------------------------------

        state.accounts = normalizeList(payload.accounts);

        state.accountsTotal = payload.accounts?.total ?? state.accounts.length;

        // ----------------------------------------------
        // Active accounts
        // ----------------------------------------------

        state.activeAccounts = normalizeList(payload.activeAccounts);

        // ----------------------------------------------
        // Positions
        // ----------------------------------------------

        state.positions = normalizeList(payload.positions);

        // ----------------------------------------------
        // Trades
        // ----------------------------------------------

        state.trades = normalizeList(payload.trades);

        // ----------------------------------------------
        // Latest trade
        // ----------------------------------------------

        state.latestTrade = payload.latestTrade ?? null;

        // ----------------------------------------------
        // Symbols
        // ----------------------------------------------

        state.symbols = normalizeList(payload.symbols);

        // ----------------------------------------------
        // Strategy runs
        // ----------------------------------------------

        state.strategyRuns = normalizeList(payload.strategyRuns);

        // ----------------------------------------------
        // Performance
        // ----------------------------------------------

        state.latestPerformance = payload.latestPerformance ?? null;

        // ----------------------------------------------
        // Broker account
        // ----------------------------------------------

        state.brokerAccount = payload.brokerAccount ?? null;

        // ----------------------------------------------
        // Timestamp
        // ----------------------------------------------

        state.lastUpdated = new Date().toISOString();
      })

      .addCase(loadDashboard.rejected, (state, action) => {
        state.loading = false;

        state.error =
          action.payload ||
          action.error?.message ||
          "Failed to load dashboard.";
      });

    // ==================================================
    // ACCOUNTS
    // ==================================================

    builder
      .addCase(fetchAccounts.pending, (state) => {
        state.loading = true;
        state.error = null;
      })

      .addCase(fetchAccounts.fulfilled, (state, action) => {
        state.loading = false;

        const payload = action.payload;

        state.accounts = normalizeList(payload);

        state.accountsTotal = payload?.total ?? state.accounts.length;
      })

      .addCase(fetchAccounts.rejected, (state, action) => {
        state.loading = false;

        state.error =
          action.payload ||
          action.error?.message ||
          "Failed to load trading accounts.";
      });

    // ==================================================
    // ACTIVE ACCOUNTS
    // ==================================================

    builder
      .addCase(fetchActiveAccounts.pending, (state) => {
        state.loading = true;
      })

      .addCase(fetchActiveAccounts.fulfilled, (state, action) => {
        state.loading = false;

        state.activeAccounts = normalizeList(action.payload);
      })

      .addCase(fetchActiveAccounts.rejected, (state, action) => {
        state.loading = false;

        state.error =
          action.payload ||
          action.error?.message ||
          "Failed to load active accounts.";
      });

    // ==================================================
    // POSITIONS
    // ==================================================

    builder
      .addCase(fetchPositions.pending, (state) => {
        state.loading = true;
      })

      .addCase(fetchPositions.fulfilled, (state, action) => {
        state.loading = false;

        state.positions = normalizeList(action.payload);
      })

      .addCase(fetchPositions.rejected, (state, action) => {
        state.loading = false;

        state.error =
          action.payload ||
          action.error?.message ||
          "Failed to load positions.";
      });

    // ==================================================
    // TRADES
    // ==================================================

    builder
      .addCase(fetchTrades.pending, (state) => {
        state.loading = true;
      })

      .addCase(fetchTrades.fulfilled, (state, action) => {
        state.loading = false;

        state.trades = normalizeList(action.payload);
      })

      .addCase(fetchTrades.rejected, (state, action) => {
        state.loading = false;

        state.error =
          action.payload || action.error?.message || "Failed to load trades.";
      });

    // ==================================================
    // LATEST TRADE
    // ==================================================

    builder
      .addCase(fetchLatestTrade.pending, (state) => {
        state.loading = true;
      })

      .addCase(fetchLatestTrade.fulfilled, (state, action) => {
        state.loading = false;
        state.latestTrade = action.payload;
      })

      .addCase(fetchLatestTrade.rejected, (state, action) => {
        state.loading = false;

        state.error =
          action.payload ||
          action.error?.message ||
          "Failed to load latest trade.";
      });

    // ==================================================
    // SYMBOLS
    // ==================================================

    builder
      .addCase(fetchSymbols.pending, (state) => {
        state.loading = true;
      })

      .addCase(fetchSymbols.fulfilled, (state, action) => {
        state.loading = false;

        state.symbols = normalizeList(action.payload);
      })

      .addCase(fetchSymbols.rejected, (state, action) => {
        state.loading = false;

        state.error =
          action.payload || action.error?.message || "Failed to load symbols.";
      });

    // ==================================================
    // STRATEGY RUNS
    // ==================================================

    builder
      .addCase(fetchStrategyRuns.pending, (state) => {
        state.loading = true;
      })

      .addCase(fetchStrategyRuns.fulfilled, (state, action) => {
        state.loading = false;

        state.strategyRuns = normalizeList(action.payload);
      })

      .addCase(fetchStrategyRuns.rejected, (state, action) => {
        state.loading = false;

        state.error =
          action.payload ||
          action.error?.message ||
          "Failed to load strategy runs.";
      });

    // ==================================================
    // PERFORMANCE
    // ==================================================

    builder
      .addCase(fetchLatestPerformance.pending, (state) => {
        state.loading = true;
      })

      .addCase(fetchLatestPerformance.fulfilled, (state, action) => {
        state.loading = false;

        state.latestPerformance = action.payload ?? null;
      })

      .addCase(fetchLatestPerformance.rejected, (state, action) => {
        state.loading = false;

        state.error =
          action.payload ||
          action.error?.message ||
          "Failed to load performance.";
      });

    // ==================================================
    // BROKER ACCOUNT
    // ==================================================

    builder
      .addCase(fetchBrokerAccount.pending, (state) => {
        state.loading = true;
      })

      .addCase(fetchBrokerAccount.fulfilled, (state, action) => {
        state.loading = false;

        state.brokerAccount = action.payload ?? null;
      })

      .addCase(fetchBrokerAccount.rejected, (state, action) => {
        state.loading = false;

        state.error =
          action.payload ||
          action.error?.message ||
          "Failed to load broker account.";
      });
  },
});

export const { clearDashboardError, resetDashboard } = dashboardSlice.actions;

export default dashboardSlice.reducer;
