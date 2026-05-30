import { create } from 'zustand';
import { Device, SystemMetrics } from '../types';
import * as api from '../services/api';

interface DeviceStore {
  devices: Device[];
  metricsMap: Record<string, SystemMetrics>;
  loading: boolean;
  error: string | null;

  fetchDevices: () => Promise<void>;
  getDevice: (id: string) => Device | undefined;
  setOnline: (deviceId: string) => void;
  setOffline: (deviceId: string) => void;
  updateMetrics: (deviceId: string, metrics: SystemMetrics) => void;
  updateDevice: (id: string, data: Partial<Device>) => void;
  removeDevice: (id: string) => void;
}

export const useDeviceStore = create<DeviceStore>((set, get) => ({
  devices: [],
  metricsMap: {},
  loading: false,
  error: null,

  fetchDevices: async () => {
    set({ loading: true, error: null });
    try {
      const devices = await api.devices.listDevices();
      if (devices === null) {
        set({ loading: false, error: 'Failed to fetch devices' });
        return;
      }
      set({ devices, loading: false });
    } catch (err) {
      set({
        loading: false,
        error: err instanceof Error ? err.message : 'Unknown error fetching devices',
      });
    }
  },

  getDevice: (id: string) => {
    return get().devices.find((d) => d.id === id);
  },

  setOnline: (deviceId: string) => {
    set((state) => ({
      devices: state.devices.map((d) =>
        d.id === deviceId ? { ...d, status: 'online', lastSeen: Date.now() } : d,
      ),
    }));
  },

  setOffline: (deviceId: string) => {
    set((state) => ({
      devices: state.devices.map((d) =>
        d.id === deviceId ? { ...d, status: 'offline' } : d,
      ),
    }));
  },

  updateMetrics: (deviceId: string, metrics: SystemMetrics) => {
    set((state) => ({
      metricsMap: { ...state.metricsMap, [deviceId]: metrics },
    }));
  },

  updateDevice: (id: string, data: Partial<Device>) => {
    set((state) => ({
      devices: state.devices.map((d) =>
        d.id === id ? { ...d, ...data } : d,
      ),
    }));
  },

  removeDevice: (id: string) => {
    set((state) => ({
      devices: state.devices.filter((d) => d.id !== id),
      metricsMap: (() => {
        const { [id]: _, ...rest } = state.metricsMap;
        return rest;
      })(),
    }));
  },
}));
