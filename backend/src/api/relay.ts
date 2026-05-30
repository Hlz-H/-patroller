import { Router, Request, Response } from 'express';
import { getDb, saveDb } from '../db';
import { sendToDevice } from '../ws';
import { tailscaleAuthMiddleware } from '../auth/tailscale';
import { v4 as uuidv4 } from 'uuid';
import { PendingCommand } from '../types';

const router = Router();
router.use(tailscaleAuthMiddleware);

router.post('/command', (req: Request, res: Response) => {
  try {
    const { deviceId, action, payload } = req.body;

    if (!deviceId || !action) {
      res.status(400).json({ error: 'deviceId and action are required' });
      return;
    }

    const db = getDb();
    const commandId = uuidv4();
    const timestamp = Date.now();

    db.run(
      `INSERT INTO pending_commands (id, device_id, action, payload_json, timestamp)
       VALUES (?, ?, ?, ?, ?)`,
      [commandId, deviceId, action, JSON.stringify(payload || {}), timestamp]
    );
    saveDb();

    const delivered = sendToDevice(deviceId, {
      type: 'command',
      deviceId,
      action,
      payload,
    });

    res.status(201).json({
      id: commandId,
      deviceId,
      action,
      delivered,
      timestamp,
    });
  } catch (err) {
    res.status(500).json({ error: 'Failed to relay command' });
  }
});

router.get('/commands/:deviceId', (req: Request, res: Response) => {
  try {
    const devId = req.params.deviceId as string;
    const db = getDb();
    const result = db.exec(
      `SELECT id, device_id, action, payload_json, timestamp
       FROM pending_commands
       WHERE device_id = ?
       ORDER BY timestamp ASC
       LIMIT 100`,
      [devId]
    );

    const commands: PendingCommand[] = [];
    if (result.length > 0) {
      for (const row of result[0].values) {
        commands.push({
          id: row[0] as string,
          deviceId: row[1] as string,
          action: row[2] as string,
          payload: row[3] ? JSON.parse(row[3] as string) : {},
          timestamp: row[4] as number,
        });
      }
    }

    res.json(commands);
  } catch (err) {
    res.status(500).json({ error: 'Failed to get pending commands' });
  }
});

router.delete('/commands/:id', (req: Request, res: Response) => {
  try {
    const cmdId = req.params.id as string;
    const db = getDb();
    const result = db.exec('SELECT id FROM pending_commands WHERE id = ?', [cmdId]);
    if (result.length === 0 || result[0].values.length === 0) {
      res.status(404).json({ error: 'Command not found' });
      return;
    }

    db.run('DELETE FROM pending_commands WHERE id = ?', [cmdId]);
    saveDb();
    res.json({ success: true });
  } catch (err) {
    res.status(500).json({ error: 'Failed to delete command' });
  }
});

export default router;
