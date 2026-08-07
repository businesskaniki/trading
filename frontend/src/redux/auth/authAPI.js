import api from "../../api/axios";

// ==========================================================
// Register
// ==========================================================

const register = async (userData) => {
  try {
    const response = await api.post("/auth/register", {
      full_name: userData.full_name,
      email: userData.email,
      password: userData.password,
    });

    return response.data;
  } catch (err) {
    throw err;
  }
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

  if (data.access_token) {
    localStorage.setItem("access_token", data.access_token);
  }

  if (data.refresh_token) {
    localStorage.setItem("refresh_token", data.refresh_token);
  }

  return data;
};

// ==========================================================
// Refresh Token
// ==========================================================

const refreshToken = async () => {
  const refresh_token = localStorage.getItem("refresh_token");

  const response = await api.post("/auth/refresh", {
    refresh_token,
  });

  if (response.data.access_token) {
    localStorage.setItem("access_token", response.data.access_token);
  }

  return response.data;
};

// ==========================================================
// Logout
// ==========================================================

const logout = async () => {
  const refresh_token = localStorage.getItem("refresh_token");

  try {
    await api.post("/auth/logout", {
      refresh_token,
    });
  } catch (error) {
    // Ignore server errors during logout
  }

  localStorage.removeItem("access_token");
  localStorage.removeItem("refresh_token");
};

const forgotPassword = async (data) => {
  const response = await api.post("/auth/forgot-password", data);

  return response.data;
};

const resetPassword = async (data) => {
  const response = await api.post("/auth/reset-password", {
    email: data.email,
    otp: data.otp,
    new_password: data.new_password,
  });

  return response.data;
};
// ==========================================================
// Current User
// ==========================================================

const getCurrentUser = async () => {
  const response = await api.get("/auth/me");

  return response.data;
};

const authAPI = {
  register,
  verifyEmail,
  resendOTP,
  login,
  refreshToken,
  logout,
  getCurrentUser,
  forgotPassword,
  resetPassword,
};

export default authAPI;
