// Alert pipeline policy — suppression, deduplication, and aggregation gating.
// Mirrors the Agent's AlertStore.add_with_policy() in Python but in TypeScript.
// Aggregation (groupKey / count) is deferred to the database layer.

import crypto from 'crypto';
import { Alert } from '../types';
import { logger } from '../app';

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const DEDUP_WINDOW_MS = 60 * 1000; // 60 seconds
const FINGERPRINT_CLEANUP_INTERVAL_MS = 60 * 1000; // cleanup every 60s

// ---------------------------------------------------------------------------
// Public types
// ---------------------------------------------------------------------------

export type PolicyAction = 'stored' | 'deduplicated' | 'suppressed';

export interface PolicyResult {
  action: PolicyAction;
  /** Set only when action === 'stored' — carries the fingerprint. */
  alert?: Alert;
}

export interface SuppressionRule {
  key: string;
  expiresAt: number; // unix-epoch ms
}

// ---------------------------------------------------------------------------
// Module-level state
// ---------------------------------------------------------------------------

/** Active suppression rules: key → expiry timestamp (ms). */
const suppressionRules = new Map<string, number>();

/** Recent alert fingerprints: fingerprint → first-seen timestamp (ms). */
const recentFingerprints = new Map<string, number>();

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function computeFingerprint(alert: Alert): string {
  return crypto
    .createHash('md5')
    .update(`${alert.type}|${alert.severity}|${alert.message}`)
    .digest('hex');
}

function isSuppressed(alert: Alert): boolean {
  const now = Date.now();
  for (const [key, expiresAt] of suppressionRules) {
    if (expiresAt <= now) {
      suppressionRules.delete(key); // lazy-clean expired
      continue;
    }
    if (alert.type.includes(key) || alert.message.toLowerCase().includes(key)) {
      return true;
    }
  }
  return false;
}

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

/**
 * Run an incoming alert through the pipeline:
 *
 *  1. Suppression  – drop if any active suppression rule matches.
 *  2. Deduplication – drop if the same fingerprint was seen within the window.
 *  3. Pass          – record the fingerprint and return the alert.
 */
export function processAlert(alert: Alert): PolicyResult {
  // Step 1 — Suppression
  if (isSuppressed(alert)) {
    logger.debug(
      { alertType: alert.type, message: alert.message },
      'Alert suppressed by policy',
    );
    return { action: 'suppressed' };
  }

  // Step 2 — Deduplication
  const fp = computeFingerprint(alert);
  const lastSeen = recentFingerprints.get(fp);
  const now = Date.now();

  if (lastSeen !== undefined && now - lastSeen < DEDUP_WINDOW_MS) {
    logger.debug(
      { alertType: alert.type, fingerprint: fp },
      'Alert deduplicated',
    );
    return { action: 'deduplicated' };
  }

  // Step 3 — Pass
  recentFingerprints.set(fp, now);
  logger.debug(
    { alertType: alert.type, fingerprint: fp },
    'Alert passed pipeline',
  );

  return {
    action: 'stored',
    alert: { ...alert, fingerprint: fp },
  };
}

/**
 * Add a suppression rule. Alerts whose `type` or `message` (lowercased)
 * contain `key` as a substring are dropped until `durationMs` has elapsed.
 */
export function suppress(key: string, durationMs: number): void {
  suppressionRules.set(key, Date.now() + durationMs);
  logger.info({ key, durationMs }, 'Suppression rule added');
}

/**
 * Immediately remove a suppression rule by key.
 */
export function unsuppress(key: string): void {
  const existed = suppressionRules.delete(key);
  if (!existed) {
    logger.warn({ key }, 'Attempted to unsuppress non-existent rule');
  } else {
    logger.info({ key }, 'Suppression rule removed');
  }
}

/**
 * Return all currently-active (non-expired) suppression rules.
 */
export function getSuppressed(): SuppressionRule[] {
  const now = Date.now();
  const rules: SuppressionRule[] = [];

  for (const [key, expiresAt] of suppressionRules) {
    if (expiresAt > now) {
      rules.push({ key, expiresAt });
    } else {
      suppressionRules.delete(key); // lazy-clean expired
    }
  }

  return rules;
}

// ---------------------------------------------------------------------------
// Periodic cleanup
// ---------------------------------------------------------------------------

const cleanupTimer = setInterval(() => {
  const now = Date.now();
  const maxAge = DEDUP_WINDOW_MS * 2;
  let cleaned = 0;

  for (const [fp, ts] of recentFingerprints) {
    if (now - ts > maxAge) {
      recentFingerprints.delete(fp);
      cleaned++;
    }
  }

  if (cleaned > 0) {
    logger.debug({ cleaned }, 'Cleaned stale fingerprints');
  }
}, FINGERPRINT_CLEANUP_INTERVAL_MS);

// Don't keep the process alive just for periodic cleanup.
cleanupTimer.unref();
