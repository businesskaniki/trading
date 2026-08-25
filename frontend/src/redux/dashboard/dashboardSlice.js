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

const initialState = {
  // ======================================================
  // Dashboard
  // ======================================================

  loading: false,
  error: null,

  // ======================================================
  // Trading Accounts
  // ======================================================

  accounts: [],
  activeAccounts: [],
  accountsTotal: 0,

  // ======================================================
  // Positions
  // ======================================================

  positions: [],

  // ======================================================
  // Trades
  // ======================================================

  trades: [],
  latestTrade: null,

  // ======================================================
  // Symbols
  // ======================================================

  symbols: [],

  // ======================================================
  // Strategy Runs
  // ======================================================

  strategyRuns: [],

  // ======================================================
  // Performance
  // ======================================================

  latestPerformance: null,

  // ======================================================
  // Broker
  // ======================================================

  brokerAccount: null,

  // ======================================================
  // Last successful dashboard refresh
  // ======================================================

  lastUpdated: null,
};

const dashboardSlice = createSlice({
  name: "dashboard",

  initialState,

  reducers: {
    clearDashboardError: (state) => {
      state.error = null;
    },

    resetDashboard: () => {
      return initialState;
    },
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

      .addCase(loadDashboard.fulfilled, (state) => {
        state.loading = false;
        state.error = null;
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
      })

      .addCase(fetchAccounts.fulfilled, (state, action) => {
        state.loading = false;

        const payload = action.payload;

        if (Array.isArray(payload)) {
          state.accounts = payload;
          state.accountsTotal = payload.length;
        } else {
          state.accounts = payload?.items || [];
          state.accountsTotal = payload?.total ?? payload?.items?.length ?? 0;
        }
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

        const payload = action.payload;

        if (Array.isArray(payload)) {
          state.activeAccounts = payload;
        } else {
          state.activeAccounts = payload?.items || [];
        }
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

        const payload = action.payload;

        state.positions = Array.isArray(payload)
          ? payload
          : payload?.items || [];
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

        const payload = action.payload;

        state.trades = Array.isArray(payload) ? payload : payload?.items || [];
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

        const payload = action.payload;

        state.symbols = Array.isArray(payload) ? payload : payload?.items || [];
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

        const payload = action.payload;

        state.strategyRuns = Array.isArray(payload)
          ? payload
          : payload?.items || [];
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
        state.latestPerformance = action.payload;
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
        state.brokerAccount = action.payload;
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
