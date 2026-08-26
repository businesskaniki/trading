import { createAsyncThunk } from "@reduxjs/toolkit";

import botAPI from "./botAPI";

const errorMessage = (error, fallback) =>
  error.response?.data?.detail || error.message || fallback;

export const fetchBotStatus = createAsyncThunk(
  "bot/fetchStatus",
  async (_, thunkAPI) => {
    try {
      return await botAPI.getStatus();
    } catch (error) {
      return thunkAPI.rejectWithValue(errorMessage(error, "Unable to read bot status."));
    }
  },
);

export const startBot = createAsyncThunk(
  "bot/start",
  async (payload, thunkAPI) => {
    try {
      return await botAPI.start(payload);
    } catch (error) {
      return thunkAPI.rejectWithValue(errorMessage(error, "Unable to start bot."));
    }
  },
);

export const stopBot = createAsyncThunk(
  "bot/stop",
  async (_, thunkAPI) => {
    try {
      return await botAPI.stop();
    } catch (error) {
      return thunkAPI.rejectWithValue(errorMessage(error, "Unable to stop bot."));
    }
  },
);