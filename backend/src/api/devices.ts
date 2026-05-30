import { Router, Request, Response } from 'express';
import { Alert } from '../types';
import {
  getAllDevices,
  getDevice,
  updateDevice,
  deleteDevice,
  registerDevice,
  updateLastSeen,
  getOnlineDevices,
  insertMetrics,
} from '../db/devices';
import { storeAlert } from '../db/alerts';
import { processAlert } from '../pipeline/policy';
import { broadcast } from '../ws';
import { tailscaleAuthMiddleware } from '../auth/tailscale';

const router = Router();
router.use(tailscaleAuthMiddleware);

router.get('/', (_req: Request, res: Response) => {
  try {
    const devices = getAllDevices();
    res.json(devices);
  } catch (err) {
    res.status(500).json({ error: 'Failed to fetch devices' });
  }
});

router.get('/online', (_req: Request, res: Response) => {
  try {
    const devices = getOnlineDevices();
    res.json(devices);
  } catch (err) {
    res.status(500).json({ error: 'Failed to fetch online devices' });
  }
});

router.get('/:id', (req: Request, res: Response) => {
  try {
    const deviceId = req.params.id as string;
    const device = getDevice(deviceId);
    if (!device) {
      res.status(404).json({ error: 'Device not found' });
      return;
    }
    res.json(device);
  } catch (err) {
    res.status(500).json({ error: 'Failed to fetch device' });
  }
});

router.put('/:id', (req: Request, res: Response) => {
  try {
    const deviceId = req.params.id as string;
    const { name, config } = req.body;
    const device = updateDevice(deviceId, { name, config });
    if (!device) {
      res.status(404).json({ error: 'Device not found' });
      return;
    }
    res.json(device);
  } catch (err) {
    res.status(500).json({ error: 'Failed to update device' });
  }
});

router.delete('/:id', (req: Request, res: Response) => {
  try {
    const deviceId = req.params.id as string;
    const deleted = deleteDevice(deviceId);
    if (!deleted) {
      res.status(404).json({ error: 'Device not found' });
      return;
    }
    res.json({ success: true });
  } catch (err) {
    res.status(500).json({ error: 'Failed to delete device' });
  }
});

router.post('/:id/heartbeat', (req: Request, res: Response) => {
  try {
    const deviceId = req.params.id as string;
    const { name, localIp, version } = req.body;
    registerDevice(deviceId, name || deviceId, localIp, version);
    updateLastSeen(deviceId);
    broadcast({ type: 'device:online', deviceId });
    res.json({ success: true, timestamp: Date.now() });
  } catch (err) {
    res.status(500).json({ error: 'Heartbeat failed' });
  }
});

router.post('/:id/metrics', (req: Request, res: Response) => {
  try {
    const deviceId = req.params.id as string;
    const metrics = req.body;
    updateLastSeen(deviceId);
    insertMetrics(deviceId, metrics);

    broadcast({
      type: 'device:metrics',
      deviceId,
      data: metrics,
    });

    res.json({ success: true });
  } catch (err) {
    res.status(500).json({ error: 'Failed to process metrics' });
  }
});

router.post('/:id/alerts', (req: Request, res: Response) => {
  try {
    const deviceId = req.params.id as string;
    const { type, severity, message, details } = req.body;

    if (!type || !severity || !message) {
      res.status(400).json({ error: 'type, severity, and message are required' });
      return;
    }

    // Run alert through policy pipeline (suppression → dedup)
    const result = processAlert({
      type,
      severity,
      message,
      details: details || {},
      deviceId,
    } as Alert);

    if (result.action !== 'stored') {
      res.json({ action: result.action, message: `Alert ${result.action}` });
      return;
    }

    const alert = storeAlert(result.alert!);

    broadcast({
      type: 'device:alert',
      deviceId,
      data: alert,
    });

    res.status(201).json(alert);
  } catch (err) {
    res.status(500).json({ error: 'Failed to store alert' });
  }
});

export default router;
