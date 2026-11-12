
import api from "../../api/axios";

const requireAccountId = (accountId) => {
  if (!accountId) {
    throw new Error("A trading account must be selected.");
  }

  return accountId;
};

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
  // Backend requires: account_id (query parameter)
  // =====================================================

  getPositions: async (accountId) => {
    const response = await api.get("/positions/", {
      params: {
        account_id: requireAccountId(accountId),
      },
    });

    return response.data;
  },

  // =====================================================
  // TRADES
  // Backend requires: account_id (query parameter)
  // =====================================================

  getTrades: async (accountId) => {
    const response = await api.get("/trades/", {
      params: {
        account_id: requireAccountId(accountId),
      },
    });

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

  getBrokerAccount: async (accountId) => {
    const response = await api.get("/broker/account", {
      params: accountId ? { account_id: accountId } : undefined,
    });

    return response.data;
  },

  // =====================================================
  // ACCOUNT ANALYTICS
  // =====================================================

  getAccountSummary: async (accountId) => {
    const response = await api.get(
      `/analytics/accounts/${requireAccountId(accountId)}/summary`,
    );

    return response.data;
  },

  getStrategyPerformance: async (accountId) => {
    const response = await api.get(
      `/analytics/accounts/${requireAccountId(accountId)}/strategies`,
    );

    return response.data;
  },

  // =====================================================
  // RISK
  // =====================================================

  getRiskProfile: async (accountId) => {
    const response = await api.get(
      `/risk/accounts/${requireAccountId(accountId)}`,
    );

    return response.data;
  },

  getEffectiveRisk: async (accountId) => {
    const response = await api.get(
      `/risk/accounts/${requireAccountId(accountId)}/effective-risk`,
    );

    return response.data;
  },
};

export default dashboardAPI;
