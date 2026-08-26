import { createSlice } from "@reduxjs/toolkit";
import { fetchSymbols, createSymbol, updateSymbol, removeSymbol } from "./symbolsThunks";

const initialState = {
  symbols: [],
  loading: false,
  saving: false,
  deleting: false,
  error: null,
};

const normalize = (payload) =>
  Array.isArray(payload) ? payload : payload?.items || [];

const symbolsSlice = createSlice({
  name: "symbols",
  initialState,
  reducers: {
    clearSymbolsError: (state) => { state.error = null; },
  },
  extraReducers: (builder) => {
    builder
      .addCase(fetchSymbols.pending, (state) => { state.loading = true; state.error = null; })
      .addCase(fetchSymbols.fulfilled, (state, action) => { state.loading = false; state.symbols = normalize(action.payload); })
      .addCase(fetchSymbols.rejected, (state, action) => { state.loading = false; state.error = action.payload; })
      .addCase(createSymbol.pending, (state) => { state.saving = true; state.error = null; })
      .addCase(createSymbol.fulfilled, (state, action) => { state.saving = false; state.symbols.unshift(action.payload); })
      .addCase(createSymbol.rejected, (state, action) => { state.saving = false; state.error = action.payload; })
      .addCase(updateSymbol.pending, (state) => { state.saving = true; state.error = null; })
      .addCase(updateSymbol.fulfilled, (state, action) => {
        state.saving = false;
        const index = state.symbols.findIndex((symbol) => symbol.id === action.payload?.id);
        if (index !== -1) state.symbols[index] = action.payload;
      })
      .addCase(updateSymbol.rejected, (state, action) => { state.saving = false; state.error = action.payload; })
      .addCase(removeSymbol.pending, (state) => { state.deleting = true; state.error = null; })
      .addCase(removeSymbol.fulfilled, (state, action) => {
        state.deleting = false;
        state.symbols = state.symbols.filter((symbol) => symbol.id !== action.payload);
      })
      .addCase(removeSymbol.rejected, (state, action) => { state.deleting = false; state.error = action.payload; });
  },
});

export const { clearSymbolsError } = symbolsSlice.actions;
export default symbolsSlice.reducer;
