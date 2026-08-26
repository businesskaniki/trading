import api from "../../../api/axios";

const symbolsAPI = {
  getSymbols: async () => {
    const response = await api.get("/symbols/");
    return response.data;
  },

  createSymbol: async (symbolData) => {
    const response = await api.post("/symbols/", symbolData);
    return response.data;
  },

  getSymbol: async (symbolId) => {
    const response = await api.get(`/symbols/${symbolId}`);
    return response.data;
  },

  updateSymbol: async (symbolId, symbolData) => {
    const response = await api.patch(`/symbols/${symbolId}`, symbolData);
    return response.data;
  },

  deleteSymbol: async (symbolId) => {
    await api.delete(`/symbols/${symbolId}`);
    return symbolId;
  },
};

export default symbolsAPI;
