// Shared type definitions for Patroller Backend

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
  /** Number of aggregated occurrences. 1 = single alert, >1 = aggregated. */
  count?: number;
  /** Logical group key for aggregation (e.g. "process:notepad.exe"). */
  groupKey?: string;
  /** MD5 fingerprint for dedup: type|severity|message. */
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

// Sandbox types (Phase 6)

export interface SandboxResult {
  id: string;
  deviceId: string;
  filePath: string;
  status: 'pending' | 'running' | 'completed' | 'failed';
  report?: unknown;
  analysis?: unknown;
  timestamp: number;
  completedAt?: number;
}

export interface SandboxRunRequest {
  deviceId: string;
  filePath: string;
  timeout?: number;
}

export interface SandboxAnalysis {
  classification: 'SAFE' | 'SUSPICIOUS' | 'MALICIOUS' | 'UNKNOWN';
  confidence: number;
  reasoning: string;
}
