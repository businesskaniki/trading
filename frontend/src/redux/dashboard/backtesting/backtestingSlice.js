import { createSlice } from "@reduxjs/toolkit";

import {
  fetchBacktests,
  fetchBacktest,
  createBacktest,
  startBacktest,
  stopBacktest,
  deleteBacktest,
} from "./backtestingThunks";

const initialState = {
  /* ---------------------------------------------------------------------- */
  /* Collection                                                             */
  /* ---------------------------------------------------------------------- */

  items: [],
  loading: false,
  error: null,
  lastUpdated: null,

  /* ---------------------------------------------------------------------- */
  /* Selected backtest                                                      */
  /* ---------------------------------------------------------------------- */

  selected: null,
  detailLoading: false,
  detailError: null,

  /* ---------------------------------------------------------------------- */
  /* Create lifecycle                                                       */
  /* ---------------------------------------------------------------------- */

  creating: false,
  createError: null,

  /* ---------------------------------------------------------------------- */
  /* Start lifecycle                                                        */
  /* ---------------------------------------------------------------------- */

  startingId: null,
  startError: null,

  /* ---------------------------------------------------------------------- */
  /* Stop lifecycle                                                         */
  /* ---------------------------------------------------------------------- */

  stoppingId: null,
  stopError: null,

  /* ---------------------------------------------------------------------- */
  /* Delete lifecycle                                                       */
  /* ---------------------------------------------------------------------- */

  deletingId: null,
  deleteError: null,
};

const getId = (value) => {
  if (!value) {
    return null;
  }

  if (typeof value === "string" || typeof value === "number") {
    return String(value);
  }

  return value.id ? String(value.id) : null;
};

const sameId = (left, right) => {
  const leftId = getId(left);
  const rightId = getId(right);

  return Boolean(leftId && rightId && leftId === rightId);
};

const upsertBacktest = (items, backtest) => {
  if (!backtest) {
    return items;
  }

  const backtestId = getId(backtest);

  if (!backtestId) {
    return items;
  }

  const index = items.findIndex((item) => sameId(item, backtest));

  if (index === -1) {
    return [backtest, ...items];
  }

  const next = [...items];
  next[index] = backtest;

  return next;
};

