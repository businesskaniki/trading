import { createSlice } from "@reduxjs/toolkit";

import {
  fetchEngineStatus,
  startEngine,
  stopEngine,
  pauseEngine,
  resumeEngine,
} from "./engineThunks";

// =====================================================
// INITIAL STATE
// =====================================================

const initialState = {
  status: "STOPPED",
  mode: null,

  // Runtime account currently controlled by the engine.
  account: null,

  market_data: null,
  strategies: null,
  pipeline: null,
  execution: null,

  loading: false,
  actionLoading: false,

  error: null,

  lastUpdated: null,
};

// =====================================================
// APPLY ENGINE SNAPSHOT
// =====================================================

const applyEngineSnapshot = (state, snapshot) => {
  if (!snapshot) {
    return;
  }

  state.status = snapshot.status || "STOPPED";
  state.mode = snapshot.mode || null;

  state.account = snapshot.account || null;

  state.market_data = snapshot.market_data || null;
  state.strategies = snapshot.strategies || null;
  state.pipeline = snapshot.pipeline || null;
  state.execution = snapshot.execution || null;

  state.lastUpdated = new Date().toISOString();
};

// =====================================================
// SLICE
// =====================================================

const engineSlice = createSlice({
  name: "engine",

  initialState,

  reducers: {
    clearEngineError: (state) => {
      state.error = null;
    },

    resetEngineState: () => ({
      ...initialState,
    }),
  },

  extraReducers: (builder) => {
    // ===================================================
    // GET STATUS
    // ===================================================

    builder
      .addCase(fetchEngineStatus.pending, (state) => {
        state.loading = true;
        state.error = null;
      })

      .addCase(fetchEngineStatus.fulfilled, (state, action) => {
        state.loading = false;
        state.error = null;

        applyEngineSnapshot(state, action.payload);
      })

      .addCase(fetchEngineStatus.rejected, (state, action) => {
        state.loading = false;

        state.error = action.payload || "Unable to fetch engine status.";
      });

    // ===================================================
    // START
    // ===================================================

    builder
      .addCase(startEngine.pending, (state) => {
        state.actionLoading = true;
        state.error = null;

        // The backend is now starting the runtime.
        state.status = "STARTING";
      })

      .addCase(startEngine.fulfilled, (state, action) => {
        state.actionLoading = false;
        state.error = null;

        applyEngineSnapshot(state, action.payload);
      })

      .addCase(startEngine.rejected, (state, action) => {
        state.actionLoading = false;

        state.error = action.payload || "Unable to start the trading engine.";

        state.status = "STOPPED";
      });

    // ===================================================
    // STOP
    // ===================================================

    builder
      .addCase(stopEngine.pending, (state) => {
        state.actionLoading = true;
        state.error = null;

        state.status = "STOPPING";
      })

      .addCase(stopEngine.fulfilled, (state, action) => {
        state.actionLoading = false;
        state.error = null;

        applyEngineSnapshot(state, action.payload);
      })

      .addCase(stopEngine.rejected, (state, action) => {
        state.actionLoading = false;

        state.error = action.payload || "Unable to stop the trading engine.";
      });

    // ===================================================
    // PAUSE
    // ===================================================

    builder
      .addCase(pauseEngine.pending, (state) => {
        state.actionLoading = true;
        state.error = null;
      })

      .addCase(pauseEngine.fulfilled, (state, action) => {
        state.actionLoading = false;
        state.error = null;

        applyEngineSnapshot(state, action.payload);
      })

      .addCase(pauseEngine.rejected, (state, action) => {
        state.actionLoading = false;

        state.error = action.payload || "Unable to pause the trading engine.";
      });

    // ===================================================
    // RESUME / UNPAUSE
    // ===================================================

    builder
      .addCase(resumeEngine.pending, (state) => {
        state.actionLoading = true;
        state.error = null;
      })

      .addCase(resumeEngine.fulfilled, (state, action) => {
        state.actionLoading = false;
        state.error = null;

        applyEngineSnapshot(state, action.payload);
      })

      .addCase(resumeEngine.rejected, (state, action) => {
        state.actionLoading = false;

        state.error = action.payload || "Unable to resume the trading engine.";
      });
  },
});

// =====================================================
// ACTIONS
// =====================================================

export const { clearEngineError, resetEngineState } = engineSlice.actions;

// =====================================================
// MAIN SELECTOR
// =====================================================

export const selectEngine = (state) => state.engine;

// =====================================================
// ENGINE STATUS
// =====================================================

export const selectEngineStatus = (state) => state.engine?.status || "STOPPED";

export const selectEngineRunning = (state) =>
  state.engine?.status === "RUNNING";

export const selectEnginePaused = (state) => state.engine?.status === "PAUSED";

export const selectEngineStarting = (state) =>
  state.engine?.status === "STARTING";

export const selectEngineStopping = (state) =>
  state.engine?.status === "STOPPING";

export const selectEngineStopped = (state) =>
  state.engine?.status === "STOPPED";

// =====================================================
// ENGINE ACCOUNT
// =====================================================

export const selectEngineAccount = (state) => state.engine?.account || null;

export const selectEngineAccountId = (state) =>
  state.engine?.account?.id || null;

// =====================================================
// ENGINE MODE
// =====================================================

export const selectEngineMode = (state) => state.engine?.mode || null;

// =====================================================
// ENGINE COMPONENTS
// =====================================================

export const selectEngineMarketData = (state) =>
  state.engine?.market_data || null;

export const selectEngineStrategies = (state) =>
  state.engine?.strategies || null;

export const selectEnginePipeline = (state) => state.engine?.pipeline || null;

export const selectEngineExecution = (state) => state.engine?.execution || null;

// =====================================================
// LOADING
// =====================================================

export const selectEngineLoading = (state) => Boolean(state.engine?.loading);

export const selectEngineActionLoading = (state) =>
  Boolean(state.engine?.actionLoading);

// =====================================================
// ERROR
// =====================================================

export const selectEngineError = (state) => state.engine?.error || null;

// =====================================================
// LAST UPDATED
// =====================================================

export const selectEngineLastUpdated = (state) =>
  state.engine?.lastUpdated || null;

// =====================================================
// DEFAULT EXPORT
// =====================================================

export default engineSlice.reducer;
