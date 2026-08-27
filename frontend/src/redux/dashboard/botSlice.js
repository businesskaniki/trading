import { createSlice } from "@reduxjs/toolkit";

import { fetchBotStatus, startBot, stopBot } from "./botThunks";

const initialState = {
  status: null,
  loading: false,
  error: null,
};

const botSlice = createSlice({
  name: "bot",
  initialState,
  reducers: {},
  extraReducers: (builder) => {
    builder
      .addCase(fetchBotStatus.pending, (state) => {
        state.loading = true;
        state.error = null;
      })
      .addCase(fetchBotStatus.fulfilled, (state, action) => {
        state.loading = false;
        state.status = action.payload;
      })
      .addCase(fetchBotStatus.rejected, (state, action) => {
        state.loading = false;
        state.error = action.payload;
      })
      .addCase(startBot.pending, (state) => {
        state.loading = true;
        state.error = null;
      })
      .addCase(startBot.fulfilled, (state, action) => {
        state.loading = false;
        state.status = action.payload;
      })
      .addCase(startBot.rejected, (state, action) => {
        state.loading = false;
        state.error = action.payload;
      })
      .addCase(stopBot.pending, (state) => {
        state.loading = true;
        state.error = null;
      })
      .addCase(stopBot.fulfilled, (state, action) => {
        state.loading = false;
        state.status = action.payload;
      })
      .addCase(stopBot.rejected, (state, action) => {
        state.loading = false;
        state.error = action.payload;
      });
  },
});

export default botSlice.reducer;