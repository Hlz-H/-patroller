import { create } from 'zustand';
import type {
  AgentStatus,
  SystemMetrics,
  ProcessInfo,
  ProcessQueryParams,
  USBDeviceInfo,
  Alert,
  AlertQueryParams,
  MonitorConfig,
  WSMessage,
  SandboxStatus,
  SmartControlInfo,
  MetricsRecord,
} from '../types';
import * as api from '../api/client';
import { wsClient } from '../api/websocket';

interface AppState {
  // Connection
  isConnected: boolean;

  // Data
  status: AgentStatus | null;
  systemMetrics: SystemMetrics | null;
  processes: ProcessInfo[];
  processTotal: number;
  usbDevices: USBDeviceInfo[];
  alerts: Alert[];
  alertTotal: number;
  unacknowledgedCount: number;
  config: MonitorConfig | null;
  sandboxStatus: SandboxStatus | null;
  sandboxRunning: boolean;
  sandboxLastResult: { report: unknown; analysis: unknown } | null;
  smartControl: SmartControlInfo | null;
  metricsHistory: MetricsRecord[];
  metricsHistoryLoading: boolean;

  // Loading states
  loading: {
    status: boolean;
    processes: boolean;
    usb: boolean;
    alerts: boolean;
    config: boolean;
    sandbox: boolean;
  };

  // Actions
  setConnected: (connected: boolean) => void;
  updateMetrics: (metrics: SystemMetrics) => void;
  addAlert: (alert: Alert) => void;
  updateStatus: (status: AgentStatus) => void;

  fetchStatus: () => Promise<void>;
  fetchProcesses: (params?: ProcessQueryParams) => Promise<void>;
  fetchUSB: () => Promise<void>;
  fetchAlerts: (params?: AlertQueryParams) => Promise<void>;
  fetchConfig: () => Promise<void>;
  fetchSandboxStatus: () => Promise<void>;
  runSandbox: (filePath: string, timeout?: number) => Promise<boolean>;

  killProcess: (pid: number) => Promise<boolean>;
  saveConfig: (config: Partial<MonitorConfig>) => Promise<boolean>;
  fetchMetricsHistory: (minutes?: number) => Promise<void>;

  connectWebSocket: () => void;
  disconnectWebSocket: () => void;
}

