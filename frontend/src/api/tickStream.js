import { getAccessToken } from "./axios";

const apiUrl = import.meta.env.VITE_API_URL || "http://localhost:8000/api/v1";

export const openTickStream = (symbol, onTick, onError) => {
  const httpUrl = new URL(apiUrl);
  const protocol = httpUrl.protocol === "https:" ? "wss:" : "ws:";
  const websocketUrl = `${protocol}//${httpUrl.host}${httpUrl.pathname}/stream/ticks/${encodeURIComponent(symbol)}`;
  let socket = null;
  let reconnectTimer = null;
  let closed = false;
  let reconnectDelay = 1000;

  const connect = () => {
    if (closed) {
      return;
    }

    const token = getAccessToken();
    const authProtocol = token ? `bearer.${token}` : "";

    socket = new WebSocket(
      websocketUrl,
      authProtocol ? [authProtocol] : undefined,
    );

    socket.onopen = () => {
      reconnectDelay = 1000;
    };

    socket.onmessage = (event) => {
      try {
        onTick(JSON.parse(event.data));
      } catch (error) {
        onError?.(error);
      }
    };

    socket.onerror = (error) => onError?.(error);
    socket.onclose = (event) => {
      socket = null;

      if (closed || event.code === 1008) {
        return;
      }

      reconnectTimer = window.setTimeout(() => {
        reconnectTimer = null;
        reconnectDelay = Math.min(reconnectDelay * 2, 30000);
        connect();
      }, reconnectDelay);
    };
  };

  connect();

  return {
    close: () => {
      closed = true;
      if (reconnectTimer) {
        window.clearTimeout(reconnectTimer);
      }
      socket?.close();
    },
  };
};
