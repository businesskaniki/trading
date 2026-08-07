import axios from "axios";

const API_URL =
    import.meta.env.VITE_API_URL || "http://localhost/api/v1";

const api = axios.create({
    baseURL: API_URL,
    timeout: 30000,
    headers: {
        "Content-Type": "application/json",
    },
});

// -----------------------------------------------------
// Request Interceptor
// Adds the access token to every request
// -----------------------------------------------------

api.interceptors.request.use(
    (config) => {
        const token = localStorage.getItem("access_token");

        if (token) {
            config.headers.Authorization = `Bearer ${token}`;
        }

        return config;
    },
    (error) => Promise.reject(error)
);

// -----------------------------------------------------
// Response Interceptor
// Placeholder for automatic refresh token handling
// -----------------------------------------------------

api.interceptors.response.use(
    (response) => response,
    async (error) => {
        return Promise.reject(error);
    }
);

export default api;