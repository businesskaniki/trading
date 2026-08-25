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
// Load persisted authentication
// ==========================================================

const storedAccessToken =
    localStorage.getItem(
        "access_token"
    );

const storedRefreshToken =
    localStorage.getItem(
        "refresh_token"
    );

const storedUser =
    localStorage.getItem("user");

let parsedUser = null;

if (storedUser) {
    try {
        parsedUser = JSON.parse(
            storedUser
        );
    } catch {
        localStorage.removeItem("user");
    }
}

// ==========================================================
// Initial State
// ==========================================================

const initialState = {
    user: parsedUser,

    accessToken:
        storedAccessToken,

    refreshToken:
        storedRefreshToken,

    isAuthenticated:
        !!storedAccessToken &&
        !!storedRefreshToken,

    // VERY IMPORTANT
    //
    // Prevents ProtectedRoute from redirecting
    // before we determine whether the stored
    // session is still valid.
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
        clearError(state) {
            state.error = null;
        },

        resetStatus(state) {
            state.loading = false;
            state.success = false;
            state.error = null;
        },

        setAuthInitialized(state) {
            state.authInitialized = true;
        },

        clearAuthentication(state) {
            state.user = null;
            state.accessToken = null;
            state.refreshToken = null;
            state.isAuthenticated = false;
        },
    },

    extraReducers: (builder) => {
        builder

            // ==================================================
            // REGISTER
            // ==================================================

            .addCase(
                registerUser.pending,
                (state) => {
                    state.loading = true;
                    state.error = null;
                    state.success = false;
                }
            )

            .addCase(
                registerUser.fulfilled,
                (state, action) => {
                    state.loading = false;
                    state.success = true;

                    state.pendingVerificationEmail =
                        action.meta.arg.email;
                }
            )

            .addCase(
                registerUser.rejected,
                (state, action) => {
                    state.loading = false;
                    state.error =
                        action.payload;
                }
            )

            // ==================================================
            // LOGIN
            // ==================================================

            .addCase(
                loginUser.pending,
                (state) => {
                    state.loading = true;
                    state.error = null;
                    state.success = false;
                }
            )

            .addCase(
                loginUser.fulfilled,
                (state, action) => {
                    const data =
                        action.payload;

                    state.loading = false;

                    state.success = true;

                    state.isAuthenticated =
                        true;

                    state.authInitialized =
                        true;

                    state.accessToken =
                        data.access_token;

                    state.refreshToken =
                        data.refresh_token;

                    state.user =
                        data.user || null;
                }
            )

            .addCase(
                loginUser.rejected,
                (state, action) => {
                    state.loading = false;

                    state.error =
                        action.payload;

                    state.isAuthenticated =
                        false;

                    state.authInitialized =
                        true;
                }
            )

            // ==================================================
            // REFRESH TOKEN
            // ==================================================

            .addCase(
                refreshAccessToken.pending,
                (state) => {
                    state.loading = true;
                }
            )

            .addCase(
                refreshAccessToken.fulfilled,
                (state, action) => {
                    state.loading = false;

                    state.authInitialized =
                        true;

                    state.isAuthenticated =
                        true;

                    state.accessToken =
                        action.payload.access_token;
                }
            )

            .addCase(
                refreshAccessToken.rejected,
                (state) => {
                    state.loading = false;

                    state.authInitialized =
                        true;

                    state.user = null;

                    state.accessToken = null;

                    state.refreshToken = null;

                    state.isAuthenticated =
                        false;
                }
            )

            // ==================================================
            // VERIFY EMAIL
            // ==================================================

            .addCase(
                verifyEmail.pending,
                (state) => {
                    state.loading = true;
                    state.error = null;
                }
            )

            .addCase(
                verifyEmail.fulfilled,
                (state) => {
                    state.loading = false;
                    state.success = true;

                    state.pendingVerificationEmail =
                        null;
                }
            )

            .addCase(
                verifyEmail.rejected,
                (state, action) => {
                    state.loading = false;
                    state.error =
                        action.payload;
                }
            )

            // ==================================================
            // RESEND OTP
            // ==================================================

            .addCase(
                resendOTP.pending,
                (state) => {
                    state.loading = true;
                    state.error = null;
                }
            )

            .addCase(
                resendOTP.fulfilled,
                (state) => {
                    state.loading = false;
                }
            )

            .addCase(
                resendOTP.rejected,
                (state, action) => {
                    state.loading = false;
                    state.error =
                        action.payload;
                }
            )

            // ==================================================
            // FORGOT PASSWORD
            // ==================================================

            .addCase(
                forgotPassword.pending,
                (state) => {
                    state.loading = true;
                    state.error = null;
                    state.success = false;
                }
            )

            .addCase(
                forgotPassword.fulfilled,
                (state) => {
                    state.loading = false;
                    state.success = true;
                }
            )

            .addCase(
                forgotPassword.rejected,
                (state, action) => {
                    state.loading = false;
                    state.error =
                        action.payload;
                }
            )

            // ==================================================
            // RESET PASSWORD
            // ==================================================

            .addCase(
                resetPassword.pending,
                (state) => {
                    state.loading = true;
                    state.error = null;
                    state.success = false;
                }
            )

            .addCase(
                resetPassword.fulfilled,
                (state) => {
                    state.loading = false;
                    state.success = true;
                }
            )

            .addCase(
                resetPassword.rejected,
                (state, action) => {
                    state.loading = false;
                    state.error =
                        action.payload;
                }
            )

            // ==================================================
            // LOGOUT
            // ==================================================

            .addCase(
                logoutUser.fulfilled,
                (state) => {
                    state.user = null;

                    state.accessToken =
                        null;

                    state.refreshToken =
                        null;

                    state.isAuthenticated =
                        false;

                    state.authInitialized =
                        true;

                    state.loading = false;

                    state.success = false;

                    state.error = null;
                }
            )

            .addCase(
                logoutUser.rejected,
                (state) => {
                    // Even if the backend logout fails,
                    // the local session is destroyed.

                    state.user = null;

                    state.accessToken =
                        null;

                    state.refreshToken =
                        null;

                    state.isAuthenticated =
                        false;

                    state.authInitialized =
                        true;

                    state.loading = false;
                }
            );
    },
});

export const {
    clearError,
    resetStatus,
    setAuthInitialized,
    clearAuthentication,
} = authSlice.actions;

export default authSlice.reducer;