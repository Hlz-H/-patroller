// Relays sandbox operation requests from the Commander UI to an agent,
// and returns results.  The heavy lifting (WSB generation, VM launch,
// monitor script, AI analysis) happens on the agent side.

import { Router, Request, Response } from 'express';
import { getDb, saveDb } from '../db';
import { sendToDevice } from '../ws';
import { tailscaleAuthMiddleware } from '../auth/tailscale';
import { v4 as uuidv4 } from 'uuid';

const router = Router();
router.use(tailscaleAuthMiddleware);

interface SandboxResult {
  id: string;
  deviceId: string;
  filePath: string;
  status: 'pending' | 'running' | 'completed' | 'failed';
  report?: unknown;
  analysis?: unknown;
  timestamp: number;
  completedAt?: number;
}

router.post('/run', (req: Request, res: Response) => {
  try {
    const { deviceId, filePath, timeout } = req.body;

    if (!deviceId || !filePath) {
      res.status(400).json({ error: 'deviceId and filePath are required' });
      return;
    }

    const db = getDb();
    const id = uuidv4();
    const timestamp = Date.now();

    db.run(
      `INSERT INTO sandbox_results (id, device_id, file_path, status, timestamp)
       VALUES (?, ?, ?, 'pending', ?)`,
      [id, deviceId, filePath, timestamp]
    );
    saveDb();

    const delivered = sendToDevice(deviceId, {
      type: 'command',
      deviceId,
      action: 'sandbox_run',
      payload: { file_path: filePath, timeout: timeout ?? undefined },
    });

    res.status(201).json({
      id,
      deviceId,
      filePath,
      status: 'pending',
      delivered,
      timestamp,
    });
  } catch (err) {
    res.status(500).json({ error: 'Failed to send sandbox command' });
  }
});

router.get('/results/:deviceId', (req: Request, res: Response) => {
  try {
    const deviceId = req.params.deviceId as string;
    const db = getDb();
    const result = db.exec(
      `SELECT id, device_id, file_path, status, report_json, analysis_json, timestamp, completed_at
       FROM sandbox_results
       WHERE device_id = ?
       ORDER BY timestamp DESC
       LIMIT 50`,
      [deviceId]
    );

    const results: SandboxResult[] = [];
    if (result.length > 0) {
      for (const row of result[0].values) {
        results.push({
          id: row[0] as string,
          deviceId: row[1] as string,
          filePath: row[2] as string,
          status: row[3] as SandboxResult['status'],
          report: row[4] ? JSON.parse(row[4] as string) : undefined,
          analysis: row[5] ? JSON.parse(row[5] as string) : undefined,
          timestamp: row[6] as number,
          completedAt: row[7] as number | undefined,
        });
      }
    }

    res.json(results);
  } catch (err) {
    res.status(500).json({ error: 'Failed to get sandbox results' });
  }
});

router.get('/result/:id', (req: Request, res: Response) => {
  try {
    const id = req.params.id as string;
    const db = getDb();
    const result = db.exec(
      `SELECT id, device_id, file_path, status, report_json, analysis_json, timestamp, completed_at
       FROM sandbox_results WHERE id = ?`,
      [id]
    );

    if (result.length === 0 || result[0].values.length === 0) {
      res.status(404).json({ error: 'Sandbox result not found' });
      return;
    }

    const row = result[0].values[0];
    res.json({
      id: row[0] as string,
      deviceId: row[1] as string,
      filePath: row[2] as string,
      status: row[3] as SandboxResult['status'],
      report: row[4] ? JSON.parse(row[4] as string) : undefined,
      analysis: row[5] ? JSON.parse(row[5] as string) : undefined,
      timestamp: row[6] as number,
      completedAt: row[7] as number | undefined,
    } satisfies SandboxResult);
  } catch (err) {
    res.status(500).json({ error: 'Failed to get sandbox result' });
  }
});

export default router;
