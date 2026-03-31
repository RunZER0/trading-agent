import { useState, useEffect, useRef } from 'react';

interface WSMessage {
  type: string;
  data: unknown;
}

export function useWebSocket(url: string) {
  const [lastMessage, setLastMessage] = useState<WSMessage | null>(null);
  const [connected, setConnected] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}${url}`;
    const ws = new WebSocket(wsUrl);
    wsRef.current = ws;

    ws.onopen = () => setConnected(true);
    ws.onclose = () => {
      setConnected(false);
      // Reconnect after 5 seconds
      setTimeout(() => {
        wsRef.current = new WebSocket(wsUrl);
      }, 5000);
    };
    ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data);
        setLastMessage(msg);
      } catch {
        // ignore parse errors
      }
    };

    return () => { ws.close(); };
  }, [url]);

  return { lastMessage, connected };
}
