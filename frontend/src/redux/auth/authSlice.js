import { createSlice } from "@reduxjs/toolkit";

import {
  registerUser,
  loginUser,
  logoutUser,
  refreshAccessToken,
  verifyEmail,
  resendOTP,
  forgotPassword,
  resetPassword,
} from "./authThunks";

// ==========================================================
// Load persisted user
//
// The access token is intentionally NOT persisted.
// It is restored through /auth/refresh using the
// HttpOnly refresh cookie during application startup.
// ==========================================================

const storedUser = localStorage.getItem("user");

let parsedUser = null;

if (storedUser) {
  try {
    parsedUser = JSON.parse(storedUser);
  } catch {
    localStorage.removeItem("user");
  }
}

// ==========================================================
// Initial State
// ==========================================================

const initialState = {
  // ------------------------------------------------------
  // User information may survive a browser reload.
  // ------------------------------------------------------

  user: parsedUser,

  // ------------------------------------------------------
  // Access token lives only in memory.
  // ------------------------------------------------------

  accessToken: null,

  // ------------------------------------------------------
  // Refresh token is NOT stored in Redux.
  //
  // It is maintained by the backend as an HttpOnly cookie.
  // ------------------------------------------------------

  isAuthenticated: false,

  // ------------------------------------------------------
  // Prevents ProtectedRoute from redirecting before the
  // startup refresh attempt has completed.
  // ------------------------------------------------------

  authInitialized: false,

  loading: false,

  success: false,

  error: null,

  pendingVerificationEmail: null,
};

// ==========================================================
// Slice
// ==========================================================

const authSlice = createSlice({
  name: "auth",

  initialState,

  reducers: {
    // ==================================================
    // Clear error
    // ==================================================

    clearError(state) {
      state.error = null;
    },

    // ==================================================
    // Reset status
    // ==================================================

    resetStatus(state) {
      state.loading = false;
      state.success = false;
      state.error = null;
    },

    // ==================================================
    // Mark authentication initialization complete
    // ==================================================

    setAuthInitialized(state) {
      state.authInitialized = true;
    },

    // ==================================================
    // Clear authentication
    //
    // This is used when the refresh session has genuinely
    // become invalid or the user explicitly logs out.
    // ==================================================

    clearAuthentication(state) {
      state.user = null;
      state.accessToken = null;
      state.isAuthenticated = false;
      state.authInitialized = true;
      state.loading = false;
      state.success = false;
      state.error = null;
    },
  },

  extraReducers: (builder) => {
    builder

      // ==================================================
      // REGISTER
      // ==================================================

      .addCase(registerUser.pending, (state) => {
        state.loading = true;
        state.error = null;
        state.success = false;
      })

      .addCase(registerUser.fulfilled, (state, action) => {
        state.loading = false;
        state.success = true;
        state.error = null;

        state.pendingVerificationEmail = action.meta.arg.email;
      })

      .addCase(registerUser.rejected, (state, action) => {
        state.loading = false;
        state.error = action.payload;
      })

      // ==================================================
      // LOGIN
      // ==================================================

      .addCase(loginUser.pending, (state) => {
        state.loading = true;
        state.error = null;
        state.success = false;
      })

      .addCase(loginUser.fulfilled, (state, action) => {
        const data = action.payload;

        state.loading = false;
        state.success = true;
        state.error = null;

        state.isAuthenticated = true;

        state.authInitialized = true;

        state.accessToken = data.access_token;

        state.user = data.user || null;
      })

      .addCase(loginUser.rejected, (state, action) => {
        state.loading = false;

        state.error = action.payload;

        state.isAuthenticated = false;

        state.accessToken = null;

        state.authInitialized = true;
      })

      // ==================================================
      // REFRESH ACCESS TOKEN
      //
      // The refresh token itself is never placed into
      // Redux. The browser sends the HttpOnly cookie.
      // ==================================================

      .addCase(refreshAccessToken.pending, (state) => {
        state.loading = true;
        state.error = null;
      })

      .addCase(refreshAccessToken.fulfilled, (state, action) => {
        const data = action.payload;

        state.loading = false;
        state.error = null;

        state.authInitialized = true;

        state.isAuthenticated = true;

        state.accessToken = data.access_token;

        // ------------------------------------------------
        // The current backend refresh endpoint does not
        // have to return user information.
        //
        // Therefore preserve the user already loaded
        // from localStorage.
        //
        // If the backend does return user information,
        // use it.
        // ------------------------------------------------

        if (data.user) {
          state.user = data.user;
        }
      })

      .addCase(refreshAccessToken.rejected, (state, action) => {
        state.loading = false;

        state.authInitialized = true;

        state.user = null;

        state.accessToken = null;

        state.isAuthenticated = false;

        state.error = action.payload || null;
      })

      // ==================================================
      // VERIFY EMAIL
      // ==================================================

      .addCase(verifyEmail.pending, (state) => {
        state.loading = true;
        state.error = null;
      })

      .addCase(verifyEmail.fulfilled, (state) => {
        state.loading = false;
        state.success = true;
        state.error = null;

        state.pendingVerificationEmail = null;
      })

      .addCase(verifyEmail.rejected, (state, action) => {
        state.loading = false;

        state.error = action.payload;
      })

      // ==================================================
      // RESEND OTP
      // ==================================================

      .addCase(resendOTP.pending, (state) => {
        state.loading = true;
        state.error = null;
      })

      .addCase(resendOTP.fulfilled, (state) => {
        state.loading = false;
        state.error = null;
      })

      .addCase(resendOTP.rejected, (state, action) => {
        state.loading = false;

        state.error = action.payload;
      })

      // ==================================================
      // FORGOT PASSWORD
      // ==================================================

      .addCase(forgotPassword.pending, (state) => {
        state.loading = true;
        state.error = null;
        state.success = false;
      })

      .addCase(forgotPassword.fulfilled, (state) => {
        state.loading = false;
        state.success = true;
        state.error = null;
      })

      .addCase(forgotPassword.rejected, (state, action) => {
        state.loading = false;

        state.error = action.payload;
      })

      // ==================================================
      // RESET PASSWORD
      // ==================================================

      .addCase(resetPassword.pending, (state) => {
        state.loading = true;
        state.error = null;
        state.success = false;
      })

      .addCase(resetPassword.fulfilled, (state) => {
        state.loading = false;
        state.success = true;
        state.error = null;
      })

      .addCase(resetPassword.rejected, (state, action) => {
        state.loading = false;

        state.error = action.payload;
      })

      // ==================================================
      // LOGOUT
      // ==================================================

      .addCase(logoutUser.pending, (state) => {
        state.loading = true;
        state.error = null;
      })

      .addCase(logoutUser.fulfilled, (state) => {
        state.user = null;

        state.accessToken = null;

        state.isAuthenticated = false;

        state.authInitialized = true;

        state.loading = false;

        state.success = false;

        state.error = null;
      })

      .addCase(logoutUser.rejected, (state) => {
        // ------------------------------------------------
        // Even when the backend logout request fails,
        // the local session must still be destroyed.
        // ------------------------------------------------

        state.user = null;

        state.accessToken = null;

        state.isAuthenticated = false;

        state.authInitialized = true;

        state.loading = false;

        state.success = false;
      });
  },
});

// ==========================================================
// Actions
// ==========================================================

export const {
  clearError,
  resetStatus,
  setAuthInitialized,
  clearAuthentication,
} = authSlice.actions;

// ==========================================================
// Reducer
// ==========================================================

export default authSlice.reducer;
