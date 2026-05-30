"""Backend WebSocket client for 巡查者 agent.

Connects to the Node.js Backend WebSocket server, pushes system metrics
and alerts in real time, and receives/executes commands (process kill,
USB block, config update) from the Backend.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Callable, Dict, Optional

import websockets

logger = logging.getLogger(__name__)

# Command callback: receives (action, payload) and returns a result dict.
CommandCallback = Callable[[str, Dict[str, Any]], Any]


class BackendClient:
    """WebSocket client that connects to the Node.js Backend.

    Parameters
    ----------
    host : str
        Backend server hostname/IP.
    port : int
        Backend server port.
    device_id : str
        Unique device identifier sent on registration.
    device_name : str
        Human-readable device name sent on registration.
    """

    def __init__(
        self,
        host: str,
        port: int,
        device_id: str,
        device_name: str,
    ) -> None:
        self._host = host
        self._port = port
        self._device_id = device_id
        self._device_name = device_name

        self._ws: Optional[websockets.WebSocketClientProtocol] = None
        self._running = False
        self._connected = False
        self._command_handler: Optional[CommandCallback] = None

    @property
    def connected(self) -> bool:
        """Whether the WebSocket connection is currently established."""
        return self._connected

    def set_command_handler(self, callback: CommandCallback) -> None:
        """Register a callback that processes incoming commands.

        The callback receives ``(action: str, payload: dict)`` and should
        return a result (arbitrary type) that will be serialized and sent
        back to the Backend as a ``command_result`` message.
        """
        self._command_handler = callback

    async def run(self) -> None:
        """Main loop: connect, register, listen for messages.

        Automatically reconnects with exponential backoff on disconnect.
        Runs until :meth:`stop` is called.
        """
        self._running = True
        backoff = 1
        max_backoff = 30

        while self._running:
            try:
                await self._connect_and_listen()
                # If _connect_and_listen returned normally (clean close),
                # reset backoff.
                backoff = 1
            except (websockets.ConnectionClosed, OSError) as exc:
                logger.warning("Backend connection closed: %s", exc)
            except Exception:
                logger.exception("Unexpected error in Backend client")

            self._connected = False

            if not self._running:
                break

            logger.info("Reconnecting to Backend in %ds...", backoff)
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, max_backoff)

        logger.info("Backend client run loop exited")

    async def stop(self) -> None:
        """Gracefully close the WebSocket connection and stop the run loop."""
        self._running = False
        if self._ws:
            try:
                await self._ws.close()
            except Exception:
                pass
            self._ws = None
        self._connected = False
        logger.info("BackendClient stopped")

    async def send_metrics(self, metrics: Dict[str, Any]) -> None:
        """Push a system metrics snapshot to the Backend."""
        if not self._ws or not self._connected:
            return
        try:
            await self._ws.send(json.dumps({"type": "metrics", "data": metrics}))
        except Exception:
            logger.exception("Failed to send metrics to Backend")
            self._connected = False

    async def send_alert(self, alert: Dict[str, Any]) -> None:
        """Push an alert to the Backend."""
        if not self._ws or not self._connected:
            return
        try:
            await self._ws.send(json.dumps({"type": "alert", "data": alert}))
        except Exception:
            logger.exception("Failed to send alert to Backend")
            self._connected = False

    def _ws_url(self) -> str:
        return f"ws://{self._host}:{self._port}/ws"

    async def _connect_and_listen(self) -> None:
        """Establish connection, register, and process incoming messages."""
        url = self._ws_url()
        logger.info("Connecting to Backend at %s", url)

        self._ws = await websockets.connect(url)
        self._connected = True
        logger.info("Connected to Backend (device=%s)", self._device_id)

        await self._ws.send(json.dumps({
            "type": "register",
            "deviceId": self._device_id,
            "name": self._device_name,
        }))

        async for raw in self._ws:
            if not self._running:
                break
            await self._on_message(raw)

    async def _on_message(self, raw: str) -> None:
        """Process a single incoming WebSocket message."""
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            logger.warning("Invalid JSON received from Backend: %s", raw[:200])
            return

        msg_type = data.get("type", "")

        if msg_type == "command":
            await self._handle_command(data)
        elif msg_type == "ping":
            if self._ws:
                await self._ws.send(json.dumps({"type": "pong"}))
        else:
            logger.debug("Unknown message type from Backend: %s", msg_type)

    async def _handle_command(self, data: Dict[str, Any]) -> None:
        """Execute a command received from the Backend and send the result."""
        action = data.get("action", "")
        payload = data.get("payload", {})

        if not self._command_handler:
            logger.warning("No command handler set, ignoring command: %s", action)
            await self._send_command_result(action, {"error": "no command handler"})
            return

        try:
            result = self._command_handler(action, payload)
            if asyncio.iscoroutine(result):
                result = await result
            logger.info("Command executed: %s", action)
            await self._send_command_result(action, result or {})
        except Exception:
            logger.exception("Command execution failed: %s", action)
            await self._send_command_result(action, {"error": "execution failed"})

    async def _send_command_result(self, action: str, result: Any) -> None:
        """Send the result of a command back to the Backend."""
        if not self._ws:
            return
        try:
            await self._ws.send(json.dumps({
                "type": "command_result",
                "action": action,
                "result": result,
            }))
        except Exception:
            logger.exception("Failed to send command_result for %s", action)
