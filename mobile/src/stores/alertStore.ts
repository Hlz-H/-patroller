import { create } from 'zustand';
import { Alert, AlertFilters } from '../types';
import * as api from '../services/api';

interface AlertStore {
  alerts: Alert[];
  total: number;
  loading: boolean;
  error: string | null;
  filters: AlertFilters;

  fetchAlerts: (filters?: AlertFilters) => Promise<void>;
  addAlert: (alert: Alert) => void;
  acknowledgeAlert: (id: string) => Promise<void>;
  setFilters: (filters: AlertFilters) => void;
  getUnacknowledgedCount: () => number;
  getCriticalCount: () => number;
}

export const useAlertStore = create<AlertStore>((set, get) => ({
  alerts: [],
  total: 0,
  loading: false,
  error: null,
  filters: {},

  fetchAlerts: async (filters?: AlertFilters) => {
    set({ loading: true, error: null });
    try {
      const mergedFilters = { ...get().filters, ...filters };
      const result = await api.alerts.listAlerts(mergedFilters);
      if (result) {
        set({ alerts: result.alerts, total: result.total, loading: false });
      } else {
        set({ error: 'Failed to fetch alerts', loading: false });
      }
    } catch (err) {
      set({ error: 'Failed to fetch alerts', loading: false });
    }
  },

  addAlert: (alert: Alert) => {
    set((state) => ({
      alerts: [alert, ...state.alerts],
      total: state.total + 1,
    }));
  },

  acknowledgeAlert: async (id: string) => {
    try {
      const success = await api.alerts.acknowledgeAlert(id);
      if (success) {
        set((state) => ({
          alerts: state.alerts.map((a) =>
            a.id === id ? { ...a, acknowledged: true } : a
          ),
        }));
      }
    } catch (err) {
      console.error('Failed to acknowledge alert:', err);
    }
  },

  setFilters: (filters: AlertFilters) => {
    set({ filters });
    get().fetchAlerts(filters);
  },

  getUnacknowledgedCount: () => {
    return get().alerts.filter((a) => !a.acknowledged).length;
  },

  getCriticalCount: () => {
    return get().alerts.filter((a) => a.severity === 'critical').length;
  },
}));
