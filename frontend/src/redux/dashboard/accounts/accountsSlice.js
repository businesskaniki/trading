import { createSlice } from "@reduxjs/toolkit";

import {
  fetchAccounts,
  createTradingAccount,
  fetchActiveAccounts,
  fetchDemoAccounts,
  fetchLiveAccounts,
  fetchAccount,
  updateTradingAccount,
  removeTradingAccount,
} from "./accountsThunks";

const initialState = {
  // ----------------------------------------------------------------------
  // Main collection
  // ----------------------------------------------------------------------

  accounts: [],

  // ----------------------------------------------------------------------
  // Currently selected account
  // ----------------------------------------------------------------------

  selectedAccount: null,

  // ----------------------------------------------------------------------
  // Filtered collections
  // ----------------------------------------------------------------------

  activeAccounts: [],

  demoAccounts: [],

  liveAccounts: [],

  // ----------------------------------------------------------------------
  // Loading states
  // ----------------------------------------------------------------------

  loading: false,

  creating: false,

  updating: false,

  deleting: false,

  // ----------------------------------------------------------------------
  // Error
  // ----------------------------------------------------------------------

  error: null,

  // ----------------------------------------------------------------------
  // Operation success
  // ----------------------------------------------------------------------

  createSuccess: false,

  updateSuccess: false,

  deleteSuccess: false,

  // ----------------------------------------------------------------------
  // Last updated
  // ----------------------------------------------------------------------

  lastUpdated: null,
};

