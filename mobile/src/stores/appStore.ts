import { create } from 'zustand';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { ConnectionConfig } from '../types';
import { configureApi, testConnection } from '../services/api';

const STORAGE_KEY = 'patroller_config';

const DEFAULT_CONFIG: ConnectionConfig = {
  backendUrl: 'http://localhost:3099',
  notificationsEnabled: true,
};

interface AppStore {
  config: ConnectionConfig;
  isConnected: boolean;
  isConnecting: boolean;

  loadConfig: () => Promise<void>;
  saveConfig: (config: ConnectionConfig) => Promise<void>;
  testAndConnect: () => Promise<boolean>;
  setConnected: (connected: boolean) => void;
}

export const useAppStore = create<AppStore>((set, get) => ({
  config: DEFAULT_CONFIG,
  isConnected: false,
  isConnecting: false,

  loadConfig: async () => {
    try {
      const stored = await AsyncStorage.getItem(STORAGE_KEY);
      if (stored) {
        const config: ConnectionConfig = JSON.parse(stored);
        configureApi(config.backendUrl);
        set({ config });
      }
    } catch (err) {
      console.error('Failed to load config:', err);
    }
  },

  saveConfig: async (config: ConnectionConfig) => {
    try {
      configureApi(config.backendUrl);
      await AsyncStorage.setItem(STORAGE_KEY, JSON.stringify(config));
      set({ config });
    } catch (err) {
      console.error('Failed to save config:', err);
    }
  },

  testAndConnect: async () => {
    set({ isConnecting: true });
    try {
      const { config } = get();
      configureApi(config.backendUrl);
      const ok = await testConnection();
      if (ok) {
        await AsyncStorage.setItem(STORAGE_KEY, JSON.stringify(config));
        set({ isConnected: true, isConnecting: false });
        return true;
      }
      set({ isConnected: false, isConnecting: false });
      return false;
    } catch (err) {
      set({ isConnected: false, isConnecting: false });
      return false;
    }
  },

  setConnected: (connected: boolean) => {
    set({ isConnected: connected });
  },
}));
