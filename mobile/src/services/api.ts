import axios, { AxiosInstance } from 'axios';
import type { Device, Alert, AlertFilters, AlertQueryResult } from '../types';

// ---------------------------------------------------------------------------
// Axios instance
// ---------------------------------------------------------------------------

let api: AxiosInstance = axios.create({
  baseURL: 'http://localhost:3099',
  timeout: 10_000,
  headers: { 'Content-Type': 'application/json' },
});

// ---------------------------------------------------------------------------
// Configuration
// ---------------------------------------------------------------------------

/**
 * Update the base URL used by all subsequent API calls.
 *
 * @param baseUrl  Full backend URL, e.g. "http://192.168.1.50:3099"
 */
export function configureApi(baseUrl: string): void {
  api = axios.create({
    baseURL: baseUrl,
    timeout: 10_000,
    headers: { 'Content-Type': 'application/json' },
  });
}

// ---------------------------------------------------------------------------
// Health check
// ---------------------------------------------------------------------------

/**
 * Verify connectivity to the backend by hitting the /health endpoint.
 *
 * @returns `true` when the backend responds with HTTP 200, otherwise `false`.
 */
export async function testConnection(): Promise<boolean> {
  try {
    const res = await api.get('/health');
    return res.status === 200;
  } catch (err) {
    console.error('[api] testConnection failed', err);
    return false;
  }
}

// ---------------------------------------------------------------------------
// Devices API
// ---------------------------------------------------------------------------

export const devices = {
  /**
   * Fetch every registered device.
   *
   * @returns Array of devices, or `null` on failure.
   */
  async listDevices(): Promise<Device[] | null> {
    try {
      const { data } = await api.get<Device[]>('/api/v1/devices');
      return data;
    } catch (err) {
      console.error('[api] listDevices failed', err);
      return null;
    }
  },

  /**
   * Fetch devices that are currently online.
   *
   * @returns Array of online devices, or `null` on failure.
   */
  async getOnlineDevices(): Promise<Device[] | null> {
    try {
      const { data } = await api.get<Device[]>('/api/v1/devices/online');
      return data;
    } catch (err) {
      console.error('[api] getOnlineDevices failed', err);
      return null;
    }
  },

  /**
   * Fetch a single device by its ID.
   *
   * @param id  Device identifier.
   * @returns The device, or `null` on failure (including 404).
   */
  async getDevice(id: string): Promise<Device | null> {
    try {
      const { data } = await api.get<Device>(`/api/v1/devices/${id}`);
      return data;
    } catch (err) {
      console.error('[api] getDevice failed', err);
      return null;
    }
  },

  /**
   * Update a device's name and/or config.
   *
   * @param id    Device identifier.
   * @param data  Partial device payload (e.g. `{ name: "New Name" }`).
   * @returns The updated device, or `null` on failure.
   */
  async updateDevice(
    id: string,
    data: Partial<Pick<Device, 'name' | 'config'>>,
  ): Promise<Device | null> {
    try {
      const { data: updated } = await api.put<Device>(
        `/api/v1/devices/${id}`,
        data,
      );
      return updated;
    } catch (err) {
      console.error('[api] updateDevice failed', err);
      return null;
    }
  },

  /**
   * Remove a device.
   *
   * @param id  Device identifier.
   * @returns `true` on success, `false` on failure.
   */
  async deleteDevice(id: string): Promise<boolean> {
    try {
      await api.delete(`/api/v1/devices/${id}`);
      return true;
    } catch (err) {
      console.error('[api] deleteDevice failed', err);
      return false;
    }
  },
};

// ---------------------------------------------------------------------------
// Alerts API
// ---------------------------------------------------------------------------

export const alerts = {
  /**
   * Query alerts with optional filters.
   *
   * @param filters  Optional deviceId, type, severity, limit, offset.
   * @returns Paginated alert result, or `null` on failure.
   */
  async listAlerts(filters?: AlertFilters): Promise<AlertQueryResult | null> {
    try {
      const { data } = await api.get<AlertQueryResult>('/api/v1/alerts', {
        params: filters,
      });
      return data;
    } catch (err) {
      console.error('[api] listAlerts failed', err);
      return null;
    }
  },

  /**
   * Fetch all alerts that have not yet been acknowledged.
   *
   * @returns Array of unacknowledged alerts, or `null` on failure.
   */
  async listUnacknowledged(): Promise<Alert[] | null> {
    try {
      const { data } = await api.get<Alert[]>(
        '/api/v1/alerts/unacknowledged',
      );
      return data;
    } catch (err) {
      console.error('[api] listUnacknowledged failed', err);
      return null;
    }
  },

  /**
   * Acknowledge an alert.
   *
   * @param id  Alert identifier.
   * @returns `true` on success, `false` on failure.
   */
  async acknowledgeAlert(id: string): Promise<boolean> {
    try {
      await api.post(`/api/v1/alerts/${id}/acknowledge`);
      return true;
    } catch (err) {
      console.error('[api] acknowledgeAlert failed', err);
      return false;
    }
  },
};

// ---------------------------------------------------------------------------
// Relay API
// ---------------------------------------------------------------------------

export const relay = {
  /**
   * Send an action command to a device via the backend relay.
   *
   * @param deviceId  Target device identifier.
   * @param action    Action name (e.g. "restart", "shutdown").
   * @param payload   Optional action-specific payload.
   * @returns `true` on success, `false` on failure.
   */
  async sendCommand(
    deviceId: string,
    action: string,
    payload?: unknown,
  ): Promise<boolean> {
    try {
      await api.post('/api/v1/relay/command', {
        deviceId,
        action,
        payload: payload ?? null,
      });
      return true;
    } catch (err) {
      console.error('[api] sendCommand failed', err);
      return false;
    }
  },
};

// ---------------------------------------------------------------------------
// Push Notification API
// ---------------------------------------------------------------------------

export const push = {
  /**
   * Register this device's Expo push token with the backend so it can
   * receive push notifications when alerts are triggered.
   *
   * @param token    The Expo push token string.
   * @param deviceId Optional device identifier for the backend to associate.
   * @returns `true` on success, `false` on failure.
   */
  async registerToken(token: string, deviceId?: string): Promise<boolean> {
    try {
      await api.post('/api/v1/notifications/register', {
        token,
        deviceId: deviceId || undefined,
      });
      return true;
    } catch (err) {
      console.error('[api] registerPushToken failed', err);
      return false;
    }
  },
};
