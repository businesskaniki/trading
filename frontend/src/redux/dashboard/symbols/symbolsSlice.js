import { createSlice } from "@reduxjs/toolkit";

import {
  syncSymbols,
  fetchAccountSymbols,
  fetchTradingUniverse,
  setSymbolSelection,
} from "./symbolsThunks";

const initialState = {
  symbolsByAccount: {},

  selectedSymbols: [],

  selectedAccountId: null,

  loading: false,

  syncing: false,

  selecting: false,

  error: null,

  syncResult: null,
};

const normalizeItems = (payload) => {
  if (Array.isArray(payload)) {
    return payload;
  }

  return payload?.items || [];
};

const symbolsSlice = createSlice({
  name: "symbols",

  initialState,

  reducers: {
    clearSymbolsError: (state) => {
      state.error = null;
    },

    clearSyncResult: (state) => {
      state.syncResult = null;
    },
  },

  extraReducers: (builder) => {
    builder

      // --------------------------------------------------
      // SYNC MT5 SYMBOLS
      // --------------------------------------------------

      .addCase(syncSymbols.pending, (state) => {
        state.syncing = true;
        state.error = null;
        state.syncResult = null;
      })

      .addCase(syncSymbols.fulfilled, (state, action) => {
        state.syncing = false;
        state.syncResult = action.payload;
      })

      .addCase(syncSymbols.rejected, (state, action) => {
        state.syncing = false;
        state.error = action.payload;
      })

      // --------------------------------------------------
      // FETCH ACCOUNT SYMBOLS
      // --------------------------------------------------

      .addCase(fetchAccountSymbols.pending, (state) => {
        state.loading = true;
        state.error = null;
      })

      .addCase(fetchAccountSymbols.fulfilled, (state, action) => {
        state.loading = false;
        const accountId = String(action.meta.arg);
        state.symbolsByAccount[accountId] = normalizeItems(action.payload);
      })

      .addCase(fetchAccountSymbols.rejected, (state, action) => {
        state.loading = false;
        state.error = action.payload;
      })

      // --------------------------------------------------
      // FETCH TRADING UNIVERSE
      // --------------------------------------------------

      .addCase(fetchTradingUniverse.pending, (state) => {
        state.error = null;
      })

      .addCase(fetchTradingUniverse.fulfilled, (state, action) => {
        state.selectedSymbols = normalizeItems(action.payload);
        state.selectedAccountId = String(action.meta.arg);
      })

      .addCase(fetchTradingUniverse.rejected, (state, action) => {
        state.error = action.payload;
      })

      // --------------------------------------------------
      // ENABLE / DISABLE SYMBOL
      // --------------------------------------------------

      .addCase(setSymbolSelection.pending, (state) => {
        state.selecting = true;
        state.error = null;
      })

      .addCase(setSymbolSelection.fulfilled, (state, action) => {
        state.selecting = false;

        const updatedSymbol = action.payload;
        const accountId = String(action.meta.arg.accountId);
        const symbols = state.symbolsByAccount[accountId] || [];

        const index = symbols.findIndex(
          (symbol) => symbol.id === updatedSymbol.id,
        );

        if (index !== -1) {
          symbols[index] = updatedSymbol;
        }

        if (
          updatedSymbol.enabled &&
          state.selectedAccountId === accountId
        ) {
          const alreadySelected = state.selectedSymbols.some(
            (symbol) => symbol.id === updatedSymbol.id,
          );

          if (!alreadySelected) {
            state.selectedSymbols.push(updatedSymbol);
          }
        } else if (state.selectedAccountId === accountId) {
          state.selectedSymbols = state.selectedSymbols.filter(
            (symbol) => symbol.id !== updatedSymbol.id,
          );
        }
      })

      .addCase(setSymbolSelection.rejected, (state, action) => {
        state.selecting = false;
        state.error = action.payload;
      });
  },
});

export const { clearSymbolsError, clearSyncResult } = symbolsSlice.actions;

export default symbolsSlice.reducer;
