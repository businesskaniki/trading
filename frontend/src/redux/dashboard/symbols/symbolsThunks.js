import { createAsyncThunk } from "@reduxjs/toolkit";
import symbolsAPI from "./symbolsAPI";

const getErrorMessage = (error, fallback) => {
  const detail = error.response?.data?.detail;

  if (Array.isArray(detail)) {
    return detail.map((item) => item.msg || "Invalid value.").join(" ");
  }

  if (typeof detail === "string") return detail;
  return error.message || fallback;
};

export const fetchSymbols = createAsyncThunk(
  "symbols/fetchSymbols",
  async (_, { rejectWithValue }) => {
    try {
      return await symbolsAPI.getSymbols();
    } catch (error) {
      return rejectWithValue(getErrorMessage(error, "Failed to load symbols."));
    }
  },
);

export const createSymbol = createAsyncThunk(
  "symbols/createSymbol",
  async (symbolData, { rejectWithValue }) => {
    try {
      return await symbolsAPI.createSymbol(symbolData);
    } catch (error) {
      return rejectWithValue(getErrorMessage(error, "Failed to create symbol."));
    }
  },
);

export const updateSymbol = createAsyncThunk(
  "symbols/updateSymbol",
  async ({ symbolId, symbolData }, { rejectWithValue }) => {
    try {
      return await symbolsAPI.updateSymbol(symbolId, symbolData);
    } catch (error) {
      return rejectWithValue(getErrorMessage(error, "Failed to update symbol."));
    }
  },
);

export const removeSymbol = createAsyncThunk(
  "symbols/removeSymbol",
  async (symbolId, { rejectWithValue }) => {
    try {
      return await symbolsAPI.deleteSymbol(symbolId);
    } catch (error) {
      return rejectWithValue(getErrorMessage(error, "Failed to delete symbol."));
    }
  },
);
