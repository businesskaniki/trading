import api from "../../../api/axios";

const engineAPI = {
  // =====================================================
  // GET ENGINE STATUS
  // =====================================================

  getStatus: async () => {
    const response = await api.get("/engine/status");

    return response.data;
  },

  // =====================================================
  // START ENGINE
  // Requires trading account ID
  // =====================================================

  start: async (accountId) => {
    if (!accountId) {
      throw new Error("A trading account ID is required.");
    }

    const response = await api.post("/engine/start", {
      account_id: accountId,
    });

    return response.data;
  },

  // =====================================================
  // STOP ENGINE
  // =====================================================

  stop: async () => {
    const response = await api.post("/engine/stop");

    return response.data;
  },

  // =====================================================
  // PAUSE ENGINE
  // =====================================================

  pause: async () => {
    const response = await api.post("/engine/pause");

    return response.data;
  },

  // =====================================================
  // RESUME / UNPAUSE ENGINE
  // =====================================================

  resume: async () => {
    const response = await api.post("/engine/resume");

    return response.data;
  },
};

export default engineAPI;
