const apiUrl = import.meta.env.VITE_API_URL || "http://localhost:8000/api/v1";

export const openTickStream = (symbol, onTick, onError) => {
  const httpUrl = new URL(apiUrl);
  const protocol = httpUrl.protocol === "https:" ? "wss:" : "ws:";
  const websocketUrl = `${protocol}//${httpUrl.host}${httpUrl.pathname}/stream/ticks/${encodeURIComponent(symbol)}`;
  const token = localStorage.getItem("access_token");
  const authProtocol = token ? `bearer.${token}` : "";
  const socket = new WebSocket(websocketUrl, authProtocol ? [authProtocol] : undefined);

  socket.onmessage = (event) => onTick(JSON.parse(event.data));
  socket.onerror = onError;
  return socket;
};
