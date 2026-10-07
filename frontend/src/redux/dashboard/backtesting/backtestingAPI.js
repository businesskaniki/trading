import api from "../../../api/axios";

const backtestingAPI = {
  /**
   * Create a new backtest.
   *
   * The backend resolves strategies, symbols, timeframes,
   * and instrument metadata from the selected trading account.
   */
  create: async ({
    accountId,
    initialBalance,
    start,
    end,
    closePositionsAtEnd = true,
  }) => {
    if (!accountId) {
      throw new Error("A trading account is required.");
    }

    if (
      initialBalance === undefined ||
      initialBalance === null ||
      initialBalance === ""
    ) {
      throw new Error("An initial balance is required.");
    }

    if (!start) {
      throw new Error("A backtest start date is required.");
    }

    if (!end) {
      throw new Error("A backtest end date is required.");
    }

    const response = await api.post("/backtests", {
      account_id: accountId,
      initial_balance: initialBalance,
      start,
      end,
      close_positions_at_end: closePositionsAtEnd,
    });

    return response.data;
  },

  /**
   * Return all registered backtests.
   */
  getAll: async () => {
    const response = await api.get("/backtests");
    return response.data;
  },

  /**
   * Return one backtest.
   */
  getById: async (backtestId) => {
    if (!backtestId) {
      throw new Error("A backtest ID is required.");
    }

    const response = await api.get(`/backtests/${backtestId}`);

    return response.data;
  },

  /**
   * Start a CREATED backtest.
   */
  start: async (backtestId) => {
    if (!backtestId) {
      throw new Error("A backtest ID is required.");
    }

    const response = await api.post(`/backtests/${backtestId}/start`);

    return response.data;
  },

  /**
   * Request cooperative shutdown of a running backtest.
   */
  stop: async (backtestId) => {
    if (!backtestId) {
      throw new Error("A backtest ID is required.");
    }

    const response = await api.post(`/backtests/${backtestId}/stop`);

    return response.data;
  },

  /**
   * Delete a completed, stopped, or failed backtest.
   */
  remove: async (backtestId) => {
    if (!backtestId) {
      throw new Error("A backtest ID is required.");
    }

    await api.delete(`/backtests/${backtestId}`);
  },
};

export default backtestingAPI;
