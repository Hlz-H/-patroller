import { Router, Request, Response } from 'express';
import { getAlerts, acknowledgeAlert, getUnacknowledgedCount } from '../db/alerts';
import { tailscaleAuthMiddleware } from '../auth/tailscale';

const router = Router();
router.use(tailscaleAuthMiddleware);

router.get('/', (req: Request, res: Response) => {
  try {
    const { deviceId, type, severity, limit, offset } = req.query;
    const result = getAlerts({
      deviceId: deviceId as string | undefined,
      type: type as string | undefined,
      severity: severity as string | undefined,
      limit: limit ? parseInt(limit as string, 10) : undefined,
      offset: offset ? parseInt(offset as string, 10) : undefined,
    });
    res.json(result);
  } catch (err) {
    res.status(500).json({ error: 'Failed to query alerts' });
  }
});

router.get('/unacknowledged', (req: Request, res: Response) => {
  try {
    const { deviceId } = req.query;
    const count = getUnacknowledgedCount(deviceId as string | undefined);
    res.json({ count });
  } catch (err) {
    res.status(500).json({ error: 'Failed to get unacknowledged count' });
  }
});

router.post('/:id/acknowledge', (req: Request, res: Response) => {
  try {
    const alertId = req.params.id as string;
    const success = acknowledgeAlert(alertId);
    if (!success) {
      res.status(404).json({ error: 'Alert not found' });
      return;
    }
    res.json({ success: true });
  } catch (err) {
    res.status(500).json({ error: 'Failed to acknowledge alert' });
  }
});

export default router;
