import axios from "axios";

const API_URL = import.meta.env.VITE_API_URL || "http://localhost:8000/api/v1";

// ==========================================================
// Main API instance
// ==========================================================

const api = axios.create({
  baseURL: API_URL,
  timeout: 30000,
  headers: {
    "Content-Type": "application/json",
  },
  withCredentials: true,
});

// ==========================================================
// Dedicated refresh client
//
// IMPORTANT:
// This client has NO response interceptor.
//
// Therefore:
// /auth/refresh
//    ↓
// 401
//    ↓
// does NOT trigger another refresh
// ==========================================================

const refreshClient = axios.create({
  baseURL: API_URL,
  timeout: 30000,
  headers: {
    "Content-Type": "application/json",
  },
  withCredentials: true,
});

// ==========================================================
// In-memory access token
//
// The access token intentionally lives only in memory.
//
// It is restored from the HttpOnly refresh cookie when the
// application starts.
// ==========================================================

let accessToken = null;

export const setAccessToken = (token) => {
  accessToken = token || null;
};

export const clearAccessToken = () => {
  accessToken = null;
};

export const getAccessToken = () => accessToken;

// ==========================================================
// Refresh state
// ==========================================================

let isRefreshing = false;

let failedQueue = [];

// ==========================================================
// Authentication endpoints
//
// These endpoints should never receive an old access token
// and should never trigger the automatic refresh mechanism.
// ==========================================================

const AUTH_ENDPOINTS = [
  "/auth/login",
  "/auth/register",
  "/auth/verify-email",
  "/auth/resend-otp",
  "/auth/refresh",
  "/auth/forgot-password",
  "/auth/reset-password",
  "/auth/logout",
];

// ==========================================================
// Check whether a request is an authentication endpoint
// ==========================================================

const isAuthEndpoint = (url = "") => {
  return AUTH_ENDPOINTS.some((endpoint) => url.includes(endpoint));
};

// ==========================================================
// Process queued requests
// ==========================================================

const processQueue = (error, token = null) => {
  failedQueue.forEach(({ resolve, reject }) => {
    if (error) {
      reject(error);
      return;
    }

    resolve(token);
  });

  failedQueue = [];
};

// ==========================================================
// Clear authentication
// ==========================================================

const clearAuthentication = () => {
  clearAccessToken();

  localStorage.removeItem("user");

  window.dispatchEvent(new Event("auth:logout"));
};

// ==========================================================
// Request interceptor
//
// Adds the current access token to normal protected
// requests.
//
// Authentication endpoints are intentionally excluded.
// ==========================================================

api.interceptors.request.use(
  (config) => {
    const requestUrl = config.url || "";

    if (!isAuthEndpoint(requestUrl) && accessToken) {
      config.headers = config.headers || {};

      config.headers.Authorization = `Bearer ${accessToken}`;
    }

    return config;
  },
  (error) => Promise.reject(error),
);

// ==========================================================
// Response interceptor
//
// Protected request:
//
//     401
//      ↓
//     refresh
//      ↓
//     new access token
//      ↓
//     retry original request
//
// Multiple simultaneous 401 responses share ONE refresh
// request. The remaining requests wait in failedQueue.
// ==========================================================

api.interceptors.response.use(
  (response) => response,

  async (error) => {
    const originalRequest = error.config;

    // --------------------------------------------------
    // Only process HTTP 401 responses
    // --------------------------------------------------

    if (error.response?.status !== 401) {
      return Promise.reject(error);
    }

    // --------------------------------------------------
    // No request configuration
    // --------------------------------------------------

    if (!originalRequest) {
      return Promise.reject(error);
    }

    // --------------------------------------------------
    // Never refresh authentication endpoints
    // --------------------------------------------------

    const requestUrl = originalRequest.url || "";

    if (isAuthEndpoint(requestUrl)) {
      return Promise.reject(error);
    }

    // --------------------------------------------------
    // Prevent infinite retry loops
    // --------------------------------------------------

    if (originalRequest._retry) {
      return Promise.reject(error);
    }

    originalRequest._retry = true;

    // --------------------------------------------------
    // Another request is already refreshing
    //
    // Wait for the existing refresh operation rather
    // than creating another refresh request.
    // --------------------------------------------------

    if (isRefreshing) {
      return new Promise((resolve, reject) => {
        failedQueue.push({
          resolve,
          reject,
        });
      }).then((newAccessToken) => {
        originalRequest.headers = originalRequest.headers || {};

        originalRequest.headers.Authorization = `Bearer ${newAccessToken}`;

        return api(originalRequest);
      });
    }

    // --------------------------------------------------
    // Start one refresh operation
    // --------------------------------------------------

    isRefreshing = true;

    try {
      // ------------------------------------------------
      // IMPORTANT:
      //
      // Do NOT send {}.
      //
      // The backend accepts the refresh token from the
      // HttpOnly cookie:
      //
      // request.cookies["refresh_token"]
      // ------------------------------------------------

      const response = await refreshClient.post("/auth/refresh");

      const newAccessToken = response.data?.access_token;

      if (!newAccessToken) {
        throw new Error("Refresh endpoint did not return access_token.");
      }

      // ------------------------------------------------
      // Store new access token in memory
      // ------------------------------------------------

      setAccessToken(newAccessToken);

      // ------------------------------------------------
      // Release waiting requests
      // ------------------------------------------------

      processQueue(null, newAccessToken);

      // ------------------------------------------------
      // Retry original request
      // ------------------------------------------------

      originalRequest.headers = originalRequest.headers || {};

      originalRequest.headers.Authorization = `Bearer ${newAccessToken}`;

      return api(originalRequest);
    } catch (refreshError) {
      // ------------------------------------------------
      // Refresh failed.
      //
      // All queued requests must fail.
      // The application will then clear its session.
      // ------------------------------------------------

      processQueue(refreshError, null);

      clearAuthentication();

      return Promise.reject(refreshError);
    } finally {
      isRefreshing = false;
    }
  },
);

export default api;
