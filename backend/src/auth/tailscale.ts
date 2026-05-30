// Tailscale identity verification middleware

import { Request, Response, NextFunction } from 'express';
import { config } from '../config';
import { IncomingMessage } from 'http';

export function tailscaleAuthMiddleware(
  req: Request,
  res: Response,
  next: NextFunction
): void {
  if (!config.TAILSCALE_AUTH) {
    // Local dev: skip auth
    next();
    return;
  }

  // In production with Tailscale, verify identity headers
  const tailscaleUser = req.headers['tailscale-user'] as string | undefined;
  const tailscaleNode = req.headers['tailscale-node'] as string | undefined;

  if (!tailscaleUser || !tailscaleNode) {
    res.status(401).json({ error: 'Tailscale identity required' });
    return;
  }

  // Store identity for downstream use
  (req as any).tailscaleUser = tailscaleUser;
  (req as any).tailscaleNode = tailscaleNode;
  next();
}

export function verifyWebSocketAuth(req: IncomingMessage): boolean {
  if (!config.TAILSCALE_AUTH) {
    // Local dev: trust localhost connections
    return true;
  }

  const tailscaleUser = req.headers['tailscale-user'] as string | undefined;
  const tailscaleNode = req.headers['tailscale-node'] as string | undefined;

  return !!(tailscaleUser && tailscaleNode);
}
