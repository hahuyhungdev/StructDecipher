/**
 * Tracking hook that reports component lifecycle and interactions
 * to the visualization backend via WebSocket.
 */
import { useEffect, useRef, useCallback } from "react";

const TRACKER_URL = "ws://localhost:8000/ws/tracker";

let sharedWs: WebSocket | null = null;
let pending: string[] = [];
let connectAttempt = 0;

function getWs(): WebSocket | null {
  if (sharedWs && sharedWs.readyState === WebSocket.OPEN) return sharedWs;

  if (!sharedWs || sharedWs.readyState === WebSocket.CLOSED) {
    try {
      sharedWs = new WebSocket(TRACKER_URL);
      sharedWs.onopen = () => {
        connectAttempt = 0;
        // Flush pending
        for (const msg of pending) {
          sharedWs!.send(msg);
        }
        pending = [];
      };
      sharedWs.onclose = () => {
        sharedWs = null;
        // Exponential backoff reconnect
        const delay = Math.min(1000 * 2 ** connectAttempt, 30000);
        connectAttempt++;
        setTimeout(() => getWs(), delay);
      };
      sharedWs.onerror = () => sharedWs?.close();
    } catch {
      return null;
    }
  }
  return sharedWs;
}

function sendEvent(event: {
  eventType: string;
  componentName: string;
  filePath?: string;
  route?: string;
  metadata?: Record<string, unknown>;
}) {
  const payload = JSON.stringify({
    ...event,
    timestamp: new Date().toISOString(),
  });

  const ws = getWs();
  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(payload);
  } else {
    pending.push(payload);
    // Also queue via REST as fallback
    fetch("http://localhost:8000/api/interaction", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: payload,
    }).catch(() => {});
  }
}

/**
 * Hook that tracks component mount/unmount lifecycle.
 * Attach to any component that should appear in the visualization.
 */
export function useTracking(
  componentName: string,
  options?: { filePath?: string; route?: string },
) {
  const nameRef = useRef(componentName);
  nameRef.current = componentName;

  useEffect(() => {
    sendEvent({
      eventType: "mount",
      componentName: nameRef.current,
      filePath: options?.filePath,
      route: options?.route || window.location.pathname,
    });

    return () => {
      sendEvent({
        eventType: "unmount",
        componentName: nameRef.current,
        filePath: options?.filePath,
        route: window.location.pathname,
      });
    };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const trackClick = useCallback((action?: string) => {
    sendEvent({
      eventType: "click",
      componentName: nameRef.current,
      route: window.location.pathname,
      metadata: action ? { action } : undefined,
    });
  }, []);

  const trackApiCall = useCallback((endpoint: string) => {
    sendEvent({
      eventType: "api_call",
      componentName: nameRef.current,
      route: window.location.pathname,
      metadata: { endpoint },
    });
  }, []);

  return { trackClick, trackApiCall };
}
