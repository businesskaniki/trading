import api from "../../api/axios";

const riskAPI = {
  getProfile: async (accountId) => (await api.get(`/risk/accounts/${accountId}`)).data,
  updateProfile: async (accountId, data) => (await api.patch(`/risk/accounts/${accountId}`, data)).data,
};

export default riskAPI;