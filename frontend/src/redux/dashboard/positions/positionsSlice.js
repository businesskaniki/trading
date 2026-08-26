import { createSlice } from "@reduxjs/toolkit";
import {
  fetchPositions,
  syncPositions,
} from "./positionsThunks";

const initialState = {
  positions: [],
  loading: false,
  syncing: false,
  error: null,
};

const positionsSlice = createSlice({
  name: "positions",
  initialState,
  reducers: {
    clearPositionsError: (state) => {
      state.error = null;
    },
  },
  extraReducers: (builder) => {
    builder
      .addCase(fetchPositions.pending, (state) => {
        state.loading = true;
        state.error = null;
      })
      .addCase(fetchPositions.fulfilled, (state, action) => {
        state.loading = false;
        state.positions = Array.isArray(action.payload)
          ? action.payload
          : action.payload?.items || [];
      })
      .addCase(fetchPositions.rejected, (state, action) => {
        state.loading = false;
        state.error = action.payload || "Failed to load positions.";
      })
      .addCase(syncPositions.pending, (state) => {
        state.syncing = true;
        state.error = null;
      })
      .addCase(syncPositions.fulfilled, (state) => {
        state.syncing = false;
      })
      .addCase(syncPositions.rejected, (state, action) => {
        state.syncing = false;
        state.error = action.payload || "Failed to synchronize positions.";
      });
  },
});

export const { clearPositionsError } = positionsSlice.actions;
export default positionsSlice.reducer;