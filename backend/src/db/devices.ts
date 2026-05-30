// Device CRUD operations

import type { SqlValue } from 'sql.js';
import { getDb, saveDb } from './index';
import { Device } from '../types';

export function registerDevice(
  id: string,
  name: string,
  localIp?: string,
  version?: string
): Device {
  const db = getDb();
  const now = Date.now();

  const existing = db.exec('SELECT id FROM devices WHERE id = ?', [id]);
  const config_json = null;

  if (existing.length > 0 && existing[0].values.length > 0) {
    // Update existing
    db.run(
      `UPDATE devices SET name = ?, local_ip = ?, last_seen = ?, status = 'online', version = ? WHERE id = ?`,
      [name, localIp || null, now, version || null, id]
    );
  } else {
    // Insert new
    db.run(
      `INSERT INTO devices (id, name, local_ip, last_seen, status, version, config_json)
       VALUES (?, ?, ?, ?, 'online', ?, ?)`,
      [id, name, localIp || null, now, version || null, config_json]
    );
  }

  saveDb();
  return getDevice(id)!;
}

export function getDevice(id: string): Device | null {
  const db = getDb();
  const result = db.exec(
    'SELECT id, name, tailscale_ip, local_ip, last_seen, status, version, config_json FROM devices WHERE id = ?',
    [id]
  );

  if (result.length === 0 || result[0].values.length === 0) return null;

  return rowToDevice(result[0].values[0]);
}

export function getAllDevices(): Device[] {
  const db = getDb();
  const result = db.exec(
    'SELECT id, name, tailscale_ip, local_ip, last_seen, status, version, config_json FROM devices ORDER BY last_seen DESC'
  );

  if (result.length === 0) return [];
  return result[0].values.map(rowToDevice);
}

export function updateDeviceStatus(
  id: string,
  status: 'online' | 'offline' | 'paused'
): void {
  const db = getDb();
  db.run('UPDATE devices SET status = ? WHERE id = ?', [status, id]);
  saveDb();
}

export function updateLastSeen(id: string): void {
  const db = getDb();
  db.run('UPDATE devices SET last_seen = ?, status = ? WHERE id = ?', [
    Date.now(),
    'online',
    id,
  ]);
  saveDb();
}

export function getOnlineDevices(): Device[] {
  const db = getDb();
  const result = db.exec(
    'SELECT id, name, tailscale_ip, local_ip, last_seen, status, version, config_json FROM devices WHERE status = ? ORDER BY last_seen DESC',
    ['online']
  );

  if (result.length === 0) return [];
  return result[0].values.map(rowToDevice);
}

export function updateDevice(
  id: string,
  updates: { name?: string; config?: unknown }
): Device | null {
  const db = getDb();
  const device = getDevice(id);
  if (!device) return null;

  if (updates.name !== undefined) {
    db.run('UPDATE devices SET name = ? WHERE id = ?', [updates.name, id]);
  }
  if (updates.config !== undefined) {
    db.run('UPDATE devices SET config_json = ? WHERE id = ?', [
      JSON.stringify(updates.config),
      id,
    ]);
  }

  saveDb();
  return getDevice(id);
}

export function deleteDevice(id: string): boolean {
  const db = getDb();
  const existing = db.exec('SELECT id FROM devices WHERE id = ?', [id]);
  if (existing.length === 0 || existing[0].values.length === 0) return false;

  db.run('DELETE FROM devices WHERE id = ?', [id]);
  saveDb();
  return true;
}

export function markStaleDevicesOffline(timeoutMs: number): number {
  const db = getDb();
  const cutoff = Date.now() - timeoutMs;
  db.run(
    "UPDATE devices SET status = 'offline' WHERE status = 'online' AND last_seen < ?",
    [cutoff]
  );
  const modified = db.getRowsModified();
  saveDb();
  return modified;
}

/** Persist a metric snapshot to the metrics_history table. */
export function insertMetrics(
  deviceId: string,
  metrics: Record<string, unknown>,
): void {
  const db = getDb();
  const timestamp = Date.now();
  db.run(
    `INSERT INTO metrics_history (device_id, timestamp, cpu_usage, memory_usage, disk_usage, network_sent, network_recv)
     VALUES (?, ?, ?, ?, ?, ?, ?)`,
    [
      deviceId,
      timestamp,
      (metrics.cpu_percent as number) ?? null,
      (metrics.memory_percent as number) ?? null,
      (metrics.disk_percent as number) ?? null,
      (metrics.network_bytes_sent as number) ?? null,
      (metrics.network_bytes_recv as number) ?? null,
    ],
  );
  saveDb();
}

export interface MetricsRecord {
  timestamp: number;
  cpuUsage: number | null;
  memoryUsage: number | null;
  diskUsage: number | null;
}

/** Query recent metrics_history rows within the given time window. */
export function getMetricsHistory(minutes: number = 60): MetricsRecord[] {
  const db = getDb();
  const cutoff = Date.now() - minutes * 60 * 1000;
  const result = db.exec(
    `SELECT timestamp, cpu_usage, memory_usage, disk_usage
     FROM metrics_history
     WHERE timestamp > ?
     ORDER BY timestamp ASC`,
    [cutoff],
  );
  if (result.length === 0) return [];
  return result[0].values.map((row) => ({
    timestamp: row[0] as number,
    cpuUsage: row[1] as number | null,
    memoryUsage: row[2] as number | null,
    diskUsage: row[3] as number | null,
  }));
}

// Helper

function rowToDevice(row: SqlValue[]): Device {
  return {
    id: row[0] as string,
    name: row[1] as string,
    tailscaleIp: (row[2] as string) || undefined,
    localIp: (row[3] as string) || undefined,
    lastSeen: row[4] as number,
    status: row[5] as Device['status'],
    version: (row[6] as string) || undefined,
    config: row[7] ? JSON.parse(row[7] as string) : undefined,
  };
}
