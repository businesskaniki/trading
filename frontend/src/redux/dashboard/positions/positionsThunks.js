import { createAsyncThunk } from "@reduxjs/toolkit";
import positionsAPI from "./positionsAPI";

const getErrorMessage = (error, fallback) => {
  const detail = error.response?.data?.detail;
  if (Array.isArray(detail)) return detail.map((item) => item.msg || "Invalid value.").join(" ");
  if (typeof detail === "string") return detail;
  return error.message || fallback;
};
const thunk = (type, request, fallback) => createAsyncThunk(type, async (payload, { rejectWithValue }) => {
  try { return await request(payload); } catch (error) { return rejectWithValue(getErrorMessage(error, fallback)); }
});
export const fetchPositions = thunk("positions/fetchPositions", () => positionsAPI.getPositions(), "Failed to load positions.");
export const createPosition = thunk("positions/createPosition", (data) => positionsAPI.createPosition(data), "Failed to create position.");
export const updatePosition = thunk("positions/updatePosition", ({ positionId, positionData }) => positionsAPI.updatePosition(positionId, positionData), "Failed to update position.");
export const removePosition = thunk("positions/removePosition", (positionId) => positionsAPI.deletePosition(positionId), "Failed to delete position.");
export const updatePositionStatus = thunk("positions/updatePositionStatus", ({ positionId, statusValue }) => positionsAPI.updateStatus(positionId, statusValue), "Failed to update position status.");
export const syncPositions = thunk("positions/syncPositions", () => positionsAPI.syncPositions(), "Failed to sync positions.");
