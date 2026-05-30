/// <reference types="vite/client" />

interface ElectronAPI {
  getAppStatus: () => Promise<{
    version: string;
    electronVersion: string;
    nodeVersion: string;
    platform: string;
    arch: string;
  }>;
  openDevTools: () => Promise<boolean>;
  minimizeWindow: () => Promise<boolean>;
  hideWindow: () => Promise<boolean>;
  showWindow: () => Promise<boolean>;
}

declare global {
  interface Window {
    electronAPI?: ElectronAPI;
  }
}

export {};
