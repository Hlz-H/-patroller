// SQLite database initialization and schema

import initSqlJs from 'sql.js';
import type { Database as SqlJsDatabase } from 'sql.js';
import { readFileSync, writeFileSync, existsSync, mkdirSync } from 'fs';
import { dirname } from 'path';
import { config } from '../config';

let db: SqlJsDatabase | null = null;

// ── Debounced persistence ──────────────────────────────────────────────
// sql.js is an in-memory WASM SQLite — the DB only exists on disk when we
// explicitly export + write.  Debounce rapid writes (metrics streaming,
// alert bursts) so we don't serialize the whole DB on every single mutation.

const SAVE_DEBOUNCE_MS = 200;
let saveTimer: ReturnType<typeof setTimeout> | null = null;

function cancelPendingSave(): void {
  if (saveTimer !== null) {
    clearTimeout(saveTimer);
    saveTimer = null;
  }
}

function ensureDir(filePath: string): void {
  const dir = dirname(filePath);
  if (!existsSync(dir)) {
    mkdirSync(dir, { recursive: true });
  }
}

export function getDb(): SqlJsDatabase {
  if (!db) throw new Error('Database not initialized. Call initDb() first.');
  return db;
}

export async function initDb(): Promise<SqlJsDatabase> {
  ensureDir(config.DB_PATH);

  const SQL = await initSqlJs();

  // Load existing database or create new
  if (existsSync(config.DB_PATH)) {
    const buffer = readFileSync(config.DB_PATH);
    db = new SQL.Database(buffer);
  } else {
    db = new SQL.Database();
  }

  // Performance pragmas
  db.run('PRAGMA journal_mode=WAL;');
  db.run('PRAGMA synchronous=NORMAL;');
  db.run('PRAGMA foreign_keys=ON;');

  // Create tables
  db.run(`
    CREATE TABLE IF NOT EXISTS devices (
      id TEXT PRIMARY KEY,
      name TEXT NOT NULL,
      tailscale_ip TEXT,
      local_ip TEXT,
      last_seen INTEGER NOT NULL,
      status TEXT DEFAULT 'offline',
      version TEXT,
      config_json TEXT
    )
  `);

  db.run(`
    CREATE TABLE IF NOT EXISTS alerts (
      id TEXT PRIMARY KEY,
      device_id TEXT NOT NULL,
      timestamp INTEGER NOT NULL,
      type TEXT NOT NULL,
      severity TEXT NOT NULL,
      message TEXT NOT NULL,
      details_json TEXT,
      acknowledged INTEGER DEFAULT 0,
      group_key TEXT,
      fingerprint TEXT,
      count INTEGER DEFAULT 1,
      FOREIGN KEY (device_id) REFERENCES devices(id)
    )
  `);

  db.run(`
    CREATE TABLE IF NOT EXISTS metrics_history (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      device_id TEXT NOT NULL,
      timestamp INTEGER NOT NULL,
      cpu_usage REAL,
      memory_usage REAL,
      disk_usage REAL,
      network_sent REAL,
      network_recv REAL
    )
  `);

  db.run(`
    CREATE TABLE IF NOT EXISTS pending_commands (
      id TEXT PRIMARY KEY,
      device_id TEXT NOT NULL,
      action TEXT NOT NULL,
      payload_json TEXT,
      timestamp INTEGER NOT NULL
    )
  `);

  db.run(`
    CREATE TABLE IF NOT EXISTS sandbox_results (
      id TEXT PRIMARY KEY,
      device_id TEXT NOT NULL,
      file_path TEXT NOT NULL,
      status TEXT NOT NULL DEFAULT 'pending',
      report_json TEXT,
      analysis_json TEXT,
      timestamp INTEGER NOT NULL,
      completed_at INTEGER,
      FOREIGN KEY (device_id) REFERENCES devices(id)
    )
  `);

  // Migration: add new columns for dedup/aggregation (safe for existing DBs)
  const migrations = [
    `ALTER TABLE alerts ADD COLUMN group_key TEXT`,
    `ALTER TABLE alerts ADD COLUMN fingerprint TEXT`,
    `ALTER TABLE alerts ADD COLUMN count INTEGER DEFAULT 1`,
  ];
  for (const sql of migrations) {
    try {
      db.exec(sql);
    } catch {
      // Column already exists — ignore
    }
  }

  saveDbNow();
  return db;
}

/**
 * Schedule a debounced disk write.  Multiple calls within 200ms are batched
 * into a single write.  Use for high-frequency mutations (metrics, alerts).
 */
export function saveDb(): void {
  if (!db) return;
  if (saveTimer !== null) return; // already scheduled
  saveTimer = setTimeout(() => {
    saveTimer = null;
    try {
      const data = db!.export();
      const buffer = Buffer.from(data);
      ensureDir(config.DB_PATH);
      writeFileSync(config.DB_PATH, buffer);
    } catch (err) {
      // Can't do much — logging isn't available at this layer.
    }
  }, SAVE_DEBOUNCE_MS);
}

/**
 * Write the database to disk immediately.  Use for shutdown / critical
 * operations where data loss is unacceptable.
 */
export function saveDbNow(): void {
  cancelPendingSave();
  if (!db) return;
  const data = db.export();
  const buffer = Buffer.from(data);
  ensureDir(config.DB_PATH);
  writeFileSync(config.DB_PATH, buffer);
}

export function closeDb(): void {
  if (db) {
    saveDbNow();
    db.close();
    db = null;
  }
}
