export interface Device {
  id: string;
  name: string;
  tailscaleIp?: string;
  localIp?: string;
  lastSeen: number;
  status: 'online' | 'offline' | 'paused';
  version?: string;
  config?: unknown;
}

export interface SystemMetrics {
  cpu: {
    percent: number;
    perCore: number[];
  };
  memory: {
    total: number;
    used: number;
    percent: number;
  };
  disk: {
    total: number;
    used: number;
    percent: number;
  };
  network: {
    bytesSent: number;
    bytesRecv: number;
  };
}

export interface MonitorStatus {
  monitors: Record<string, unknown>;
}

export interface Alert {
  id: string;
  deviceId: string;
  timestamp: number;
  type: string;
  severity: string;
  message: string;
  details?: unknown;
  acknowledged?: boolean;
  count?: number;
  groupKey?: string;
  fingerprint?: string;
}

export interface AlertFilters {
  deviceId?: string;
  type?: string;
  severity?: string;
  limit?: number;
  offset?: number;
}

export interface AlertQueryResult {
  alerts: Alert[];
  total: number;
}

// WebSocket message types
export type WsMessage =
  | { type: 'register'; deviceId: string; name: string }
  | { type: 'metrics'; data: SystemMetrics }
  | { type: 'alert'; data: Alert }
  | { type: 'status'; data: MonitorStatus }
  | { type: 'subscribe'; deviceIds: string[] }
  | { type: 'command'; deviceId: string; action: string; payload: unknown }
  | { type: 'device:online'; deviceId: string }
  | { type: 'device:offline'; deviceId: string }
  | { type: 'device:metrics'; deviceId: string; data: SystemMetrics }
  | { type: 'device:alert'; deviceId: string; data: Alert };

export interface PendingCommand {
  id: string;
  deviceId: string;
  action: string;
  payload: unknown;
  timestamp: number;
}

// Mobile-only types
export interface ConnectionConfig {
  backendUrl: string;
  notificationsEnabled: boolean;
  pushToken?: string;
}

export interface AppStats {
  totalDevices: number;
  onlineDevices: number;
  unacknowledgedAlerts: number;
  criticalAlerts: number;
}
