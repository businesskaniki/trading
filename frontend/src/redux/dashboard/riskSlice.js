import { createSlice } from "@reduxjs/toolkit";

import { fetchRiskProfile, updateRiskProfile } from "./riskThunks";

const riskSlice = createSlice({
  name: "risk",
  initialState: { profile: null, loading: false, saving: false, error: null, saved: false },
  reducers: { clearRiskState: (state) => { state.error = null; state.saved = false; } },
  extraReducers: (builder) => {
    builder
      .addCase(fetchRiskProfile.pending, (state) => {
        state.loading = true;
        state.error = null;
        state.profile = null;
        state.saved = false;
      })
      .addCase(fetchRiskProfile.fulfilled, (state, action) => {
        state.loading = false;
        state.profile = action.payload;
      })
      .addCase(fetchRiskProfile.rejected, (state, action) => {
        state.loading = false;
        state.profile = null;
        state.error = action.payload;
      })
      .addCase(updateRiskProfile.pending, (state) => { state.saving = true; state.saved = false; state.error = null; })
      .addCase(updateRiskProfile.fulfilled, (state, action) => { state.saving = false; state.saved = true; state.profile = action.payload; })
      .addCase(updateRiskProfile.rejected, (state, action) => { state.saving = false; state.error = action.payload; });
  },
});

export const { clearRiskState } = riskSlice.actions;
export default riskSlice.reducer;