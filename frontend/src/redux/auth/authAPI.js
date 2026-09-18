import api, { clearAccessToken, setAccessToken } from "../../api/axios";

// ==========================================================
// Register
// ==========================================================

const register = async (userData) => {
    const response = await api.post(
        "/auth/register",
        {
            full_name: userData.full_name,
            email: userData.email,
            password: userData.password,
        }
    );

    return response.data;
};

// ==========================================================
// Verify Email
// ==========================================================

const verifyEmail = async (data) => {
    const response = await api.post(
        "/auth/verify-email",
        {
            email: data.email,
            otp: data.otp,
        }
    );

    return response.data;
};

// ==========================================================
// Resend OTP
// ==========================================================

const resendOTP = async (email) => {
    const response = await api.post(
        "/auth/resend-otp",
        {
            email,
        }
    );

    return response.data;
};

// ==========================================================
// Login
// ==========================================================

const login = async (credentials) => {
    const response = await api.post(
        "/auth/login",
        {
            email: credentials.email,
            password: credentials.password,
        }
    );

    const data = response.data;

    // ------------------------------------------------------
    // Store access token
    // ------------------------------------------------------

    setAccessToken(data.access_token);

    // ------------------------------------------------------
    // Store user
    // ------------------------------------------------------

    if (data.user) {
        localStorage.setItem(
            "user",
            JSON.stringify(data.user)
        );
    }

    return data;
};

// ==========================================================
// Refresh Token
//
// This function is mainly useful for application startup.
// Normal API requests are automatically refreshed by
// axios.js.
// ==========================================================

const refreshToken = async () => {
    try {
        const response = await api.post(
            "/auth/refresh",
            {}
        );

        const data = response.data;

        if (!data.access_token) {
            throw new Error(
                "Refresh endpoint did not return access_token."
            );
        }

        setAccessToken(data.access_token);

        return data;
    } catch (error) {
        clearAccessToken();
        localStorage.removeItem("user");
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

        localStorage.removeItem(
            "user"
        );
    }
};

// ==========================================================
// Forgot Password
// ==========================================================

const forgotPassword = async (data) => {
    const response = await api.post(
        "/auth/forgot-password",
        data
    );

    return response.data;
};

// ==========================================================
// Reset Password
// ==========================================================

const resetPassword = async (data) => {
    const response = await api.post(
        "/auth/reset-password",
        {
            email: data.email,
            otp: data.otp,
            new_password: data.new_password,
        }
    );

    return response.data;
};

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
