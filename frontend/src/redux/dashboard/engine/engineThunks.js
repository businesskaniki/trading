import { createAsyncThunk } from "@reduxjs/toolkit";

import engineAPI from "./engineAPI";

// =====================================================
// GET ENGINE STATUS
// =====================================================

export const fetchEngineStatus = createAsyncThunk(
  "engine/fetchStatus",
  async (_, { rejectWithValue }) => {
    try {
      return await engineAPI.getStatus();
    } catch (error) {
      return rejectWithValue(
        error.response?.data?.detail ||
          error.message ||
          "Unable to fetch engine status.",
      );
    }
  },
);

// =====================================================
// START ENGINE
// =====================================================
// Requires the trading account ID.

export const startEngine = createAsyncThunk(
  "engine/start",
  async (accountId, { rejectWithValue }) => {
    try {
      if (!accountId) {
        return rejectWithValue(
          "A trading account must be selected before starting the engine.",
        );
      }

      return await engineAPI.start(accountId);
    } catch (error) {
      return rejectWithValue(
        error.response?.data?.detail ||
          error.message ||
          "Unable to start the trading engine.",
      );
    }
  },
);

// =====================================================
// STOP ENGINE
// =====================================================

export const stopEngine = createAsyncThunk(
  "engine/stop",
  async (_, { rejectWithValue }) => {
    try {
      return await engineAPI.stop();
    } catch (error) {
      return rejectWithValue(
        error.response?.data?.detail ||
          error.message ||
          "Unable to stop the trading engine.",
      );
    }
  },
);

// =====================================================
// PAUSE ENGINE
// =====================================================

export const pauseEngine = createAsyncThunk(
  "engine/pause",
  async (_, { rejectWithValue }) => {
    try {
      return await engineAPI.pause();
    } catch (error) {
      return rejectWithValue(
        error.response?.data?.detail ||
          error.message ||
          "Unable to pause the trading engine.",
      );
    }
  },
);

// =====================================================
// RESUME / UNPAUSE ENGINE
// =====================================================

export const resumeEngine = createAsyncThunk(
  "engine/resume",
  async (_, { rejectWithValue }) => {
    try {
      return await engineAPI.resume();
    } catch (error) {
      return rejectWithValue(
        error.response?.data?.detail ||
          error.message ||
          "Unable to resume the trading engine.",
      );
    }
  },
);
