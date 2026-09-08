import { createSlice } from "@reduxjs/toolkit";

import {
  fetchAccounts,
  createTradingAccount,
  fetchActiveAccounts,
  fetchDemoAccounts,
  fetchLiveAccounts,
  fetchAccount,
  updateTradingAccount,
  connectTradingAccount,
  disconnectTradingAccount,
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

  connecting: false,

  disconnecting: false,

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

  connectSuccess: false,

  disconnectSuccess: false,

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
    // Select trading account
    // ------------------------------------------------------------------

    selectAccount: (state, action) => {
      const account = state.accounts.find((item) => item.id === action.payload);

      state.selectedAccount = account || null;
    },

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

      state.connectSuccess = false;

      state.disconnectSuccess = false;

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

        // --------------------------------------------------------------
        // Preserve the current selection when possible.
        //
        // If there is no selected account, automatically select
        // the first available trading account.
        // --------------------------------------------------------------

        if (
          !state.selectedAccount ||
          !state.accounts.some(
            (account) => account.id === state.selectedAccount.id,
          )
        ) {
          state.selectedAccount = state.accounts[0] || null;
        }

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

          // ----------------------------------------------------------
          // Automatically select the newly created account.
          // ----------------------------------------------------------

          state.selectedAccount = action.payload;
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

        // --------------------------------------------------------------
        // Keep the account in the main collection synchronized.
        // --------------------------------------------------------------

        if (action.payload) {
          const index = state.accounts.findIndex(
            (account) => account.id === action.payload.id,
          );

          if (index !== -1) {
            state.accounts[index] = action.payload;
          }
        }
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
    // CONNECT ACCOUNT
    // ==================================================================

    builder

      .addCase(connectTradingAccount.pending, (state) => {
        state.connecting = true;

        state.connectSuccess = false;

        state.error = null;
      })

      .addCase(connectTradingAccount.fulfilled, (state, action) => {
        state.connecting = false;

        state.connectSuccess = true;

        const connectedAccount = action.payload;

        const index = state.accounts.findIndex(
          (account) => account.id === connectedAccount?.id,
        );

        if (index !== -1) {
          state.accounts[index] = connectedAccount;
        }

        if (state.selectedAccount?.id === connectedAccount?.id) {
          state.selectedAccount = connectedAccount;
        }

        state.lastUpdated = new Date().toISOString();
      })

      .addCase(connectTradingAccount.rejected, (state, action) => {
        state.connecting = false;

        state.connectSuccess = false;

        state.error = action.payload || "Failed to connect trading account.";
      });

    // ==================================================================
    // DISCONNECT ACCOUNT
    // ==================================================================

    builder

      .addCase(disconnectTradingAccount.pending, (state) => {
        state.disconnecting = true;

        state.disconnectSuccess = false;

        state.error = null;
      })

      .addCase(disconnectTradingAccount.fulfilled, (state, action) => {
        state.disconnecting = false;

        state.disconnectSuccess = true;

        const disconnectedAccount = action.payload;

        const index = state.accounts.findIndex(
          (account) => account.id === disconnectedAccount?.id,
        );

        if (index !== -1) {
          state.accounts[index] = disconnectedAccount;
        }

        if (state.selectedAccount?.id === disconnectedAccount?.id) {
          state.selectedAccount = disconnectedAccount;
        }

        state.lastUpdated = new Date().toISOString();
      })

      .addCase(disconnectTradingAccount.rejected, (state, action) => {
        state.disconnecting = false;

        state.disconnectSuccess = false;

        state.error = action.payload || "Failed to disconnect trading account.";
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

        const deletedAccountId = action.payload;

        state.accounts = state.accounts.filter(
          (account) => account.id !== deletedAccountId,
        );

        state.activeAccounts = state.activeAccounts.filter(
          (account) => account.id !== deletedAccountId,
        );

        state.demoAccounts = state.demoAccounts.filter(
          (account) => account.id !== deletedAccountId,
        );

        state.liveAccounts = state.liveAccounts.filter(
          (account) => account.id !== deletedAccountId,
        );

        // ------------------------------------------------------------
        // If the deleted account was selected, automatically switch
        // to another available account.
        // ------------------------------------------------------------

        if (state.selectedAccount?.id === deletedAccountId) {
          state.selectedAccount = state.accounts[0] || null;
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
  selectAccount,
  clearAccountsError,
  clearSelectedAccount,
  clearAccountOperationState,
} = accountsSlice.actions;

export default accountsSlice.reducer;
