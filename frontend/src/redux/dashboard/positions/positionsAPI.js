import api from "../../../api/axios";

const positionsAPI = {
  getPositions: async () => (await api.get("/positions/")).data,
  createPosition: async (positionData) => (await api.post("/positions/", positionData)).data,
  getPosition: async (positionId) => (await api.get(`/positions/${positionId}`)).data,
  updatePosition: async (positionId, positionData) => (await api.patch(`/positions/${positionId}`, positionData)).data,
  deletePosition: async (positionId) => { await api.delete(`/positions/${positionId}`); return positionId; },
  updateStatus: async (positionId, statusValue) => (await api.patch(`/positions/${positionId}/status`, null, { params: { status_value: statusValue } })).data,
  syncPositions: async () => (await api.post("/positions/sync")).data,
};

export default positionsAPI;
