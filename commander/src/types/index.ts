// ==================== Agent Status ====================
export interface AgentStatus {
  agent_id: string;
  agent_name: string;
  version: string;
  uptime: number;
  start_time: string;
  connected_clients: number;
  monitor_enabled: boolean;
  usb_monitor_enabled: boolean;
}

// ==================== System Metrics ====================
export interface SystemMetrics {
  cpu_percent: number;
  cpu_count: number;
  memory_total: number;
  memory_used: number;
  memory_percent: number;
  disk_total: number;
  disk_used: number;
  disk_percent: number;
  network_bytes_sent: number;
  network_bytes_recv: number;
  timestamp: string;
}

export interface DiskInfo {
  device: string;
  mountpoint: string;
  total: number;
  used: number;
  free: number;
  percent: number;
}

export interface NetworkInfo {
  interface: string;
  bytes_sent: number;
  bytes_recv: number;
  packets_sent: number;
  packets_recv: number;
}

// ==================== Process ====================
export interface ProcessInfo {
  pid: number;
  name: string;
  cpu_percent: number;
  memory_percent: number;
  memory_rss: number;
  status: string;
  username: string;
  create_time: number;
  exe_path: string;
  cmdline: string;
  is_blacklisted: boolean;
  is_whitelisted: boolean;
  children_count: number;
}

// ==================== USB ====================
export interface USBDeviceInfo {
  vid: string;
  pid: string;
  serial: string;
  manufacturer: string;
  product: string;
  device_class: string;
  status: 'connected' | 'disconnected' | 'blocked';
  last_event: string;
  event_type: 'connect' | 'disconnect' | 'block';
}

// ==================== Alert ====================
export type AlertSeverity = 'info' | 'warn' | 'critical';
export type AlertType = 'process' | 'usb' | 'network' | 'system';

export interface Alert {
  id: string;
  severity: AlertSeverity;
  type: AlertType;
  title: string;
  message: string;
  details: Record<string, unknown>;
  timestamp: string | number;
  acknowledged?: boolean;
}

// ==================== Config ====================
export interface MonitorConfig {
  process_whitelist: string[];
  process_blacklist: string[];
  usb_blocklist: string[];
  monitor_enabled: boolean;
  usb_monitor_enabled: boolean;
  network_monitor_enabled: boolean;
  check_interval: number;
}

// ==================== API Responses ====================
export interface ApiResponse<T> {
  success: boolean;
  data: T;
  message?: string;
  timestamp: string;
}

export interface SmartControlInfo {
  enabled: boolean;
  health_score?: number;
  summary?: string;
  tuner_multiplier?: number;
}

export interface StatusResponse {
  status: AgentStatus;
  metrics: SystemMetrics;
  smart_control?: SmartControlInfo;
}

export interface ProcessQueryParams {
  page?: number;
  page_size?: number;
  sort_by?: string;
  sort_order?: 'asc' | 'desc';
  search?: string;
  status?: string;
}

export interface ProcessListResponse {
  processes: ProcessInfo[];
  total: number;
  page: number;
  page_size: number;
}

export interface AlertQueryParams {
  page?: number;
  page_size?: number;
  severity?: AlertSeverity;
  type?: AlertType;
  acknowledged?: boolean;
}

export interface AlertListResponse {
  alerts: Alert[];
  total: number;
  page: number;
  page_size: number;
}

// ==================== WebSocket Messages ====================
export interface WSMetricsMessage {
  type: 'metrics';
  data: SystemMetrics;
}

export interface WSAlertMessage {
  type: 'alert';
  data: Alert;
}

export interface WSStatusMessage {
  type: 'status';
  data: AgentStatus;
}

export type WSMessage = WSMetricsMessage | WSAlertMessage | WSStatusMessage;

// ==================== Sandbox ====================
export interface SandboxStatus {
  enabled: boolean;
  available: boolean;
  timeout_seconds: number;
  reason?: string;
}

export interface SandboxResult {
  id: string;
  deviceId?: string;
  filePath: string;
  status: 'pending' | 'running' | 'completed' | 'failed';
  report?: unknown;
  analysis?: unknown;
  timestamp: number;
  completedAt?: number;
}

export interface SandboxRunRequest {
  file_path: string;
  timeout?: number;
}

export interface SandboxRunResponse {
  report?: unknown;
  analysis?: unknown;
  error?: string;
}

// ==================== Component Props ====================
export interface StatusCardProps {
  label: string;
  value: number | string;
  unit?: string;
  color?: string;
  icon?: React.ReactNode;
  loading?: boolean;
}

export interface ProcessTableProps {
  processes: ProcessInfo[];
  loading: boolean;
  onKill: (pid: number) => void;
  onRefresh: () => void;
}

// ==================== Metrics History ====================
export interface MetricsRecord {
  timestamp: number;
  cpuUsage: number | null;
  memoryUsage: number | null;
  diskUsage: number | null;
}

export interface GetMetricsHistoryResponse {
  records: MetricsRecord[];
  total: number;
}
