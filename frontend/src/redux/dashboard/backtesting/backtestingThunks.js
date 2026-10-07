import { createAsyncThunk } from "@reduxjs/toolkit";

import backtestingAPI from "./backtestingAPI";

/**
 * Extract the most useful message returned by FastAPI/Axios.
 */
const getErrorMessage = (error, fallbackMessage) => {
  const detail = error?.response?.data?.detail;

  if (Array.isArray(detail)) {
    return detail
      .map((item) => {
        if (typeof item === "string") {
          return item;
        }

        return item?.msg || item?.message || String(item);
      })
      .join(", ");
  }

  if (typeof detail === "string" && detail.trim()) {
    return detail;
  }

  const responseData = error?.response?.data;

  if (
    responseData &&
    typeof responseData === "object" &&
    typeof responseData.message === "string" &&
    responseData.message.trim()
  ) {
    return responseData.message;
  }

  if (
    responseData &&
    typeof responseData === "object" &&
    typeof responseData.error === "string" &&
    responseData.error.trim()
  ) {
    return responseData.error;
  }

  if (typeof responseData === "string" && responseData.trim()) {
    return responseData;
  }

  if (error?.message && error.message.trim()) {
    return error.message;
  }

  return fallbackMessage;
};

/**
 * Validate a backtest ID before making a request.
 */
const normalizeBacktestId = (backtestId) => {
  if (
    backtestId === undefined ||
    backtestId === null ||
    String(backtestId).trim() === ""
  ) {
    throw new Error("A backtest ID is required.");
  }

  return String(backtestId);
};

/**
 * Normalize the collection response.
 *
 * Supported responses:
 *
 * [
 *   {...},
 *   {...}
 * ]
 *
 * {
 *   "items": [...]
 * }
 *
 * {
 *   "backtests": [...]
 * }
 */
const normalizeListResponse = (data) => {
  if (Array.isArray(data)) {
    return data;
  }

  if (Array.isArray(data?.items)) {
    return data.items;
  }

  if (Array.isArray(data?.backtests)) {
    return data.backtests;
  }

  return [];
};

/**
 * Normalize an individual backtest response.
 */
const normalizeBacktestResponse = (data) => {
  if (!data) {
    return null;
  }

  if (data?.backtest && typeof data.backtest === "object") {
    return data.backtest;
  }

  return data;
};

/* -------------------------------------------------------------------------- */
/* Fetch all backtests                                                        */
/* -------------------------------------------------------------------------- */

export const fetchBacktests = createAsyncThunk(
  "backtesting/fetchAll",

  async (_, { rejectWithValue }) => {
    try {
      const data = await backtestingAPI.getAll();

      return normalizeListResponse(data);
    } catch (error) {
      return rejectWithValue(
        getErrorMessage(error, "Failed to load backtests."),
      );
    }
  },
);

/* -------------------------------------------------------------------------- */
/* Fetch one backtest                                                         */
/* -------------------------------------------------------------------------- */

export const fetchBacktest = createAsyncThunk(
  "backtesting/fetchOne",

  async (backtestId, { rejectWithValue }) => {
    try {
      const normalizedId = normalizeBacktestId(backtestId);

      const data = await backtestingAPI.getById(normalizedId);

      const backtest = normalizeBacktestResponse(data);

      if (!backtest) {
        throw new Error("The backend returned an empty backtest.");
      }

      return backtest;
    } catch (error) {
      return rejectWithValue(
        getErrorMessage(error, "Failed to load the backtest."),
      );
    }
  },
);

/* -------------------------------------------------------------------------- */
/* Create backtest                                                            */
/* -------------------------------------------------------------------------- */

export const createBacktest = createAsyncThunk(
  "backtesting/create",

  async (payload, { rejectWithValue }) => {
    try {
      if (!payload || typeof payload !== "object") {
        throw new Error("A backtest configuration is required.");
      }

      const data = await backtestingAPI.create(payload);

      const backtest = normalizeBacktestResponse(data);

      if (!backtest) {
        throw new Error("The backend did not return the created backtest.");
      }

      return backtest;
    } catch (error) {
      return rejectWithValue(
        getErrorMessage(error, "Failed to create the backtest."),
      );
    }
  },
);

/* -------------------------------------------------------------------------- */
/* Start backtest                                                             */
/* -------------------------------------------------------------------------- */

export const startBacktest = createAsyncThunk(
  "backtesting/start",

  async (backtestId, { rejectWithValue }) => {
    try {
      const normalizedId = normalizeBacktestId(backtestId);

      const data = await backtestingAPI.start(normalizedId);

      const backtest = normalizeBacktestResponse(data);

      if (!backtest) {
        throw new Error("The backend did not return the started backtest.");
      }

      return backtest;
    } catch (error) {
      return rejectWithValue(
        getErrorMessage(error, "Failed to start the backtest."),
      );
    }
  },
);

/* -------------------------------------------------------------------------- */
/* Stop backtest                                                              */
/* -------------------------------------------------------------------------- */

export const stopBacktest = createAsyncThunk(
  "backtesting/stop",

  async (backtestId, { rejectWithValue }) => {
    try {
      const normalizedId = normalizeBacktestId(backtestId);

      const data = await backtestingAPI.stop(normalizedId);

      const backtest = normalizeBacktestResponse(data);

      if (!backtest) {
        throw new Error("The backend did not return the stopped backtest.");
      }

      return backtest;
    } catch (error) {
      return rejectWithValue(
        getErrorMessage(error, "Failed to stop the backtest."),
      );
    }
  },
);

/* -------------------------------------------------------------------------- */
/* Delete backtest                                                            */
/* -------------------------------------------------------------------------- */

export const deleteBacktest = createAsyncThunk(
  "backtesting/delete",

  async (backtestId, { rejectWithValue }) => {
    try {
      const normalizedId = normalizeBacktestId(backtestId);

      await backtestingAPI.remove(normalizedId);

      /*
       * Return the exact ID that was sent to the backend.
       *
       * The DELETE endpoint returns 204, so there is no response body
       * from which to obtain the deleted ID.
       */
      return normalizedId;
    } catch (error) {
      return rejectWithValue(
        getErrorMessage(error, "Failed to delete the backtest."),
      );
    }
  },
);
