// Alert storage operations

import type { SqlValue } from 'sql.js';
import { getDb, saveDb } from './index';
import { Alert, AlertFilters, AlertQueryResult } from '../types';
interface StoreAlertData {
  id?: string;
  deviceId: string;
  timestamp?: number;
  type: string;
  severity: string;
  message: string;
  details?: unknown;
  acknowledged?: boolean;
  groupKey?: string;
  fingerprint?: string;
  count?: number;
}

export function storeAlert(data: StoreAlertData): Alert {
  const db = getDb();

  // Aggregation: if groupKey is set, try to update an existing alert within 60s window
  if (data.groupKey) {
    const existing = db.exec(
      'SELECT * FROM alerts WHERE group_key = ? AND device_id = ? ORDER BY timestamp DESC LIMIT 1',
      [data.groupKey, data.deviceId]
    );
    if (existing.length > 0 && existing[0].values.length > 0) {
      const existingRow = existing[0].values[0];
      const existingTimestamp = existingRow[2] as number;
      const now = data.timestamp || Date.now();

      if (now - existingTimestamp < 60000) {
        // Within aggregation window: update existing alert
        const existingCount = (existingRow[10] as number) || 1;
        const newCount = existingCount + 1;

        // Merge details: spread new details over existing
        let mergedDetails: Record<string, unknown> = {};
        if (existingRow[6]) {
          mergedDetails = JSON.parse(existingRow[6] as string);
        }
        if (data.details) {
          mergedDetails = { ...mergedDetails, ...(data.details as Record<string, unknown>) };
        }

        db.run(
          'UPDATE alerts SET count = ?, timestamp = ?, details_json = ? WHERE id = ?',
          [newCount, now, JSON.stringify(mergedDetails), existingRow[0]]
        );
        saveDb();

        return {
          id: existingRow[0] as string,
          deviceId: existingRow[1] as string,
          timestamp: now,
          type: existingRow[3] as string,
          severity: existingRow[4] as string,
          message: existingRow[5] as string,
          details: mergedDetails,
          acknowledged: existingRow[7] === 1,
          count: newCount,
          groupKey: existingRow[8] as string,
          fingerprint: existingRow[9] as string,
        };
      }
    }
  }

  // No aggregation match: insert new alert
  const id = data.id || crypto.randomUUID();
  const timestamp = data.timestamp || Date.now();
  const details_json = data.details ? JSON.stringify(data.details) : null;
  const count = data.count || 1;

  db.run(
    `INSERT INTO alerts (id, device_id, timestamp, type, severity, message, details_json, acknowledged, group_key, fingerprint, count)
     VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?, ?, ?)`,
    [id, data.deviceId, timestamp, data.type, data.severity, data.message, details_json, data.groupKey || null, data.fingerprint || null, count]
  );

  saveDb();

  return {
    id,
    deviceId: data.deviceId,
    timestamp,
    type: data.type,
    severity: data.severity,
    message: data.message,
    details: data.details,
    acknowledged: false,
    count,
    groupKey: data.groupKey,
    fingerprint: data.fingerprint,
  };
}

export function getAlerts(filters: AlertFilters = {}): AlertQueryResult {
  const db = getDb();
  const conditions: string[] = [];
  const params: SqlValue[] = [];

  if (filters.deviceId) {
    conditions.push('device_id = ?');
    params.push(filters.deviceId);
  }
  if (filters.type) {
    conditions.push('type = ?');
    params.push(filters.type);
  }
  if (filters.severity) {
    conditions.push('severity = ?');
    params.push(filters.severity);
  }

  const where = conditions.length > 0 ? `WHERE ${conditions.join(' AND ')}` : '';

  // Get total count
  const countResult = db.exec(`SELECT COUNT(*) as cnt FROM alerts ${where}`, params);
  const total = countResult.length > 0 ? (countResult[0].values[0][0] as number) : 0;

  // Get paginated results
  const limit = filters.limit || 50;
  const offset = filters.offset || 0;

  const result = db.exec(
    `SELECT id, device_id, timestamp, type, severity, message, details_json, acknowledged, group_key, fingerprint, count
     FROM alerts ${where}
     ORDER BY timestamp DESC
     LIMIT ? OFFSET ?`,
    [...params, limit, offset]
  );

  const alerts: Alert[] = [];
  if (result.length > 0) {
    for (const row of result[0].values) {
      alerts.push(rowToAlert(row));
    }
  }

  return { alerts, total };
}

export function acknowledgeAlert(id: string): boolean {
  const db = getDb();
  const existing = db.exec('SELECT id FROM alerts WHERE id = ?', [id]);
  if (existing.length === 0 || existing[0].values.length === 0) return false;

  db.run('UPDATE alerts SET acknowledged = 1 WHERE id = ?', [id]);
  saveDb();
  return true;
}

export function getUnacknowledgedCount(deviceId?: string): number {
  const db = getDb();
  if (deviceId) {
    const result = db.exec(
      'SELECT COUNT(*) FROM alerts WHERE acknowledged = 0 AND device_id = ?',
      [deviceId]
    );
    return result.length > 0 ? (result[0].values[0][0] as number) : 0;
  } else {
    const result = db.exec('SELECT COUNT(*) FROM alerts WHERE acknowledged = 0');
    return result.length > 0 ? (result[0].values[0][0] as number) : 0;
  }
}

export function getRecentAlerts(minutes: number): Alert[] {
  const db = getDb();
  const cutoff = Date.now() - minutes * 60 * 1000;

  const result = db.exec(
    `SELECT id, device_id, timestamp, type, severity, message, details_json, acknowledged, group_key, fingerprint, count
     FROM alerts WHERE timestamp > ?
     ORDER BY timestamp DESC`,
    [cutoff]
  );

  if (result.length === 0) return [];
  return result[0].values.map(rowToAlert);
}

// Helper

function rowToAlert(row: SqlValue[]): Alert {
  return {
    id: row[0] as string,
    deviceId: row[1] as string,
    timestamp: row[2] as number,
    type: row[3] as string,
    severity: row[4] as string,
    message: row[5] as string,
    details: row[6] ? JSON.parse(row[6] as string) : undefined,
    acknowledged: row[7] === 1,
    groupKey: row[8] as string | undefined,
    fingerprint: row[9] as string | undefined,
    count: row[10] as number,
  };
}
