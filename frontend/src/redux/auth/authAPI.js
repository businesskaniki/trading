import api, { clearAccessToken, setAccessToken } from "../../api/axios";

// ==========================================================
// Register
// ==========================================================

const register = async (userData) => {
  const response = await api.post("/auth/register", {
    full_name: userData.full_name,
    email: userData.email,
    password: userData.password,
  });

  return response.data;
};

// ==========================================================
// Verify Email
// ==========================================================

const verifyEmail = async (data) => {
  const response = await api.post("/auth/verify-email", {
    email: data.email,
    otp: data.otp,
  });

  return response.data;
};

// ==========================================================
// Resend OTP
// ==========================================================

const resendOTP = async (email) => {
  const response = await api.post("/auth/resend-otp", {
    email,
  });

  return response.data;
};

// ==========================================================
// Login
// ==========================================================

const login = async (credentials) => {
  const response = await api.post("/auth/login", {
    email: credentials.email,
    password: credentials.password,
  });

  const data = response.data;

  // ------------------------------------------------------
  // Store access token in memory
  // ------------------------------------------------------

  if (data.access_token) {
    setAccessToken(data.access_token);
  }

  // ------------------------------------------------------
  // Persist user information locally
  //
  // The refresh token is NOT stored here.
  // It is maintained by the backend as an HttpOnly cookie.
  // ------------------------------------------------------

  if (data.user) {
    localStorage.setItem("user", JSON.stringify(data.user));
  }

  return data;
};

// ==========================================================
// Refresh Token
//
// Used primarily during application startup.
//
// The browser automatically sends the HttpOnly
// refresh_token cookie because axios uses:
//
//     withCredentials: true
//
// IMPORTANT:
// Do not send {} here.
// The backend reads the refresh token from the cookie.
// ==========================================================

const refreshToken = async () => {
  try {
    const response = await api.post("/auth/refresh");

    const data = response.data;

    if (!data.access_token) {
      throw new Error("Refresh endpoint did not return access_token.");
    }

    // --------------------------------------------------
    // Replace the expired access token in memory
    // --------------------------------------------------

    setAccessToken(data.access_token);

    // --------------------------------------------------
    // The refresh endpoint may return user information.
    // Preserve the existing user when it does not.
    // --------------------------------------------------

    if (data.user) {
      localStorage.setItem("user", JSON.stringify(data.user));
    }

    return data;
  } catch (error) {
    clearAccessToken();

    throw error;
  }
};

// ==========================================================
// Logout
// ==========================================================

const logout = async () => {
  try {
    await api.post("/auth/logout");
  } finally {
    clearAccessToken();

    localStorage.removeItem("user");
  }
};

// ==========================================================
// Forgot Password
// ==========================================================

const forgotPassword = async (data) => {
  const response = await api.post("/auth/forgot-password", data);

  return response.data;
};

// ==========================================================
// Reset Password
// ==========================================================

const resetPassword = async (data) => {
  const response = await api.post("/auth/reset-password", {
    email: data.email,
    otp: data.otp,
    new_password: data.new_password,
  });

  return response.data;
};

// ==========================================================
// API
// ==========================================================

const authAPI = {
  register,
  verifyEmail,
  resendOTP,
  login,
  refreshToken,
  logout,
  forgotPassword,
  resetPassword,
};

export default authAPI;