const accountsSlice = createSlice({
  name: "accounts",

  initialState,

  reducers: {
    // ------------------------------------------------------------------
    // Clear error
    // ------------------------------------------------------------------

    clearAccountsError: (state) => {
      state.error = null;
    },

    // ------------------------------------------------------------------
    // Clear selected account
    // ------------------------------------------------------------------

    clearSelectedAccount: (state) => {
      state.selectedAccount = null;
    },

    // ------------------------------------------------------------------
    // Reset operation states
    // ------------------------------------------------------------------

    clearAccountOperationState: (state) => {
      state.createSuccess = false;

      state.updateSuccess = false;

      state.deleteSuccess = false;

      state.error = null;
    },
  },

  extraReducers: (builder) => {
    // ==================================================================
    // GET ALL ACCOUNTS
    // ==================================================================

    builder

      .addCase(fetchAccounts.pending, (state) => {
        state.loading = true;

        state.error = null;
      })

      .addCase(fetchAccounts.fulfilled, (state, action) => {
        state.loading = false;

        state.accounts = Array.isArray(action.payload)
          ? action.payload
          : action.payload?.items || [];

        state.lastUpdated = new Date().toISOString();
      })

      .addCase(fetchAccounts.rejected, (state, action) => {
        state.loading = false;

        state.error = action.payload || "Failed to load trading accounts.";
      });

    // ==================================================================
    // CREATE ACCOUNT
    // ==================================================================

    builder

      .addCase(createTradingAccount.pending, (state) => {
        state.creating = true;

        state.createSuccess = false;

        state.error = null;
      })

      .addCase(createTradingAccount.fulfilled, (state, action) => {
        state.creating = false;

        state.createSuccess = true;

        if (action.payload) {
          state.accounts.unshift(action.payload);
        }

        state.lastUpdated = new Date().toISOString();
      })

      .addCase(createTradingAccount.rejected, (state, action) => {
        state.creating = false;

        state.createSuccess = false;

        state.error = action.payload || "Failed to create trading account.";
      });

    // ==================================================================
    // ACTIVE ACCOUNTS
    // ==================================================================

    builder

      .addCase(fetchActiveAccounts.pending, (state) => {
        state.error = null;
      })

      .addCase(fetchActiveAccounts.fulfilled, (state, action) => {
        state.activeAccounts = Array.isArray(action.payload)
          ? action.payload
          : action.payload?.items || [];
      })

      .addCase(fetchActiveAccounts.rejected, (state, action) => {
        state.error = action.payload || "Failed to load active accounts.";
      });

    // ==================================================================
    // DEMO ACCOUNTS
    // ==================================================================

    builder

      .addCase(fetchDemoAccounts.pending, (state) => {
        state.error = null;
      })

      .addCase(fetchDemoAccounts.fulfilled, (state, action) => {
        state.demoAccounts = Array.isArray(action.payload)
          ? action.payload
          : action.payload?.items || [];
      })

      .addCase(fetchDemoAccounts.rejected, (state, action) => {
        state.error = action.payload || "Failed to load demo accounts.";
      });

    // ==================================================================
    // LIVE ACCOUNTS
    // ==================================================================

    builder

      .addCase(fetchLiveAccounts.pending, (state) => {
        state.error = null;
      })

      .addCase(fetchLiveAccounts.fulfilled, (state, action) => {
        state.liveAccounts = Array.isArray(action.payload)
          ? action.payload
          : action.payload?.items || [];
      })

      .addCase(fetchLiveAccounts.rejected, (state, action) => {
        state.error = action.payload || "Failed to load live accounts.";
      });

    // ==================================================================
    // GET SINGLE ACCOUNT
    // ==================================================================

    builder

      .addCase(fetchAccount.pending, (state) => {
        state.loading = true;

        state.error = null;
      })

      .addCase(fetchAccount.fulfilled, (state, action) => {
        state.loading = false;

        state.selectedAccount = action.payload;
      })

      .addCase(fetchAccount.rejected, (state, action) => {
        state.loading = false;

        state.error = action.payload || "Failed to load trading account.";
      });

    // ==================================================================
    // UPDATE ACCOUNT
    // ==================================================================

    builder

      .addCase(updateTradingAccount.pending, (state) => {
        state.updating = true;

        state.updateSuccess = false;

        state.error = null;
      })

      .addCase(updateTradingAccount.fulfilled, (state, action) => {
        state.updating = false;

        state.updateSuccess = true;

        const updatedAccount = action.payload;

        const index = state.accounts.findIndex(
          (account) => account.id === updatedAccount?.id,
        );

        if (index !== -1) {
          state.accounts[index] = updatedAccount;
        }

        if (state.selectedAccount?.id === updatedAccount?.id) {
          state.selectedAccount = updatedAccount;
        }

        state.lastUpdated = new Date().toISOString();
      })

      .addCase(updateTradingAccount.rejected, (state, action) => {
        state.updating = false;

        state.updateSuccess = false;

        state.error = action.payload || "Failed to update trading account.";
      });

    // ==================================================================
    // DELETE ACCOUNT
    // ==================================================================

    builder

      .addCase(removeTradingAccount.pending, (state) => {
        state.deleting = true;

        state.deleteSuccess = false;

        state.error = null;
      })

      .addCase(removeTradingAccount.fulfilled, (state, action) => {
        state.deleting = false;

        state.deleteSuccess = true;

        state.accounts = state.accounts.filter(
          (account) => account.id !== action.payload,
        );

        state.activeAccounts = state.activeAccounts.filter(
          (account) => account.id !== action.payload,
        );

        state.demoAccounts = state.demoAccounts.filter(
          (account) => account.id !== action.payload,
        );

        state.liveAccounts = state.liveAccounts.filter(
          (account) => account.id !== action.payload,
        );

        if (state.selectedAccount?.id === action.payload) {
          state.selectedAccount = null;
        }

        state.lastUpdated = new Date().toISOString();
      })

      .addCase(removeTradingAccount.rejected, (state, action) => {
        state.deleting = false;

        state.deleteSuccess = false;

        state.error = action.payload || "Failed to delete trading account.";
      });
  },
});

export const {
  clearAccountsError,
  clearSelectedAccount,
  clearAccountOperationState,
} = accountsSlice.actions;

export default accountsSlice.reducer;
