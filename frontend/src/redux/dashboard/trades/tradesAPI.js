import api from "../../../api/axios";

const tradesAPI = {
  getTrades: async (accountId) =>
    (
      await api.get("/trades/", {
        params: { account_id: accountId },
      })
    ).data,
};

export default tradesAPI;
