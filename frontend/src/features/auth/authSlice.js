import { createSlice, createAsyncThunk } from "@reduxjs/toolkit";
import api from "../../api/axios";
import { setCookie, removeCookie } from "../../utils/cookies";

export const login = createAsyncThunk(
  "auth/login",
  async (credentials, { rejectWithValue }) => {
    try {
      const resp = await api.post("/auth/login", credentials);
      const { access_token, refresh_token, user } = resp.data;
      if (access_token) localStorage.setItem("accessToken", access_token);
      if (refresh_token) setCookie("refreshToken", refresh_token);
      return { user, accessToken: access_token };
    } catch (err) {
      return rejectWithValue(err.response?.data || err.message);
    }
  },
);

export const refreshToken = createAsyncThunk(
  "auth/refresh",
  async (_, { rejectWithValue }) => {
    try {
      const resp = await api.post("/auth/refresh");
      const { access_token, user } = resp.data;
      if (access_token) localStorage.setItem("accessToken", access_token);
      return { user, accessToken: access_token };
    } catch (err) {
      localStorage.removeItem("accessToken");
      removeCookie("refreshToken");
      return rejectWithValue(err.response?.data || err.message);
    }
  },
);

const authSlice = createSlice({
  name: "auth",
  initialState: {
    user: null,
    accessToken: localStorage.getItem("accessToken") || null,
    status: "idle",
    error: null,
  },
  reducers: {
    logout(state) {
      state.user = null;
      state.accessToken = null;
      localStorage.removeItem("accessToken");
      removeCookie("refreshToken");
    },
  },
  extraReducers: (builder) => {
    builder
      .addCase(login.pending, (state) => {
        state.status = "loading";
        state.error = null;
      })
      .addCase(login.fulfilled, (state, action) => {
        state.status = "succeeded";
        state.user = action.payload.user;
        state.accessToken = action.payload.accessToken;
      })
      .addCase(login.rejected, (state, action) => {
        state.status = "failed";
        state.error = action.payload;
      })
      .addCase(refreshToken.fulfilled, (state, action) => {
        state.status = "succeeded";
        state.user = action.payload.user;
        state.accessToken = action.payload.accessToken;
      })
      .addCase(refreshToken.rejected, (state) => {
        state.user = null;
        state.accessToken = null;
      });
  },
});

export const { logout } = authSlice.actions;
export default authSlice.reducer;
