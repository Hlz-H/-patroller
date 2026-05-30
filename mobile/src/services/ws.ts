import { useEffect, useRef, useCallback, useState } from 'react';
import { useDeviceStore } from '../stores/deviceStore';
import { useAlertStore } from '../stores/alertStore';
import { useAppStore } from '../stores/appStore';
import { WsMessage } from '../types';

const MAX_RECONNECT_DELAY = 30000;
const INITIAL_RECONNECT_DELAY = 1000;

interface UseWebSocketReturn {
  isConnected: boolean;
  reconnect: () => void;
}

export function useWebSocket(): UseWebSocketReturn {
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectDelayRef = useRef(INITIAL_RECONNECT_DELAY);
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [isConnected, setIsConnected] = useState(false);
  const mountedRef = useRef(true);

  const backendUrl = useAppStore((s) => s.config.backendUrl);
  const setOnline = useDeviceStore((s) => s.setOnline);
  const setOffline = useDeviceStore((s) => s.setOffline);
  const updateMetrics = useDeviceStore((s) => s.updateMetrics);
  const addAlert = useAlertStore((s) => s.addAlert);
  const setAppConnected = useAppStore((s) => s.setConnected);

  const connect = useCallback(() => {
    if (!backendUrl) return;

    // Convert http:// to ws://, https:// to wss://
    const wsUrl = backendUrl.replace(/^http/, 'ws') + '/ws';

    try {
      const ws = new WebSocket(wsUrl);
      wsRef.current = ws;

      ws.onopen = () => {
        setIsConnected(true);
        setAppConnected(true);
        reconnectDelayRef.current = INITIAL_RECONNECT_DELAY;
      };

      ws.onmessage = (event) => {
        try {
          const msg: WsMessage = JSON.parse(event.data);
          switch (msg.type) {
            case 'device:online':
              setOnline(msg.deviceId);
              break;
            case 'device:offline':
              setOffline(msg.deviceId);
              break;
            case 'device:metrics':
              updateMetrics(msg.deviceId, msg.data);
              break;
            case 'device:alert':
              addAlert(msg.data);
              break;
          }
        } catch (err) {
          console.error('WS parse error:', err);
        }
      };

      ws.onclose = () => {
        if (!mountedRef.current) return;
        setIsConnected(false);
        setAppConnected(false);
        scheduleReconnect();
      };

      ws.onerror = (err) => {
        console.error('WS error:', err);
      };
    } catch (err) {
      console.error('WS connection failed:', err);
      scheduleReconnect();
    }
  }, [backendUrl, setOnline, setOffline, updateMetrics, addAlert, setAppConnected]);

  const scheduleReconnect = useCallback(() => {
    if (!mountedRef.current) return;
    const delay = reconnectDelayRef.current;
    reconnectTimerRef.current = setTimeout(() => {
      if (mountedRef.current) {
        reconnectDelayRef.current = Math.min(
          delay * 2,
          MAX_RECONNECT_DELAY
        );
        connect();
      }
    }, delay);
  }, [connect]);

  const reconnect = useCallback(() => {
    if (reconnectTimerRef.current) {
      clearTimeout(reconnectTimerRef.current);
    }
    if (wsRef.current) {
      wsRef.current.close();
    }
    reconnectDelayRef.current = INITIAL_RECONNECT_DELAY;
    connect();
  }, [connect]);

  useEffect(() => {
    mountedRef.current = true;
    connect();

    return () => {
      mountedRef.current = false;
      if (reconnectTimerRef.current) {
        clearTimeout(reconnectTimerRef.current);
      }
      if (wsRef.current) {
        wsRef.current.close();
      }
    };
  }, [connect]);

  return { isConnected, reconnect };
}
