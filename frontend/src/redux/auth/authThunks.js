import { createAsyncThunk } from "@reduxjs/toolkit";
import authAPI from "./authAPI";

export const registerUser = createAsyncThunk(
  "auth/register",
  async (userData, thunkAPI) => {
    try {
      return await authAPI.register(userData);
    } catch (error) {
      return thunkAPI.rejectWithValue(
        error.response?.data?.detail || error.response?.data || error.message,
      );
    }
  },
);

export const loginUser = createAsyncThunk(
  "auth/login",
  async (credentials, thunkAPI) => {
    try {
      return await authAPI.login(credentials);
    } catch (error) {
      return thunkAPI.rejectWithValue(
        error.response?.data?.detail || error.response?.data || error.message,
      );
    }
  },
);

export const getCurrentUser = createAsyncThunk(
  "auth/me",
  async (_, thunkAPI) => {
    try {
      return await authAPI.getCurrentUser();
    } catch (error) {
      return thunkAPI.rejectWithValue(
        error.response?.data?.detail || error.message,
      );
    }
  },
);

export const logoutUser = createAsyncThunk(
  "auth/logout",
  async (_, thunkAPI) => {
    try {
      await authAPI.logout();
    } catch (error) {
      return thunkAPI.rejectWithValue(error.message);
    }
  },
);

export const verifyEmail = createAsyncThunk(
  "auth/verifyEmail",
  async (data, thunkAPI) => {
    try {
      return await authAPI.verifyEmail(data);
    } catch (error) {
      return thunkAPI.rejectWithValue(
        error.response?.data?.detail || error.message,
      );
    }
  },
);

export const resendOTP = createAsyncThunk(
  "auth/resendOTP",
  async (email, thunkAPI) => {
    try {
      return await authAPI.resendOTP(email);
    } catch (error) {
      return thunkAPI.rejectWithValue(
        error.response?.data?.detail || error.message,
      );
    }
  },
);

export const forgotPassword = createAsyncThunk(
    "auth/forgotPassword",
    async (data, thunkAPI) => {
        try {
            return await authAPI.forgotPassword(data);
        } catch (error) {
            return thunkAPI.rejectWithValue(
                error.response?.data?.detail ||
                error.message
            );
        }
    }
);

export const resetPassword = createAsyncThunk(
    "auth/resetPassword",
    async (data, thunkAPI) => {
        try {
            return await authAPI.resetPassword(data);
        } catch (error) {
            return thunkAPI.rejectWithValue(
                error.response?.data?.detail ||
                error.response?.data ||
                error.message
            );
        }
    }
);