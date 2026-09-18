import axios from "axios";

const API_URL =
    import.meta.env.VITE_API_URL || "http://localhost:8000/api/v1";

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
// Separate axios instance for token refresh
//
// IMPORTANT:
// This does NOT use the main interceptors.
// Therefore the refresh request will never trigger
// another refresh request.
// ==========================================================

const refreshClient = axios.create({
    baseURL: API_URL,
    timeout: 30000,
    headers: {
        "Content-Type": "application/json",
    },
    withCredentials: true,
});

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
// Process queued requests
// ==========================================================

const processQueue = (error, token = null) => {
    failedQueue.forEach(({ resolve, reject }) => {
        if (error) {
            reject(error);
        } else {
            resolve(token);
        }
    });

    failedQueue = [];
};

// ==========================================================
// Clear authentication
// ==========================================================

const clearAuthentication = () => {
    clearAccessToken();
    localStorage.removeItem("user");

    window.dispatchEvent(
        new Event("auth:logout")
    );
};

// ==========================================================
// Request Interceptor
//
// Adds access token to normal API requests.
//
// IMPORTANT:
// Login, register, refresh, etc. are excluded because
// they should NOT receive an old access token.
// ==========================================================

api.interceptors.request.use(
    (config) => {
        const publicEndpoints = [
            "/auth/login",
            "/auth/register",
            "/auth/verify-email",
            "/auth/resend-otp",
            "/auth/refresh",
            "/auth/forgot-password",
            "/auth/reset-password",
            "/auth/logout",
        ];

        const requestUrl = config.url || "";

        const isPublicEndpoint = publicEndpoints.some(
            (endpoint) =>
                requestUrl.includes(endpoint)
        );

        if (!isPublicEndpoint) {
            if (accessToken) {
                config.headers.Authorization =
                    `Bearer ${accessToken}`;
            }
        }

        return config;
    },

    (error) => Promise.reject(error)
);

// ==========================================================
// Response Interceptor
//
// Handles:
//
// 401
// ↓
// access token expired
// ↓
// refresh token
// ↓
// save new access token
// ↓
// retry original request
// ==========================================================

api.interceptors.response.use(
    (response) => response,

    async (error) => {
        const originalRequest =
            error.config;

        // --------------------------------------------------
        // Only handle 401 errors
        // --------------------------------------------------

        if (
            error.response?.status !== 401
        ) {
            return Promise.reject(error);
        }

        // --------------------------------------------------
        // Safety checks
        // --------------------------------------------------

        if (!originalRequest) {
            return Promise.reject(error);
        }

        // --------------------------------------------------
        // Never refresh these endpoints
        // --------------------------------------------------

        const url =
            originalRequest.url || "";

        const shouldNotRefresh =
            url.includes("/auth/login") ||
            url.includes("/auth/register") ||
            url.includes("/auth/verify-email") ||
            url.includes("/auth/resend-otp") ||
            url.includes("/auth/refresh") ||
            url.includes("/auth/forgot-password") ||
            url.includes("/auth/reset-password") ||
            url.includes("/auth/logout");

        if (shouldNotRefresh) {
            return Promise.reject(error);
        }

        // --------------------------------------------------
        // Prevent infinite retry
        // --------------------------------------------------

        if (originalRequest._retry) {
            return Promise.reject(error);
        }

        originalRequest._retry = true;

        // --------------------------------------------------
        // Get refresh token
        // --------------------------------------------------

        // --------------------------------------------------
        // Another request is already refreshing
        // --------------------------------------------------

        if (isRefreshing) {
            return new Promise(
                (resolve, reject) => {
                    failedQueue.push({
                        resolve,
                        reject,
                    });
                }
            )
                .then((newAccessToken) => {
                    originalRequest.headers.Authorization =
                        `Bearer ${newAccessToken}`;

                    return api(
                        originalRequest
                    );
                });
        }

        // --------------------------------------------------
        // Start refresh
        // --------------------------------------------------

        isRefreshing = true;

        try {
            const response =
                await refreshClient.post(
                    "/auth/refresh",
                    {}
                );

            const newAccessToken =
                response.data.access_token;

            if (!newAccessToken) {
                throw new Error(
                    "Refresh endpoint did not return access_token."
                );
            }

            // --------------------------------------------------
            // Save new access token
            // --------------------------------------------------

            setAccessToken(newAccessToken);

            // --------------------------------------------------
            // Resolve queued requests
            // --------------------------------------------------

            processQueue(
                null,
                newAccessToken
            );

            // --------------------------------------------------
            // Retry original request
            // --------------------------------------------------

            originalRequest.headers.Authorization =
                `Bearer ${newAccessToken}`;

            return api(
                originalRequest
            );

        } catch (refreshError) {
            // --------------------------------------------------
            // Refresh failed
            // --------------------------------------------------

            processQueue(
                refreshError,
                null
            );

            clearAuthentication();

            return Promise.reject(
                refreshError
            );

        } finally {
            isRefreshing = false;
        }
    }
);

export default api;
