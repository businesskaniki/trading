
import { useEffect, useRef, useState } from "react";

const EMPTY_POSITIONS = [];

function buildWebSocketUrl() {
  const apiBase =
    import.meta.env.VITE_API_BASE_URL ||
    "http://localhost:8000/api/v1";

  const url = new URL(apiBase, window.location.href);

  url.protocol = url.protocol === "https:" ? "wss:" : "ws:";
  url.pathname = `${url.pathname.replace(/\/+$/, "")}/positions/ws`;
  url.search = "";
  url.hash = "";

  return url.toString();
}

export function usePositionWebSocket({
  getAccessToken,
  initialPositions = EMPTY_POSITIONS,
  enabled = true,
} = {}) {
  const [positions, setPositions] = useState(initialPositions);
  const [status, setStatus] = useState("disconnected");
  const [error, setError] = useState(null);
  const [lastUpdatedAt, setLastUpdatedAt] = useState(null);

  const receivedSnapshotRef = useRef(false);

  /*
   * Keep the REST positions as the initial display until
   * the first WebSocket snapshot arrives.
   */
  useEffect(() => {
    if (!receivedSnapshotRef.current) {
      setPositions(initialPositions);
    }
  }, [initialPositions]);

  useEffect(() => {
    if (!enabled || typeof getAccessToken !== "function") {
      setStatus("disconnected");
      return undefined;
    }

    let disposed = false;
    let socket = null;
    let reconnectTimer = null;
    let retryCount = 0;

    function scheduleReconnect() {
      if (disposed || reconnectTimer !== null) {
        return;
      }

      const delay = Math.min(
        1000 * 2 ** retryCount,
        10000,
      );

      retryCount += 1;

      reconnectTimer = window.setTimeout(() => {
        reconnectTimer = null;
        connect();
      }, delay);
    }

    function connect() {
      if (disposed) {
        return;
      }

      setStatus(
        retryCount === 0 ? "connecting" : "reconnecting",
      );

      let nextSocket;

      try {
        nextSocket = new WebSocket(buildWebSocketUrl());
        socket = nextSocket;
      } catch (connectionError) {
        setError(
          connectionError.message ||
            "Unable to create the positions WebSocket.",
        );

        scheduleReconnect();
        return;
      }

      nextSocket.onopen = () => {
        let token;

        try {
          token = getAccessToken();
        } catch (tokenError) {
          setError(
            tokenError.message ||
              "Unable to retrieve the access token.",
          );

          nextSocket.close();
          return;
        }

        if (!token) {
          setError(
            "Waiting for an access token to connect to live positions.",
          );

          nextSocket.close();
          return;
        }

        nextSocket.send(
          JSON.stringify({
            type: "auth",
            token,
          }),
        );
      };

      nextSocket.onmessage = (event) => {
        let message;

        try {
          message = JSON.parse(event.data);
        } catch {
          return;
        }

        if (message.type === "authenticated") {
          setStatus("connected");
          setError(null);
          return;
        }

        if (message.type === "positions.snapshot") {
          const nextPositions = Array.isArray(message.positions)
            ? message.positions
            : [];

          receivedSnapshotRef.current = true;
          retryCount = 0;

          setPositions(nextPositions);
          setLastUpdatedAt(message.timestamp || null);
          setError(null);
          setStatus("connected");
          return;
        }

        if (message.type === "positions.error") {
          setError(
            message.message ||
              "Live position synchronization failed.",
          );
        }
      };

      nextSocket.onerror = () => {
        if (!disposed) {
          setStatus("reconnecting");
        }
      };

      nextSocket.onclose = (event) => {
        if (disposed) {
          return;
        }

        setStatus("disconnected");

        if (event.code === 4401) {
          setError(
            "Live positions authentication failed. Check the access token.",
          );
        }

        scheduleReconnect();
      };
    }

    connect();

    return () => {
      disposed = true;

      if (reconnectTimer !== null) {
        window.clearTimeout(reconnectTimer);
      }

      if (socket) {
        socket.onopen = null;
        socket.onmessage = null;
        socket.onerror = null;
        socket.onclose = null;

        socket.close(1000, "Positions page unmounted");
      }
    };
  }, [enabled, getAccessToken]);

  return {
    positions,
    status,
    error,
    lastUpdatedAt,
  };
}
