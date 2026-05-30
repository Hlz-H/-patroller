import axios, { AxiosError } from 'axios';
import type {
  StatusResponse,
  SystemMetrics,
  ProcessInfo,
  ProcessQueryParams,
  ProcessListResponse,
  USBDeviceInfo,
  Alert,
  AlertQueryParams,
  AlertListResponse,
  MonitorConfig,
  AgentStatus,
  SandboxStatus,
  GetMetricsHistoryResponse,
} from '../types';

// ── Agent client (localhost:8099) ──────────────────────────────────────
const agentClient = axios.create({
  baseURL: 'http://localhost:8099',
  timeout: 10000,
  headers: { 'Content-Type': 'application/json' },
});

agentClient.interceptors.response.use(
  (response) => response,
  (error: AxiosError) => {
    const message = error.response
      ? `服务器错误: ${error.response.status}`
      : error.code === 'ECONNREFUSED'
        ? '无法连接到 Agent 服务，请确认 Agent 已启动'
        : `网络错误: ${error.message}`;
    return Promise.reject(new Error(message));
  }
);

// ── Backend client (localhost:3099) for alert ack ──────────────────────
const backendClient = axios.create({
  baseURL: 'http://localhost:3099',
  timeout: 10000,
  headers: { 'Content-Type': 'application/json' },
});

// ── API functions ──────────────────────────────────────────────────────

/** GET /api/v1/status → StatusResponse (Agent raw → transformed) */
export async function getStatus(): Promise<StatusResponse> {
  const { data } = await agentClient.get('/api/v1/status');
  // Agent returns: { status, version, uptime_seconds, monitors: { system_resource, process, usb } }

  const monitors = data.monitors || {};

  const status: AgentStatus = {
    agent_id: 'agent-1',
    agent_name: '巡查者 Agent',
    version: data.version || '0.0.0',
    uptime: data.uptime_seconds ?? 0,
    start_time: data.uptime_seconds
      ? new Date(Date.now() - data.uptime_seconds * 1000).toISOString()
      : new Date().toISOString(),
    connected_clients: 0,
    monitor_enabled: monitors.system_resource?.enabled ?? true,
    usb_monitor_enabled: monitors.usb?.enabled ?? true,
  };

  const metrics = await getSystem();
  return {
    status,
    metrics,
    smart_control: data.smart_control || { enabled: false },
  };
}

/** GET /api/v1/system → SystemMetrics (Agent returns raw dict directly) */
export async function getSystem(): Promise<SystemMetrics> {
  const { data } = await agentClient.get('/api/v1/system');
  return data;
}

/** GET /api/v1/processes → ProcessListResponse */
export async function getProcesses(
  params?: ProcessQueryParams
): Promise<ProcessListResponse> {
  const queryParams: Record<string, unknown> = {};

  if (params?.page !== undefined && params?.page_size !== undefined) {
    queryParams.offset = (params.page - 1) * params.page_size;
    queryParams.limit = params.page_size;
  } else {
    queryParams.offset = 0;
    queryParams.limit = params?.page_size ?? 50;
  }

  const { data } = await agentClient.get('/api/v1/processes', {
    params: queryParams,
  });
  // Agent returns: { total, offset, limit, processes: [...] }

  return {
    processes: data.processes || [],
    total: data.total ?? 0,
    page: data.limit > 0 ? Math.floor(data.offset / data.limit) + 1 : 1,
    page_size: data.limit ?? 50,
  };
}

/** POST /api/v1/process/kill/{pid} → { success: boolean } */
export async function killProcess(
  pid: number
): Promise<{ success: boolean }> {
  const { data } = await agentClient.post(`/api/v1/process/kill/${pid}`);
  return { success: data.success };
}

/** GET /api/v1/usb → USBDeviceInfo[] */
export async function getUSB(): Promise<USBDeviceInfo[]> {
  const { data } = await agentClient.get('/api/v1/usb');
  // Agent returns: { devices: [...], events: [...] }
  return data.devices || [];
}

