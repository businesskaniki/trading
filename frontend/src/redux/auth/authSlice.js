import { createSlice } from "@reduxjs/toolkit";
import {
  registerUser,
  loginUser,
  logoutUser,
  getCurrentUser,
  verifyEmail,
  resendOTP,
  forgotPassword,
  resetPassword,
} from "./authThunks";
console.log("Auth slice loaded");
const initialState = {
  user: null,

  accessToken: localStorage.getItem("access_token"),

  isAuthenticated: !!localStorage.getItem("access_token"),

  loading: false,

  success: false,

  error: null,
  pendingVerificationEmail: null,
};

const authSlice = createSlice({
  name: "auth",

  initialState,

  reducers: {
    clearError(state) {
      state.error = null;
    },

    resetStatus(state) {
      state.loading = false;
      state.success = false;
      state.error = null;
    },
  },

  extraReducers: (builder) => {
    builder

      // Register

      .addCase(registerUser.pending, (state) => {
        state.loading = true;
        state.error = null;
      })

      .addCase(registerUser.fulfilled, (state, action) => {
        state.loading = false;
        state.success = true;
        state.pendingVerificationEmail = action.meta.arg.email;
      })

      .addCase(registerUser.rejected, (state, action) => {
        state.loading = false;
        state.error = action.payload;
        console.log(action);
      })

      // Login

      .addCase(loginUser.pending, (state) => {
        state.loading = true;
        state.error = null;
      })

      .addCase(loginUser.fulfilled, (state, action) => {
        state.loading = false;
        state.success = true;

        state.isAuthenticated = true;

        state.accessToken = action.payload.access_token;

        state.user = action.payload.user || null;
      })

      .addCase(loginUser.rejected, (state, action) => {
        state.loading = false;
        state.error = action.payload;

        state.isAuthenticated = false;
      })

      // Current User

      .addCase(getCurrentUser.pending, (state) => {
        state.loading = true;
      })

      .addCase(getCurrentUser.fulfilled, (state, action) => {
        state.loading = false;

        state.user = action.payload;

        state.isAuthenticated = true;
      })

      .addCase(getCurrentUser.rejected, (state) => {
        state.loading = false;

        state.user = null;

        state.isAuthenticated = false;
      })

      // Verify Email

      .addCase(verifyEmail.pending, (state) => {
        state.loading = true;
        state.error = null;
      })

      .addCase(verifyEmail.fulfilled, (state) => {
        state.loading = false;
        state.success = true;
        state.pendingVerificationEmail = null;
      })

      .addCase(verifyEmail.rejected, (state, action) => {
        state.loading = false;
        state.error = action.payload;
      })

      .addCase(forgotPassword.pending, (state) => {
        state.loading = true;
        state.error = null;
      })

      .addCase(forgotPassword.fulfilled, (state) => {
        state.loading = false;
      })

      .addCase(forgotPassword.rejected, (state, action) => {
        state.loading = false;
        state.error = action.payload;
      })

      // Reset Password

      .addCase(resetPassword.pending, (state) => {
        state.loading = true;
        state.error = null;
      })

      .addCase(resetPassword.fulfilled, (state) => {
        state.loading = false;
        state.success = true;
      })

      .addCase(resetPassword.rejected, (state, action) => {
        state.loading = false;
        state.error = action.payload;
      })

      // Resend OTP

      .addCase(resendOTP.pending, (state) => {
        state.loading = true;
        state.error = null;
      })

      .addCase(resendOTP.fulfilled, (state) => {
        state.loading = false;
      })

      .addCase(resendOTP.rejected, (state, action) => {
        state.loading = false;
        state.error = action.payload;
      })

      // Logout

      .addCase(logoutUser.fulfilled, (state) => {
        state.user = null;

        state.accessToken = null;

        state.isAuthenticated = false;

        state.loading = false;

        state.success = false;

        state.error = null;
      });
  },
});

export const { clearError, resetStatus } = authSlice.actions;

export default authSlice.reducer;
