import api from "../../../api/axios";

const tradesAPI = {
  getTrades: async () => (await api.get("/trades/")).data,
};

export default tradesAPI;