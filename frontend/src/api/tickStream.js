import { getAccessToken } from "./axios";

const apiUrl = import.meta.env.VITE_API_URL || "http://localhost:8000/api/v1";

export const openTickStream = (accountId, symbolId, onTick, onError) => {
  const httpUrl = new URL(apiUrl);

  const protocol = httpUrl.protocol === "https:" ? "wss:" : "ws:";

  const websocketUrl =
    `${protocol}//${httpUrl.host}${httpUrl.pathname}` +
    `/stream/ticks/${encodeURIComponent(accountId)}` +
    `/${encodeURIComponent(symbolId)}`;

  let socket = null;
  let reconnectTimer = null;
  let closed = false;
  let reconnectDelay = 1000;

  const connect = () => {
    if (closed) return;

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

    socket.onerror = (error) => {
      onError?.(error);
    };

    socket.onclose = (event) => {
      socket = null;

      // Do not retry authentication or authorization failures.
      if (closed || event.code === 1008 || event.code === 1013) {
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
        reconnectTimer = null;
      }

      socket?.close();
      socket = null;
    },
  };
};
