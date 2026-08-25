import { createAsyncThunk } from "@reduxjs/toolkit";

import authAPI from "./authAPI";

// ==========================================================
// Register
// ==========================================================

export const registerUser = createAsyncThunk(
    "auth/register",

    async (userData, thunkAPI) => {
        try {
            return await authAPI.register(
                userData
            );
        } catch (error) {
            return thunkAPI.rejectWithValue(
                error.response?.data?.detail ||
                error.response?.data ||
                error.message
            );
        }
    }
);

// ==========================================================
// Login
// ==========================================================

export const loginUser = createAsyncThunk(
    "auth/login",

    async (credentials, thunkAPI) => {
        try {
            return await authAPI.login(
                credentials
            );
        } catch (error) {
            return thunkAPI.rejectWithValue(
                error.response?.data?.detail ||
                error.response?.data ||
                error.message
            );
        }
    }
);

// ==========================================================
// Refresh Token
// ==========================================================

export const refreshAccessToken =
    createAsyncThunk(
        "auth/refresh",

        async (_, thunkAPI) => {
            try {
                return await authAPI.refreshToken();
            } catch (error) {
                return thunkAPI.rejectWithValue(
                    error.response?.data?.detail ||
                    error.response?.data ||
                    error.message
                );
            }
        }
    );

// ==========================================================
// Logout
// ==========================================================

export const logoutUser = createAsyncThunk(
    "auth/logout",

    async (_, thunkAPI) => {
        try {
            await authAPI.logout();

            return true;
        } catch (error) {
            return thunkAPI.rejectWithValue(
                error.message
            );
        }
    }
);

// ==========================================================
// Verify Email
// ==========================================================

export const verifyEmail = createAsyncThunk(
    "auth/verifyEmail",

    async (data, thunkAPI) => {
        try {
            return await authAPI.verifyEmail(
                data
            );
        } catch (error) {
            return thunkAPI.rejectWithValue(
                error.response?.data?.detail ||
                error.message
            );
        }
    }
);

// ==========================================================
// Resend OTP
// ==========================================================

export const resendOTP = createAsyncThunk(
    "auth/resendOTP",

    async (email, thunkAPI) => {
        try {
            return await authAPI.resendOTP(
                email
            );
        } catch (error) {
            return thunkAPI.rejectWithValue(
                error.response?.data?.detail ||
                error.message
            );
        }
    }
);

// ==========================================================
// Forgot Password
// ==========================================================

export const forgotPassword =
    createAsyncThunk(
        "auth/forgotPassword",

        async (data, thunkAPI) => {
            try {
                return await authAPI.forgotPassword(
                    data
                );
            } catch (error) {
                return thunkAPI.rejectWithValue(
                    error.response?.data?.detail ||
                    error.message
                );
            }
        }
    );

// ==========================================================
// Reset Password
// ==========================================================

export const resetPassword =
    createAsyncThunk(
        "auth/resetPassword",

        async (data, thunkAPI) => {
            try {
                return await authAPI.resetPassword(
                    data
                );
            } catch (error) {
                return thunkAPI.rejectWithValue(
                    error.response?.data?.detail ||
                    error.response?.data ||
                    error.message
                );
            }
        }
    );