import { useEffect, useRef, useState, useCallback } from "react";
import type { InteractionEvent, WsMessage } from "../types";

const WS_URL =
  (window.location.protocol === "https:" ? "wss://" : "ws://") +
  window.location.host +
  "/ws/dashboard";

export function useWebSocket() {
  const wsRef = useRef<WebSocket | null>(null);
  const [connected, setConnected] = useState(false);
  const [activeNodes, setActiveNodes] = useState<string[]>([]);
  const [events, setEvents] = useState<InteractionEvent[]>([]);
  const [structureUpdate, setStructureUpdate] = useState<unknown>(null);
  const reconnectTimer = useRef<ReturnType<typeof setTimeout>>();

  const connect = useCallback(() => {
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) return;

    try {
      const ws = new WebSocket(WS_URL);
      wsRef.current = ws;

      ws.onopen = () => setConnected(true);

      ws.onmessage = (ev) => {
        try {
          const msg: WsMessage = JSON.parse(ev.data);
          if (msg.activeNodes) setActiveNodes(msg.activeNodes);

          if (msg.type === "interaction" && msg.data) {
            setEvents((prev) => [
              ...prev.slice(-99),
              msg.data as InteractionEvent,
            ]);
          }
          if (msg.type === "structure_update" && msg.data) {
            setStructureUpdate(msg.data);
          }
          if (msg.type === "clear") {
            setEvents([]);
            setActiveNodes([]);
          }
        } catch {
          /* non-JSON pong */
        }
      };

      ws.onclose = () => {
        setConnected(false);
        reconnectTimer.current = setTimeout(connect, 3000);
      };

      ws.onerror = () => ws.close();
    } catch {
      reconnectTimer.current = setTimeout(connect, 3000);
    }
  }, []);

  useEffect(() => {
    connect();
    // Ping keepalive
    const interval = setInterval(() => {
      if (wsRef.current?.readyState === WebSocket.OPEN) {
        wsRef.current.send("ping");
      }
    }, 25000);
    return () => {
      clearInterval(interval);
      clearTimeout(reconnectTimer.current);
      wsRef.current?.close();
    };
  }, [connect]);

  return { connected, activeNodes, events, structureUpdate };
}
