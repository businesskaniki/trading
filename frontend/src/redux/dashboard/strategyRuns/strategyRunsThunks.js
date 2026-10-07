import { createAsyncThunk } from "@reduxjs/toolkit";

import strategyRunsAPI from "./strategyRunsAPI";

const getErrorMessage = (error, fallbackMessage) => {
  const detail = error?.response?.data?.detail;

  if (typeof detail === "string" && detail.trim()) {
    return detail;
  }

  if (Array.isArray(detail)) {
    return detail.map((item) => item?.msg || String(item)).join(", ");
  }

  const responseData = error?.response?.data;

  if (
    responseData &&
    typeof responseData === "object" &&
    typeof responseData.message === "string"
  ) {
    return responseData.message;
  }

  if (typeof responseData === "string" && responseData.trim()) {
    return responseData;
  }

  if (error?.message) {
    return error.message;
  }

  return fallbackMessage;
};

const normalizeListResponse = (data) => {
  if (Array.isArray(data)) {
    return data;
  }

  if (Array.isArray(data?.items)) {
    return data.items;
  }

  return [];
};

/* ==========================================================
   FETCH ALL STRATEGY RUNS
   ========================================================== */

export const fetchStrategyRuns = createAsyncThunk(
  "strategyRuns/fetchAll",
  async (_, { rejectWithValue }) => {
    try {
      const data = await strategyRunsAPI.getAll();

      return normalizeListResponse(data);
    } catch (error) {
      return rejectWithValue(
        getErrorMessage(error, "Failed to load strategy runs."),
      );
    }
  },
);

/* ==========================================================
   FETCH ONE STRATEGY RUN
   ========================================================== */

export const fetchStrategyRun = createAsyncThunk(
  "strategyRuns/fetchOne",
  async (strategyRunId, { rejectWithValue }) => {
    try {
      return await strategyRunsAPI.getById(strategyRunId);
    } catch (error) {
      return rejectWithValue(
        getErrorMessage(error, "Failed to load the strategy run."),
      );
    }
  },
);

/* ==========================================================
   UPDATE STRATEGY RUN
   ========================================================== */

export const updateStrategyRun = createAsyncThunk(
  "strategyRuns/update",
  async ({ strategyRunId, payload }, { rejectWithValue }) => {
    try {
      return await strategyRunsAPI.update(strategyRunId, payload);
    } catch (error) {
      return rejectWithValue(
        getErrorMessage(error, "Failed to update the strategy."),
      );
    }
  },
);

/* ==========================================================
   ACTIVATE STRATEGY
   ========================================================== */

export const enableStrategyRun = createAsyncThunk(
  "strategyRuns/enable",
  async (strategyRunId, { rejectWithValue }) => {
    try {
      return await strategyRunsAPI.enable(strategyRunId);
    } catch (error) {
      return rejectWithValue(
        getErrorMessage(error, "Failed to activate the strategy."),
      );
    }
  },
);

/* ==========================================================
   DEACTIVATE STRATEGY
   ========================================================== */

export const disableStrategyRun = createAsyncThunk(
  "strategyRuns/disable",
  async (strategyRunId, { rejectWithValue }) => {
    try {
      return await strategyRunsAPI.disable(strategyRunId);
    } catch (error) {
      return rejectWithValue(
        getErrorMessage(error, "Failed to deactivate the strategy."),
      );
    }
  },
);

/* ==========================================================
   FILTER BY STRATEGY NAME
   ========================================================== */

export const fetchStrategyRunsByName = createAsyncThunk(
  "strategyRuns/fetchByName",
  async (strategyName, { rejectWithValue }) => {
    try {
      const data = await strategyRunsAPI.getByName(strategyName);

      return normalizeListResponse(data);
    } catch (error) {
      return rejectWithValue(
        getErrorMessage(error, "Failed to load strategy runs."),
      );
    }
  },
);

/* ==========================================================
   FILTER BY STATUS
   ========================================================== */

export const fetchStrategyRunsByStatus = createAsyncThunk(
  "strategyRuns/fetchByStatus",
  async (status, { rejectWithValue }) => {
    try {
      const data = await strategyRunsAPI.getByStatus(status);

      return normalizeListResponse(data);
    } catch (error) {
      return rejectWithValue(
        getErrorMessage(error, "Failed to load strategy runs."),
      );
    }
  },
);

/* ==========================================================
   FILTER BY TYPE
   ========================================================== */

export const fetchStrategyRunsByType = createAsyncThunk(
  "strategyRuns/fetchByType",
  async (runType, { rejectWithValue }) => {
    try {
      const data = await strategyRunsAPI.getByType(runType);

      return normalizeListResponse(data);
    } catch (error) {
      return rejectWithValue(
        getErrorMessage(error, "Failed to load strategy runs."),
      );
    }
  },
);