/** GET /api/v1/alerts → AlertListResponse */
export async function getAlerts(
  params?: AlertQueryParams
): Promise<AlertListResponse> {
  const queryParams: Record<string, unknown> = {};

  if (params?.page !== undefined && params?.page_size !== undefined) {
    queryParams.offset = (params.page - 1) * params.page_size;
    queryParams.limit = params.page_size;
  } else {
    queryParams.limit = params?.page_size ?? 50;
  }

  const { data } = await agentClient.get('/api/v1/alerts', {
    params: queryParams,
  });
  // Agent returns: { total, alerts: [{ alert_id, timestamp, type, severity, message, details }] }

  const alerts: Alert[] = (data.alerts || []).map(
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    (raw: any): Alert => ({
      id: String(raw.alert_id ?? ''),
      severity: raw.severity || 'info',
      type: raw.type || 'system',
      title: (raw.message || '').split('\n')[0] || raw.message || 'Unknown',
      message: raw.message || '',
      details: raw.details || {},
      timestamp: raw.timestamp ?? Date.now(),
    })
  );

  return {
    alerts,
    total: data.total ?? 0,
    page: params?.page || 1,
    page_size: params?.page_size || 50,
  };
}

/** PATCH /api/v1/alerts/:id/ack → acknowledge an alert (via Backend) */
export async function acknowledgeAlert(
  alertId: string
): Promise<{ success: boolean }> {
  const { data } = await backendClient.patch(
    `/api/v1/alerts/${alertId}/ack`
  );
  return { success: data.success ?? true };
}

/** GET /api/v1/metrics/history → metrics records (via Backend) */
export async function getMetricsHistory(
  minutes: number = 60
): Promise<GetMetricsHistoryResponse> {
  const { data } = await backendClient.get('/api/v1/metrics/history', {
    params: { minutes },
  });
  return data;
}

/** GET /api/v1/config → MonitorConfig (via Agent) */
export async function getAgentConfig(): Promise<MonitorConfig> {
  const { data } = await agentClient.get('/api/v1/config');
  return {
    process_whitelist: data.process_whitelist || [],
    process_blacklist: data.process_blacklist || [],
    usb_blocklist: data.usb_blocklist || [],
    monitor_enabled: data.monitor_enabled ?? true,
    usb_monitor_enabled: data.usb_monitor_enabled ?? true,
    network_monitor_enabled: data.network_monitor_enabled ?? true,
    check_interval: data.check_interval ?? 5,
  };
}

/** POST /api/v1/config → MonitorConfig */
export async function updateConfig(
  config: Partial<MonitorConfig>
): Promise<MonitorConfig> {
  // Transform flat MonitorConfig into Agent's nested format
  const body = {
    process: {
      whitelist: config.process_whitelist || [],
      blacklist: config.process_blacklist || [],
    },
    usb: {
      blocklist: config.usb_blocklist || [],
    },
  };

  await agentClient.post('/api/v1/config', body);

  // Return the config as MonitorConfig
  return {
    process_whitelist: config.process_whitelist || [],
    process_blacklist: config.process_blacklist || [],
    usb_blocklist: config.usb_blocklist || [],
    monitor_enabled: config.monitor_enabled ?? true,
    usb_monitor_enabled: config.usb_monitor_enabled ?? true,
    network_monitor_enabled: config.network_monitor_enabled ?? true,
    check_interval: config.check_interval ?? 5,
  };
}

// ── Sandbox API ──────────────────────────────────────────────────────

/** GET /api/v1/sandbox/status → SandboxStatus */
export async function getSandboxStatus(): Promise<SandboxStatus> {
  const { data } = await agentClient.get('/api/v1/sandbox/status');
  return data;
}

/** POST /api/v1/sandbox/run-and-analyze → { report, analysis } */
export async function runSandbox(
  filePath: string,
  timeout?: number
): Promise<{ report: unknown; analysis: unknown }> {
  const { data } = await agentClient.post('/api/v1/sandbox/run-and-analyze', {
    file_path: filePath,
    timeout,
  });
  if (data.error) throw new Error(data.error);
  return data;
}

export { agentClient as default };
