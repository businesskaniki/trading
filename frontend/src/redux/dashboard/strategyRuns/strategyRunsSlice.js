import { createSlice } from "@reduxjs/toolkit";

import {
  disableStrategyRun,
  enableStrategyRun,
  fetchStrategyRun,
  fetchStrategyRuns,
  fetchStrategyRunsByName,
  fetchStrategyRunsByStatus,
  fetchStrategyRunsByType,
  updateStrategyRun,
} from "./strategyRunsThunks";

const initialState = {
  items: [],

  selected: null,

  loading: false,
  detailLoading: false,
  mutationLoading: false,

  error: null,
  detailError: null,
  mutationError: null,

  lastUpdated: null,

  filters: {
    name: null,
    status: null,
    type: null,
  },
};

const normalizeList = (payload) => {
  if (Array.isArray(payload)) {
    return payload;
  }

  if (Array.isArray(payload?.items)) {
    return payload.items;
  }

  return [];
};

const replaceItem = (items, updatedItem) => {
  if (!updatedItem?.id) {
    return items;
  }

  const exists = items.some(
    (item) => String(item.id) === String(updatedItem.id),
  );

  if (!exists) {
    return [updatedItem, ...items];
  }

  return items.map((item) =>
    String(item.id) === String(updatedItem.id) ? updatedItem : item,
  );
};

