"""REST API and WebSocket server for 巡查者 agent.

Provides a FastAPI application with:
  - REST endpoints for status, system metrics, processes, USB, alerts, config
  - WebSocket endpoint for real-time metric/alert streaming
  - CORS enabled for local dashboard access
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any, Dict, List, Optional, Set

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from agent.alert import Alert, AlertSeverity, AlertStore
from agent.config import AgentConfig
from agent.monitors.process_monitor import ProcessMonitor
from agent.monitors.system_resource import SystemResourceMonitor
from agent.monitors.usb_control import USBMonitor
from agent.monitors.registry_monitor import RegistryMonitor
from agent.monitors.service_monitor import ServiceMonitor
from agent.monitors.directory_integrity import DirectoryIntegrityMonitor
from agent.sandbox import SandboxManager

# Module-level reference for the SmartControlEngine (set after APIServer init).
# The status endpoint reads this lazily to expose the health score.
_smart_control_ref: Optional['SmartControlEngine'] = None  # type: ignore[assignment]


def set_smart_control_engine(engine: 'SmartControlEngine') -> None:  # type: ignore[name-defined]
    global _smart_control_ref
    _smart_control_ref = engine

logger = logging.getLogger(__name__)

# -- FastAPI application factory --


def create_app(
    config: AgentConfig,
    alert_store: AlertStore,
    sys_monitor: SystemResourceMonitor,
    proc_monitor: ProcessMonitor,
    usb_monitor: USBMonitor,
    sandbox_mgr: Optional[SandboxManager] = None,
    reg_monitor: Optional[RegistryMonitor] = None,
    svc_monitor: Optional[ServiceMonitor] = None,
    dir_monitor: Optional[DirectoryIntegrityMonitor] = None,
) -> tuple[FastAPI, _WSManager]:
    """Build and configure the FastAPI application.

    Returns the app and the WebSocket manager (for external metrics broadcast).
    """

    app = FastAPI(
        title="巡查者 Agent API",
        version="0.1.0",
        docs_url="/docs",
        redoc_url="/redoc",
    )

    # CORS – allow local dashboard access.
    origins = config.api.cors_origins or ["*"]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    ws_manager = _WSManager(alert_store)

    # -- REST endpoints --

    @app.get("/api/v1/status")
    async def get_status() -> Dict[str, Any]:
        sc = _smart_control_ref
        health_info: Dict[str, Any] = {"enabled": False}
        if sc and sc.running:
            # Evaluate a fresh state snapshot for the status endpoint.
            from agent.controllers.state import StateEvaluator
            evaluator = StateEvaluator(alert_store)
            state = evaluator.evaluate()
            health_info = {
                "enabled": True,
                "health_score": round(state.health_score, 1),
                "summary": state.summary,
                "tuner_multiplier": round(sc.tuner.multiplier, 2),
            }
        return {
            "status": "running",
            "version": "0.1.0",
            "uptime_seconds": round(time.time() - _start_time, 1),
            "monitors": {
                "system_resource": sys_monitor.status(),
                "process": proc_monitor.status(),
                "usb": usb_monitor.status(),
            },
            "smart_control": health_info,
        }

    @app.get("/api/v1/system")
    async def get_system() -> Dict[str, Any]:
        metrics = sys_monitor.latest_metrics
        if metrics is None:
            return {"error": "No metrics collected yet"}
        return metrics

    @app.get("/api/v1/processes")
    async def get_processes(
        limit: int = 100,
        offset: int = 0,
    ) -> Dict[str, Any]:
        """Return process snapshot with optional pagination."""
        snapshot = proc_monitor.latest_snapshot
        total = len(snapshot)
        page = snapshot[offset : offset + limit]
        return {
            "total": total,
            "offset": offset,
            "limit": limit,
            "processes": page,
        }

    @app.post("/api/v1/process/kill/{pid}")
    async def kill_process(pid: int) -> Dict[str, Any]:
        success, message = proc_monitor.kill_process(pid)
        return {"success": success, "message": message, "pid": pid}

    @app.get("/api/v1/usb")
    async def get_usb() -> Dict[str, Any]:
        return {
            "devices": usb_monitor.latest_devices,
            "events": usb_monitor.events[-50:],
        }

    @app.get("/api/v1/alerts")
    async def get_alerts(
        severity: Optional[str] = None,
        alert_type: Optional[str] = None,
        limit: int = 100,
    ) -> Dict[str, Any]:
        """Return alert history with optional filtering."""
        alerts = alert_store.get_recent(min(limit, 500))

        if severity:
            try:
                sev = AlertSeverity(severity)
                alerts = [a for a in alerts if a.severity == sev]
            except ValueError:
                pass

        if alert_type:
            from agent.alert import AlertType

            try:
                at = AlertType(alert_type)
                alerts = [a for a in alerts if a.alert_type == at]
            except ValueError:
                pass

        return {
            "total": len(alerts),
            "alerts": [a.to_dict() for a in alerts],
        }

    @app.get("/api/v1/config")
    async def get_config() -> Dict[str, Any]:
        """Return the current runtime configuration."""
        return {
            "process_whitelist": list(getattr(proc_monitor._proc_config, "whitelist", [])),
            "process_blacklist": list(getattr(proc_monitor._proc_config, "blacklist", [])),
            "usb_blocklist": list(getattr(usb_monitor._usb_config, "blocklist", [])),
            "monitor_enabled": sys_monitor._config.enabled,
            "usb_monitor_enabled": usb_monitor._mon_config.enabled,
            "network_monitor_enabled": True,
            "check_interval": int(sys_monitor._config.interval_seconds),
        }

    @app.post("/api/v1/config")
    async def update_config(payload: Dict[str, Any]) -> Dict[str, Any]:
        """Update runtime configuration (partial updates supported)."""
        changes: List[str] = []

        # Process config update.
        if "process" in payload:
            proc_data = payload["process"]
            from agent.config import ProcessConfig

            new_proc = ProcessConfig(
                whitelist=proc_data.get("whitelist", config.process.whitelist),
                blacklist=proc_data.get("blacklist", config.process.blacklist),
            )
            proc_monitor.update_config(new_proc)
            changes.append("process")

        # USB config update.
        if "usb" in payload:
            usb_data = payload["usb"]
            from agent.config import USBConfig

            new_usb = USBConfig(blocklist=usb_data.get("blocklist", config.usb.blocklist))
            usb_monitor.update_config(new_usb)
            changes.append("usb")

        return {"updated": changes, "status": "ok"}

    # -- System hardening endpoints --

    @app.get("/api/v1/registry")
    async def get_registry() -> Dict[str, Any]:
        if not reg_monitor:
            return {"error": "Registry monitor not initialized"}
        return {
            "status": reg_monitor.status(),
            "snapshot": reg_monitor.latest_snapshot,
        }

    @app.get("/api/v1/services")
    async def get_services() -> Dict[str, Any]:
        if not svc_monitor:
            return {"error": "Service monitor not initialized"}
        return {
            "status": svc_monitor.status(),
            "services": svc_monitor.latest_services,
        }

    @app.get("/api/v1/directory-integrity")
    async def get_directory_integrity() -> Dict[str, Any]:
        if not dir_monitor:
            return {"error": "Directory integrity monitor not initialized"}
        return {
            "status": dir_monitor.status(),
            "snapshot": dir_monitor.latest_snapshot,
        }

    # -- Sandbox endpoints --

    @app.get("/api/v1/sandbox/status")
    async def sandbox_status() -> Dict[str, Any]:
        if not sandbox_mgr:
            return {"enabled": False, "available": False, "reason": "Sandbox not initialized"}
        return {
            "enabled": sandbox_mgr.enabled,
            "available": sandbox_mgr.available,
            "timeout_seconds": config.sandbox.timeout_seconds,
        }

    @app.post("/api/v1/sandbox/run")
    async def sandbox_run(payload: Dict[str, Any]) -> Dict[str, Any]:
        if not sandbox_mgr or not sandbox_mgr.enabled:
            return {"error": "Sandbox not enabled"}
        file_path = payload.get("file_path", "")
        if not file_path:
            return {"error": "file_path is required"}
        timeout = payload.get("timeout")
        report = await sandbox_mgr.run_file(file_path, timeout=timeout)
        if report is None:
            return {"error": "Sandbox execution failed (see agent logs)"}
        return {"status": "completed", "report": report}

    @app.post("/api/v1/sandbox/analyze")
    async def sandbox_analyze(payload: Dict[str, Any]) -> Dict[str, Any]:
        if not sandbox_mgr or not sandbox_mgr.enabled:
            return {"error": "Sandbox not enabled"}
        report = payload.get("report", {})
        if not report:
            return {"error": "report is required"}
        from agent.config import AIConfig
        llm_cfg = config.ai.llm
        if not llm_cfg.enabled:
            return {"error": "LLM analysis not enabled in config"}
        analysis = await sandbox_mgr.analyze_report(
            report,
            llm_endpoint=llm_cfg.endpoint,
            model=llm_cfg.model or config.sandbox.ai_analysis.model,
        )
        if analysis is None:
            return {"error": "AI analysis failed"}
        return {"status": "completed", "analysis": analysis}

    @app.post("/api/v1/sandbox/run-and-analyze")
    async def sandbox_run_and_analyze(payload: Dict[str, Any]) -> Dict[str, Any]:
        if not sandbox_mgr or not sandbox_mgr.enabled:
            return {"error": "Sandbox not enabled"}
        file_path = payload.get("file_path", "")
        if not file_path:
            return {"error": "file_path is required"}
        timeout = payload.get("timeout")
        report = await sandbox_mgr.run_file(file_path, timeout=timeout)
        if report is None:
            return {"error": "Sandbox execution failed"}
        analysis = None
        llm_cfg = config.ai.llm
        if llm_cfg.enabled:
            analysis = await sandbox_mgr.analyze_report(
                report, llm_endpoint=llm_cfg.endpoint, model=llm_cfg.model,
            )
        return {"status": "completed", "report": report, "analysis": analysis}

    # -- WebSocket --

    @app.websocket("/ws")
    async def websocket_endpoint(ws: WebSocket) -> None:
        await ws_manager.connect(ws)
        try:
            while True:
                # Keep the connection alive; client may send keep-alive pings.
                data = await ws.receive_text()
                if data == "ping":
                    await ws.send_text(json.dumps({"type": "pong"}))
        except WebSocketDisconnect:
            await ws_manager.disconnect(ws)
        except Exception:
            logger.exception("WebSocket error")
            await ws_manager.disconnect(ws)

    return app, ws_manager


# -- WebSocket connection manager --


class _WSManager:
    """Manages WebSocket connections and broadcasts metrics/alerts."""

    def __init__(self, alert_store: AlertStore) -> None:
        self._connections: Set[WebSocket] = set()
        self._alert_store = alert_store
        # Subscribe to alerts for real-time broadcast.
        alert_store.subscribe(self._on_alert)

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self._connections.add(ws)
        logger.debug("WebSocket client connected (total: %d)", len(self._connections))

    async def disconnect(self, ws: WebSocket) -> None:
        self._connections.discard(ws)
        logger.debug("WebSocket client disconnected (total: %d)", len(self._connections))

    def _on_alert(self, alert: Alert) -> None:
        """Alert callback — broadcast to all connected clients."""
        asyncio.create_task(self._broadcast({"type": "alert", "data": alert.to_dict()}))

    async def broadcast_metrics(self, metrics: Dict[str, Any]) -> None:
        """Send a metrics snapshot to all clients."""
        await self._broadcast({"type": "metrics", "data": metrics})

    async def _broadcast(self, message: Dict[str, Any]) -> None:
        """Send a JSON message to all connected WebSocket clients."""
        if not self._connections:
            return
        payload = json.dumps(message, default=str)
        stale: List[WebSocket] = []
        for ws in self._connections:
            try:
                await ws.send_text(payload)
            except Exception:
                stale.append(ws)
        for ws in stale:
            await self.disconnect(ws)


# -- Server runner --

_start_time = time.time()


class APIServer:
    """Manages the uvicorn server lifecycle.

    Parameters
    ----------
    config : AgentConfig
    alert_store : AlertStore
    sys_monitor : SystemResourceMonitor
    proc_monitor : ProcessMonitor
    usb_monitor : USBMonitor
    """

    def __init__(
        self,
        config: AgentConfig,
        alert_store: AlertStore,
        sys_monitor: SystemResourceMonitor,
        proc_monitor: ProcessMonitor,
        usb_monitor: USBMonitor,
        sandbox_mgr: Optional[SandboxManager] = None,
        reg_monitor: Optional[RegistryMonitor] = None,
        svc_monitor: Optional[ServiceMonitor] = None,
        dir_monitor: Optional[DirectoryIntegrityMonitor] = None,
    ) -> None:
        self._config = config
        self._app, self.ws_manager = create_app(
            config, alert_store, sys_monitor, proc_monitor, usb_monitor,
            sandbox_mgr=sandbox_mgr,
            reg_monitor=reg_monitor,
            svc_monitor=svc_monitor,
            dir_monitor=dir_monitor,
        )
        self._server: Optional[uvicorn.Server] = None

    async def run(self) -> None:
        """Start the uvicorn server (blocks until stop() is called)."""
        cfg = uvicorn.Config(
            app=self._app,
            host=self._config.api.host,
            port=self._config.api.port,
            log_level="warning",
            ws="websockets",
        )
        self._server = uvicorn.Server(cfg)
        logger.info("API server starting on %s:%d", self._config.api.host, self._config.api.port)
        await self._server.serve()

    async def stop(self) -> None:
        """Signal the server to shut down."""
        if self._server:
            self._server.should_exit = True
        logger.info("API server stopped")
