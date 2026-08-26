import { createAsyncThunk } from "@reduxjs/toolkit";

import accountsAPI from "./accountsAPI";

// =====================================================
// ERROR HANDLER
// =====================================================

const getErrorMessage = (error, fallback) => {
  const responseData = error.response?.data;

  // -----------------------------------------------------
  // FastAPI validation errors
  // -----------------------------------------------------

  if (responseData?.detail && Array.isArray(responseData.detail)) {
    return responseData.detail
      .map((item) => {
        const location = Array.isArray(item.loc)
          ? item.loc.filter((part) => part !== "body").join(".")
          : "";

        const message = item.msg || "Invalid value.";

        return location ? `${location}: ${message}` : message;
      })
      .join(" ");
  }

  // -----------------------------------------------------
  // FastAPI normal error
  // -----------------------------------------------------

  if (responseData?.detail) {
    if (typeof responseData.detail === "string") {
      return responseData.detail;
    }

    return JSON.stringify(responseData.detail);
  }

  // -----------------------------------------------------
  // Axios error
  // -----------------------------------------------------

  if (error.message) {
    return error.message;
  }

  return fallback;
};

// =====================================================
// GET ALL ACCOUNTS
// =====================================================

export const fetchAccounts = createAsyncThunk(
  "accounts/fetchAccounts",

  async (_, { rejectWithValue }) => {
    try {
      return await accountsAPI.getAccounts();
    } catch (error) {
      return rejectWithValue(
        getErrorMessage(error, "Failed to load trading accounts."),
      );
    }
  },
);

// =====================================================
// CREATE ACCOUNT
// =====================================================

export const createTradingAccount = createAsyncThunk(
  "accounts/createTradingAccount",

  async (accountData, { rejectWithValue }) => {
    try {
      return await accountsAPI.createAccount(accountData);
    } catch (error) {
      return rejectWithValue(
        getErrorMessage(error, "Failed to create trading account."),
      );
    }
  },
);

// =====================================================
// GET ACTIVE ACCOUNTS
// =====================================================

export const fetchActiveAccounts = createAsyncThunk(
  "accounts/fetchActiveAccounts",

  async (_, { rejectWithValue }) => {
    try {
      return await accountsAPI.getActiveAccounts();
    } catch (error) {
      return rejectWithValue(
        getErrorMessage(error, "Failed to load active accounts."),
      );
    }
  },
);

// =====================================================
// GET DEMO ACCOUNTS
// =====================================================

export const fetchDemoAccounts = createAsyncThunk(
  "accounts/fetchDemoAccounts",

  async (_, { rejectWithValue }) => {
    try {
      return await accountsAPI.getDemoAccounts();
    } catch (error) {
      return rejectWithValue(
        getErrorMessage(error, "Failed to load demo accounts."),
      );
    }
  },
);

// =====================================================
// GET LIVE ACCOUNTS
// =====================================================

export const fetchLiveAccounts = createAsyncThunk(
  "accounts/fetchLiveAccounts",

  async (_, { rejectWithValue }) => {
    try {
      return await accountsAPI.getLiveAccounts();
    } catch (error) {
      return rejectWithValue(
        getErrorMessage(error, "Failed to load live accounts."),
      );
    }
  },
);

// =====================================================
// GET SINGLE ACCOUNT
// =====================================================

export const fetchAccount = createAsyncThunk(
  "accounts/fetchAccount",

  async (accountId, { rejectWithValue }) => {
    try {
      return await accountsAPI.getAccount(accountId);
    } catch (error) {
      return rejectWithValue(
        getErrorMessage(error, "Failed to load trading account."),
      );
    }
  },
);

// =====================================================
// UPDATE ACCOUNT
// =====================================================

export const updateTradingAccount = createAsyncThunk(
  "accounts/updateTradingAccount",

  async ({ accountId, accountData }, { rejectWithValue }) => {
    try {
      return await accountsAPI.updateAccount(accountId, accountData);
    } catch (error) {
      return rejectWithValue(
        getErrorMessage(error, "Failed to update trading account."),
      );
    }
  },
);

// =====================================================
// DELETE ACCOUNT
// =====================================================

export const removeTradingAccount = createAsyncThunk(
  "accounts/removeTradingAccount",

  async (accountId, { rejectWithValue }) => {
    try {
      await accountsAPI.deleteAccount(accountId);

      // Return the deleted ID so the
      // accountsSlice can remove it
      // from the Redux state.

      return accountId;
    } catch (error) {
      return rejectWithValue(
        getErrorMessage(error, "Failed to delete trading account."),
      );
    }
  },
);
