import { createAsyncThunk } from "@reduxjs/toolkit";

import riskAPI from "./riskAPI";

const errorMessage = (error, fallback) => {
  const detail = error.response?.data?.detail;
  if (Array.isArray(detail)) return detail.map((item) => item.msg).join(" ");
  return detail || error.message || fallback;
};

export const fetchRiskProfile = createAsyncThunk(
  "risk/fetchProfile",
  async (accountId, thunkAPI) => {
    try { return await riskAPI.getProfile(accountId); }
    catch (error) { return thunkAPI.rejectWithValue(errorMessage(error, "Unable to load risk profile.")); }
  },
);

export const updateRiskProfile = createAsyncThunk(
  "risk/updateProfile",
  async ({ accountId, data }, thunkAPI) => {
    try { return await riskAPI.updateProfile(accountId, data); }
    catch (error) { return thunkAPI.rejectWithValue(errorMessage(error, "Unable to save risk profile.")); }
  },
);