const strategyRunsSlice = createSlice({
  name: "strategyRuns",

  initialState,

  reducers: {
    clearStrategyRunsError: (state) => {
      state.error = null;
    },

    clearStrategyRunDetailError: (state) => {
      state.detailError = null;
    },

    clearStrategyRunMutationError: (state) => {
      state.mutationError = null;
    },

    clearSelectedStrategyRun: (state) => {
      state.selected = null;
      state.detailError = null;
    },

    setSelectedStrategyRun: (state, action) => {
      state.selected = action.payload || null;
    },

    clearStrategyRunFilters: (state) => {
      state.filters = {
        name: null,
        status: null,
        type: null,
      };
    },

    setStrategyRunFilter: (state, action) => {
      const { key, value } = action.payload || {};

      if (!Object.prototype.hasOwnProperty.call(state.filters, key)) {
        return;
      }

      state.filters[key] = value || null;
    },
  },

  extraReducers: (builder) => {
    builder

      /* ======================================================
         FETCH ALL
         ====================================================== */

      .addCase(fetchStrategyRuns.pending, (state) => {
        state.loading = true;
        state.error = null;
      })

      .addCase(fetchStrategyRuns.fulfilled, (state, action) => {
        state.loading = false;
        state.error = null;

        state.items = normalizeList(action.payload);

        state.lastUpdated = new Date().toISOString();

        state.filters = {
          name: null,
          status: null,
          type: null,
        };
      })

      .addCase(fetchStrategyRuns.rejected, (state, action) => {
        state.loading = false;

        state.error =
          action.payload ||
          action.error?.message ||
          "Failed to load strategy runs.";
      })

      /* ======================================================
         FETCH ONE
         ====================================================== */

      .addCase(fetchStrategyRun.pending, (state) => {
        state.detailLoading = true;
        state.detailError = null;
      })

      .addCase(fetchStrategyRun.fulfilled, (state, action) => {
        state.detailLoading = false;
        state.detailError = null;

        state.selected = action.payload || null;

        state.items = replaceItem(state.items, action.payload);
      })

      .addCase(fetchStrategyRun.rejected, (state, action) => {
        state.detailLoading = false;

        state.detailError =
          action.payload ||
          action.error?.message ||
          "Failed to load the strategy run.";
      })

      /* ======================================================
         GENERIC UPDATE
         ====================================================== */

      .addCase(updateStrategyRun.pending, (state) => {
        state.mutationLoading = true;
        state.mutationError = null;
      })

      .addCase(updateStrategyRun.fulfilled, (state, action) => {
        state.mutationLoading = false;
        state.mutationError = null;

        if (action.payload) {
          state.items = replaceItem(state.items, action.payload);

          state.selected = action.payload;
        }

        state.lastUpdated = new Date().toISOString();
      })

      .addCase(updateStrategyRun.rejected, (state, action) => {
        state.mutationLoading = false;

        state.mutationError =
          action.payload ||
          action.error?.message ||
          "Failed to update the strategy.";
      })

      /* ======================================================
         ENABLE
         ====================================================== */

      .addCase(enableStrategyRun.pending, (state) => {
        state.mutationLoading = true;
        state.mutationError = null;
      })

      .addCase(enableStrategyRun.fulfilled, (state, action) => {
        state.mutationLoading = false;
        state.mutationError = null;

        if (action.payload) {
          state.items = replaceItem(state.items, action.payload);

          state.selected = action.payload;
        }

        state.lastUpdated = new Date().toISOString();
      })

      .addCase(enableStrategyRun.rejected, (state, action) => {
        state.mutationLoading = false;

        state.mutationError =
          action.payload ||
          action.error?.message ||
          "Failed to activate the strategy.";
      })

      /* ======================================================
         DISABLE
         ====================================================== */

      .addCase(disableStrategyRun.pending, (state) => {
        state.mutationLoading = true;
        state.mutationError = null;
      })

      .addCase(disableStrategyRun.fulfilled, (state, action) => {
        state.mutationLoading = false;
        state.mutationError = null;

        if (action.payload) {
          state.items = replaceItem(state.items, action.payload);

          state.selected = action.payload;
        }

        state.lastUpdated = new Date().toISOString();
      })

      .addCase(disableStrategyRun.rejected, (state, action) => {
        state.mutationLoading = false;

        state.mutationError =
          action.payload ||
          action.error?.message ||
          "Failed to deactivate the strategy.";
      })

      /* ======================================================
         FILTER: NAME
         ====================================================== */

      .addCase(fetchStrategyRunsByName.pending, (state) => {
        state.loading = true;
        state.error = null;
      })

      .addCase(fetchStrategyRunsByName.fulfilled, (state, action) => {
        state.loading = false;
        state.error = null;

        state.items = normalizeList(action.payload);

        state.lastUpdated = new Date().toISOString();

        state.filters = {
          name: action.meta.arg,
          status: null,
          type: null,
        };
      })

      .addCase(fetchStrategyRunsByName.rejected, (state, action) => {
        state.loading = false;

        state.error =
          action.payload ||
          action.error?.message ||
          "Failed to load strategy runs.";
      })

      /* ======================================================
         FILTER: STATUS
         ====================================================== */

      .addCase(fetchStrategyRunsByStatus.pending, (state) => {
        state.loading = true;
        state.error = null;
      })

      .addCase(fetchStrategyRunsByStatus.fulfilled, (state, action) => {
        state.loading = false;
        state.error = null;

        state.items = normalizeList(action.payload);

        state.lastUpdated = new Date().toISOString();

        state.filters = {
          name: null,
          status: action.meta.arg,
          type: null,
        };
      })

      .addCase(fetchStrategyRunsByStatus.rejected, (state, action) => {
        state.loading = false;

        state.error =
          action.payload ||
          action.error?.message ||
          "Failed to load strategy runs.";
      })

      /* ======================================================
         FILTER: TYPE
         ====================================================== */

      .addCase(fetchStrategyRunsByType.pending, (state) => {
        state.loading = true;
        state.error = null;
      })

      .addCase(fetchStrategyRunsByType.fulfilled, (state, action) => {
        state.loading = false;
        state.error = null;

        state.items = normalizeList(action.payload);

        state.lastUpdated = new Date().toISOString();

        state.filters = {
          name: null,
          status: null,
          type: action.meta.arg,
        };
      })

      .addCase(fetchStrategyRunsByType.rejected, (state, action) => {
        state.loading = false;

        state.error =
          action.payload ||
          action.error?.message ||
          "Failed to load strategy runs.";
      });
  },
});

export const {
  clearStrategyRunsError,
  clearStrategyRunDetailError,
  clearStrategyRunMutationError,
  clearSelectedStrategyRun,
  setSelectedStrategyRun,
  clearStrategyRunFilters,
  setStrategyRunFilter,
} = strategyRunsSlice.actions;

export default strategyRunsSlice.reducer;
