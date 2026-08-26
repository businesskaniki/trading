import api from "../../api/axios";

const dashboardAPI = {
  // =====================================================
  // TRADING ACCOUNTS
  // =====================================================

  getAccounts: async () => {
    const response = await api.get("/trading-accounts/");

    return response.data;
  },

  getActiveAccounts: async () => {
    const response = await api.get("/trading-accounts/active");

    return response.data;
  },

  getDemoAccounts: async () => {
    const response = await api.get("/trading-accounts/demo");

    return response.data;
  },

  getLiveAccounts: async () => {
    const response = await api.get("/trading-accounts/live");

    return response.data;
  },

  // =====================================================
  // SYMBOLS
  // =====================================================

  getSymbols: async () => {
    const response = await api.get("/symbols/");

    return response.data;
  },

  // =====================================================
  // POSITIONS
  // =====================================================

  getPositions: async () => {
    const response = await api.get("/positions/");

    return response.data;
  },

  // =====================================================
  // TRADES
  // =====================================================

  getTrades: async () => {
    const response = await api.get("/trades/");

    return response.data;
  },

  getLatestTrade: async () => {
    const response = await api.get("/trades/latest");

    return response.data;
  },

  // =====================================================
  // STRATEGY RUNS
  // =====================================================

  getStrategyRuns: async () => {
    const response = await api.get("/strategy-runs/");

    return response.data;
  },

  // =====================================================
  // PERFORMANCE
  // =====================================================

  getLatestPerformance: async () => {
    const response = await api.get("/performance/latest");

    return response.data;
  },

  // =====================================================
  // BROKER
  // =====================================================

  getBrokerAccount: async () => {
    const response = await api.get("/broker/account");

    return response.data;
  },

  // =====================================================
  // ACCOUNT ANALYTICS
  // =====================================================

  getAccountSummary: async (accountId) => {
    const response = await api.get(`/analytics/accounts/${accountId}/summary`);

    return response.data;
  },

  getStrategyPerformance: async (accountId) => {
    const response = await api.get(`/analytics/accounts/${accountId}/strategies`);
    return response.data;
  },

  // =====================================================
  // RISK
  // =====================================================

  getRiskProfile: async (accountId) => {
    const response = await api.get(`/risk/accounts/${accountId}`);

    return response.data;
  },

  getEffectiveRisk: async (accountId) => {
    const response = await api.get(
      `/risk/accounts/${accountId}/effective-risk`,
    );

    return response.data;
  },
};

export default dashboardAPI;
