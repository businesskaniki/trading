import api from "../../../api/axios";

const accountsAPI = {
  // =====================================================
  // TRADING ACCOUNTS
  // =====================================================

  getAccounts: async () => {
    const response = await api.get("/trading-accounts/");

    return response.data;
  },

  // =====================================================
  // CREATE ACCOUNT
  // =====================================================

  createAccount: async (accountData) => {
    const response = await api.post("/trading-accounts/", accountData);

    return response.data;
  },

  // =====================================================
  // ACTIVE ACCOUNTS
  // =====================================================

  getActiveAccounts: async () => {
    const response = await api.get("/trading-accounts/active");

    return response.data;
  },

  // =====================================================
  // DEMO ACCOUNTS
  // =====================================================

  getDemoAccounts: async () => {
    const response = await api.get("/trading-accounts/demo");

    return response.data;
  },

  // =====================================================
  // LIVE ACCOUNTS
  // =====================================================

  getLiveAccounts: async () => {
    const response = await api.get("/trading-accounts/live");

    return response.data;
  },

  // =====================================================
  // GET SINGLE ACCOUNT
  // =====================================================

  getAccount: async (accountId) => {
    const response = await api.get(`/trading-accounts/${accountId}`);

    return response.data;
  },

  // =====================================================
  // UPDATE ACCOUNT
  // =====================================================

  updateAccount: async (accountId, accountData) => {
    const response = await api.patch(
      `/trading-accounts/${accountId}`,
      accountData,
    );

    return response.data;
  },

  // =====================================================
  // CONNECT ACCOUNT
  // =====================================================

  connectAccount: async (accountId) => {
    const response = await api.post(`/trading-accounts/${accountId}/connect`);

    return response.data;
  },

  // =====================================================
  // DISCONNECT ACCOUNT
  // =====================================================

  disconnectAccount: async (accountId) => {
    const response = await api.post(
      `/trading-accounts/${accountId}/disconnect`,
    );

    return response.data;
  },

  // =====================================================
  // DELETE ACCOUNT
  // =====================================================

  deleteAccount: async (accountId) => {
    const response = await api.delete(`/trading-accounts/${accountId}`);

    return response.data;
  },
};

export default accountsAPI;