const backtestingSlice = createSlice({
  name: "backtesting",

  initialState,

  reducers: {
    /* -------------------------------------------------------------------- */
    /* General errors                                                       */
    /* -------------------------------------------------------------------- */

    clearBacktestingError: (state) => {
      state.error = null;
    },

    clearBacktestDetailError: (state) => {
      state.detailError = null;
    },

    clearBacktestCreateError: (state) => {
      state.createError = null;
    },

    clearBacktestStartError: (state) => {
      state.startError = null;
    },

    clearBacktestStopError: (state) => {
      state.stopError = null;
    },

    clearBacktestDeleteError: (state) => {
      state.deleteError = null;
    },

    /* -------------------------------------------------------------------- */
    /* Selection                                                            */
    /* -------------------------------------------------------------------- */

    setSelectedBacktest: (state, action) => {
      state.selected = action.payload || null;
      state.detailError = null;
    },

    clearSelectedBacktest: (state) => {
      state.selected = null;
      state.detailError = null;
    },
  },

  extraReducers: (builder) => {
    builder

      /* ================================================================== */
      /* FETCH ALL                                                          */
      /* ================================================================== */

      .addCase(fetchBacktests.pending, (state) => {
        state.loading = true;
        state.error = null;
      })

      .addCase(fetchBacktests.fulfilled, (state, action) => {
        state.loading = false;
        state.error = null;
        state.lastUpdated = new Date().toISOString();

        const incomingItems = Array.isArray(action.payload)
          ? action.payload.filter(Boolean)
          : [];

        state.items = incomingItems;

        /*
         * If there is already a selected backtest, replace it with the
         * freshly loaded version from the collection.
         */
        if (state.selected) {
          const updatedSelected = incomingItems.find((backtest) =>
            sameId(backtest, state.selected),
          );

          if (updatedSelected) {
            state.selected = updatedSelected;
          } else {
            /*
             * The selected backtest no longer exists in the collection.
             */
            state.selected = null;
          }
        }

        /*
         * If nothing is selected but the backend returned backtests,
         * automatically select the first one.
         *
         * This prevents the page from looking empty even though data
         * successfully loaded.
         */
        if (!state.selected && incomingItems.length > 0) {
          state.selected = incomingItems[0];
        }
      })

      .addCase(fetchBacktests.rejected, (state, action) => {
        state.loading = false;
        state.error =
          action.payload ||
          action.error?.message ||
          "Failed to load backtests.";
      })

      /* ================================================================== */
      /* FETCH ONE                                                          */
      /* ================================================================== */

      .addCase(fetchBacktest.pending, (state) => {
        state.detailLoading = true;
        state.detailError = null;
      })

      .addCase(fetchBacktest.fulfilled, (state, action) => {
        state.detailLoading = false;
        state.detailError = null;

        const backtest = action.payload;

        if (!backtest) {
          return;
        }

        state.selected = backtest;
        state.items = upsertBacktest(state.items, backtest);
      })

      .addCase(fetchBacktest.rejected, (state, action) => {
        state.detailLoading = false;
        state.detailError =
          action.payload ||
          action.error?.message ||
          "Failed to load the backtest.";
      })

      /* ================================================================== */
      /* CREATE                                                             */
      /* ================================================================== */

      .addCase(createBacktest.pending, (state) => {
        state.creating = true;
        state.createError = null;
      })

      .addCase(createBacktest.fulfilled, (state, action) => {
        state.creating = false;
        state.createError = null;

        const created = action.payload;

        if (!created) {
          return;
        }

        state.items = upsertBacktest(state.items, created);
        state.selected = created;
      })

      .addCase(createBacktest.rejected, (state, action) => {
        state.creating = false;
        state.createError =
          action.payload ||
          action.error?.message ||
          "Failed to create the backtest.";
      })

      /* ================================================================== */
      /* START                                                              */
      /* ================================================================== */

      .addCase(startBacktest.pending, (state, action) => {
        state.startingId = action.meta.arg;
        state.startError = null;
      })

      .addCase(startBacktest.fulfilled, (state, action) => {
        state.startingId = null;
        state.startError = null;

        const updatedBacktest = action.payload;

        if (!updatedBacktest) {
          return;
        }

        state.items = upsertBacktest(state.items, updatedBacktest);

        if (state.selected && sameId(state.selected, updatedBacktest)) {
          state.selected = updatedBacktest;
        }
      })

      .addCase(startBacktest.rejected, (state, action) => {
        state.startingId = null;
        state.startError =
          action.payload ||
          action.error?.message ||
          "Failed to start the backtest.";
      })

      /* ================================================================== */
      /* STOP                                                               */
      /* ================================================================== */

      .addCase(stopBacktest.pending, (state, action) => {
        state.stoppingId = action.meta.arg;
        state.stopError = null;
      })

      .addCase(stopBacktest.fulfilled, (state, action) => {
        state.stoppingId = null;
        state.stopError = null;

        const updatedBacktest = action.payload;

        if (!updatedBacktest) {
          return;
        }

        state.items = upsertBacktest(state.items, updatedBacktest);

        if (state.selected && sameId(state.selected, updatedBacktest)) {
          state.selected = updatedBacktest;
        }
      })

      .addCase(stopBacktest.rejected, (state, action) => {
        state.stoppingId = null;
        state.stopError =
          action.payload ||
          action.error?.message ||
          "Failed to stop the backtest.";
      })

      /* ================================================================== */
      /* DELETE                                                             */
      /* ================================================================== */

      .addCase(deleteBacktest.pending, (state, action) => {
        state.deletingId = action.meta.arg;
        state.deleteError = null;
      })

      .addCase(deleteBacktest.fulfilled, (state, action) => {
        const deletedId = getId(action.payload);

        state.deletingId = null;
        state.deleteError = null;

        if (!deletedId) {
          return;
        }

        state.items = state.items.filter(
          (backtest) => getId(backtest) !== deletedId,
        );

        if (getId(state.selected) === deletedId) {
          /*
           * Select another existing backtest if one remains.
           * Otherwise clear the selection.
           */
          state.selected = state.items.length > 0 ? state.items[0] : null;
        }
      })

      .addCase(deleteBacktest.rejected, (state, action) => {
        state.deletingId = null;
        state.deleteError =
          action.payload ||
          action.error?.message ||
          "Failed to delete the backtest.";
      });
  },
});

export const {
  clearBacktestingError,
  clearBacktestDetailError,
  clearBacktestCreateError,
  clearBacktestStartError,
  clearBacktestStopError,
  clearBacktestDeleteError,
  setSelectedBacktest,
  clearSelectedBacktest,
} = backtestingSlice.actions;

export default backtestingSlice.reducer;
