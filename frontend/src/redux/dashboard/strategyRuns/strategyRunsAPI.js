import api from "../../../api/axios";

const strategyRunsAPI = {
  /**
   * Get all strategy runs belonging to the authenticated user.
   */
  getAll: async () => {
    const response = await api.get("/strategy-runs");
    return response.data;
  },

  /**
   * Get a single strategy run.
   */
  getById: async (strategyRunId) => {
    if (!strategyRunId) {
      throw new Error("A strategy run ID is required.");
    }

    const response = await api.get(
      `/strategy-runs/${strategyRunId}`,
    );

    return response.data;
  },

  /**
   * Update an existing strategy run.
   *
   * Used for mutable fields such as:
   * - enabled
   * - status
   * - parameters
   * - symbols
   * - timeframe
   * - notes
   *
   * Account and strategy definition identity remain
   * controlled by the backend service.
   */
  update: async (strategyRunId, payload) => {
    if (!strategyRunId) {
      throw new Error("A strategy run ID is required.");
    }

    if (!payload || typeof payload !== "object") {
      throw new Error("A strategy run update payload is required.");
    }

    const response = await api.patch(
      `/strategy-runs/${strategyRunId}`,
      payload,
    );

    return response.data;
  },

  /**
   * Activate an existing strategy.
   */
  enable: async (strategyRunId) => {
    return strategyRunsAPI.update(strategyRunId, {
      enabled: true,
    });
  },

  /**
   * Deactivate an existing strategy.
   */
  disable: async (strategyRunId) => {
    return strategyRunsAPI.update(strategyRunId, {
      enabled: false,
    });
  },

  /**
   * Get strategy runs by strategy name.
   */
  getByName: async (strategyName) => {
    if (!strategyName) {
      throw new Error("A strategy name is required.");
    }

    const response = await api.get(
      `/strategy-runs/name/${encodeURIComponent(strategyName)}`,
    );

    return response.data;
  },

  /**
   * Get strategy runs by status.
   */
  getByStatus: async (status) => {
    if (!status) {
      throw new Error("A strategy run status is required.");
    }

    const response = await api.get(
      `/strategy-runs/status/${encodeURIComponent(status)}`,
    );

    return response.data;
  },

  /**
   * Get strategy runs by type.
   */
  getByType: async (runType) => {
    if (!runType) {
      throw new Error("A strategy run type is required.");
    }

    const response = await api.get(
      `/strategy-runs/type/${encodeURIComponent(runType)}`,
    );

    return response.data;
  },
};

export default strategyRunsAPI;