export const useStore = create<AppState>((set, get) => ({
  isConnected: false,
  status: null,
  systemMetrics: null,
  processes: [],
  processTotal: 0,
  usbDevices: [],
  alerts: [],
  alertTotal: 0,
  unacknowledgedCount: 0,
  config: null,
  sandboxStatus: null,
  sandboxRunning: false,
  sandboxLastResult: null,
  smartControl: null,
  metricsHistory: [],
  metricsHistoryLoading: false,
  loading: {
    status: false,
    processes: false,
    usb: false,
    alerts: false,
    config: false,
    sandbox: false,
  },

  setConnected: (connected) => set({ isConnected: connected }),

  updateMetrics: (metrics) => set({ systemMetrics: metrics }),

  addAlert: (alert) =>
    set((state) => {
      const newAlerts = [alert, ...state.alerts].slice(0, 500);
      return {
        alerts: newAlerts,
        alertTotal: state.alertTotal + 1,
        unacknowledgedCount: state.unacknowledgedCount + (alert.acknowledged ? 0 : 1),
      };
    }),

  updateStatus: (status) => set({ status }),

  fetchStatus: async () => {
    set((s) => ({ loading: { ...s.loading, status: true } }));
    try {
      const result = await api.getStatus();
      set({
        status: result.status,
        systemMetrics: result.metrics,
        smartControl: result.smart_control || null,
        loading: { ...get().loading, status: false },
      });
    } catch {
      set((s) => ({ loading: { ...s.loading, status: false } }));
    }
  },

  fetchProcesses: async (params) => {
    set((s) => ({ loading: { ...s.loading, processes: true } }));
    try {
      const result = await api.getProcesses(params);
      set({
        processes: result.processes,
        processTotal: result.total,
        loading: { ...get().loading, processes: false },
      });
    } catch {
      set((s) => ({ loading: { ...s.loading, processes: false } }));
    }
  },

  fetchUSB: async () => {
    set((s) => ({ loading: { ...s.loading, usb: true } }));
    try {
      const devices = await api.getUSB();
      set({
        usbDevices: devices,
        loading: { ...get().loading, usb: false },
      });
    } catch {
      set((s) => ({ loading: { ...s.loading, usb: false } }));
    }
  },

  fetchAlerts: async (params) => {
    set((s) => ({ loading: { ...s.loading, alerts: true } }));
    try {
      const result = await api.getAlerts(params);
      set({
        alerts: result.alerts,
        alertTotal: result.total,
        unacknowledgedCount: result.alerts.filter((a) => !a.acknowledged).length,
        loading: { ...get().loading, alerts: false },
      });
    } catch {
      set((s) => ({ loading: { ...s.loading, alerts: false } }));
    }
  },

  fetchConfig: async () => {
    set((s) => ({ loading: { ...s.loading, config: true } }));
    try {
      // Now reads full config from the Agent's GET /api/v1/config endpoint
      // (whitelist, blacklist, blocklist, toggle states, etc.)
      const cfg = await api.getAgentConfig();
      set({
        config: cfg,
        loading: { ...get().loading, config: false },
      });
    } catch {
      set((s) => ({ loading: { ...s.loading, config: false } }));
    }
  },

  killProcess: async (pid) => {
    try {
      await api.killProcess(pid);
      return true;
    } catch {
      return false;
    }
  },

  saveConfig: async (partial) => {
    try {
      // Merge with existing config so partial updates don't reset unseen fields
      const current = get().config ?? {
        process_whitelist: [],
        process_blacklist: [],
        usb_blocklist: [],
        monitor_enabled: true,
        usb_monitor_enabled: true,
        network_monitor_enabled: true,
        check_interval: 5,
      };
      const merged = { ...current, ...partial };
      const result = await api.updateConfig(merged);
      set({ config: result });
      return true;
    } catch {
      return false;
    }
  },

  fetchMetricsHistory: async (minutes = 60) => {
    set({ metricsHistoryLoading: true });
    try {
      const { records } = await api.getMetricsHistory(minutes);
      set({ metricsHistory: records, metricsHistoryLoading: false });
    } catch {
      set({ metricsHistory: [], metricsHistoryLoading: false });
    }
  },

  fetchSandboxStatus: async () => {
    set((s) => ({ loading: { ...s.loading, sandbox: true } }));
    try {
      const status = await api.getSandboxStatus();
      set({
        sandboxStatus: status,
        loading: { ...get().loading, sandbox: false },
      });
    } catch {
      set((s) => ({ loading: { ...s.loading, sandbox: false } }));
    }
  },

  runSandbox: async (filePath, timeout) => {
    set({ sandboxRunning: true });
    try {
      const result = await api.runSandbox(filePath, timeout);
      set({ sandboxLastResult: result, sandboxRunning: false });
      return true;
    } catch {
      set({ sandboxRunning: false });
      return false;
    }
  },

  connectWebSocket: () => {
    wsClient.onMessage((msg: WSMessage) => {
      const store = get();
      switch (msg.type) {
        case 'metrics':
          store.updateMetrics(msg.data);
          store.setConnected(true);
          break;
        case 'alert':
          store.addAlert(msg.data);
          store.setConnected(true);
          break;
        case 'status':
          store.setConnected(true);
          if (msg.data) {
            store.updateStatus(msg.data);
          }
          break;
      }
    });
    wsClient.connect();
  },

  disconnectWebSocket: () => {
    wsClient.destroy();
    set({ isConnected: false });
  },
}));
