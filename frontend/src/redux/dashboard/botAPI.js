import api from "../../api/axios";

const botAPI = {
  getStatus: async () => (await api.get("/bot/status")).data,
  start: async (payload) => (await api.post("/bot/start", payload)).data,
  stop: async () => (await api.post("/bot/stop")).data,
};

export default botAPI;