"""Service monitor for 巡查者 agent.

Monitors Windows service state changes — new service creation, existing
service deletions, and running→stopped / stopped→running transitions.

Uses ``wmi`` (pywin32) when available, otherwise falls back to
``subprocess`` + ``sc query``.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List, Optional, Set, Tuple

from agent.alert import AlertStore, AlertType
from agent.config import MonitorConfig, ServiceConfig

logger = logging.getLogger(__name__)

# Windows service helpers

_SERVICE_AVAILABLE = False

try:
    import pythoncom
    import win32com.client

    _SERVICE_AVAILABLE = True
except ImportError:
    logger.warning("pywin32 not installed — service monitoring degraded")


def _query_services_wmi() -> List[Dict[str, Any]]:
    """Query services via WMI Win32_Service.

    Returns a list of dicts with keys: name, display_name, state,
    start_mode, path_name.

    Falls back to ``sc query`` if WMI unavailable.
    """
    if _SERVICE_AVAILABLE:
        try:
            pythoncom.CoInitialize()
            wmi = win32com.client.Dispatch("WbemScripting.SWbemLocator")
            svc = wmi.ConnectServer(".", "root\\cimv2")
            services: List[Dict[str, Any]] = []
            for s in svc.ExecQuery("SELECT * FROM Win32_Service"):
                services.append({
                    "name": str(s.Name or ""),
                    "display_name": str(s.DisplayName or ""),
                    "state": str(s.State or ""),
                    "start_mode": str(s.StartMode or ""),
                    "path_name": str(s.PathName or ""),
                })
            return services
        except Exception:
            logger.exception("WMI service query failed, falling back to sc query")

    # Fallback: sc query
    import subprocess
    try:
        result = subprocess.run(
            ["sc", "query", "type=", "service", "state=", "all"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        lines = result.stdout.splitlines()
        services: List[Dict[str, Any]] = []
        current: Dict[str, Any] = {}
        for line in lines:
            line = line.strip()
            if not line:
                continue
            if line.startswith("SERVICE_NAME:"):
                if current:
                    services.append(current)
                current = {"name": line.split(":", 1)[1].strip()}
            elif line.startswith("DISPLAY_NAME:"):
                current["display_name"] = line.split(":", 1)[1].strip()
            elif line.startswith("STATE"):
                # Format: STATE : 4  RUNNING
                parts = line.split()
                current["state"] = parts[-1] if len(parts) > 1 else ""
            elif line.startswith("START_TYPE"):
                current["start_mode"] = _sc_start_type(line)
        if current:
            services.append(current)
        return services
    except Exception:
        logger.exception("sc query fallback failed")
        return []


def _sc_start_type(line: str) -> str:
    """Parse START_TYPE line from sc query output."""
    parts = line.split()
    if len(parts) >= 3:
        return parts[-1]
    return ""


# Service monitor


class ServiceMonitor:
    """Async background monitor for Windows service changes.

    Parameters
    ----------
    mon_config : MonitorConfig
    svc_config : ServiceConfig
    alert_store : AlertStore
    """

    def __init__(
        self,
        mon_config: MonitorConfig,
        svc_config: ServiceConfig,
        alert_store: AlertStore,
    ) -> None:
        self._mon_config = mon_config
        self._svc_config = svc_config
        self._alert_store = alert_store

        self._running = False
        self._task: Optional[asyncio.Task[None]] = None

        # Previous snapshot for diffing: {name: (state, start_mode)}
        self._previous: Dict[str, Tuple[str, str]] = {}
        self._latest_services: List[Dict[str, Any]] = []

    # -- Filtering

    def _is_monitored(self, name: str) -> bool:
        names = self._svc_config.monitored_names
        if not names:
            return True
        return name.lower() in {n.lower() for n in names}

    # -- Control

    async def run(self) -> None:
        if self._running:
            return
        self._running = True
        logger.info(
            "ServiceMonitor started (interval=%.1fs)",
            self._mon_config.interval_seconds,
        )

        # Prime the snapshot.
        services = _query_services_wmi()
        self._previous = {
            s["name"]: (s["state"], s["start_mode"])
            for s in services
            if self._is_monitored(s["name"])
        }
        self._latest_services = services

        while self._running:
            try:
                self._poll()
            except Exception:
                logger.exception("Error in service polling cycle")
            await asyncio.sleep(self._mon_config.interval_seconds)

    async def stop(self) -> None:
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("ServiceMonitor stopped")

    def status(self) -> Dict[str, Any]:
        return {
            "running": self._running,
            "enabled": self._mon_config.enabled,
            "tracked_services": len(self._previous),
            "total_services": len(self._latest_services),
        }

    # -- Polling

    def _poll(self) -> None:
        services = _query_services_wmi()
        self._latest_services = services

        current: Dict[str, Tuple[str, str]] = {
            s["name"]: (s["state"], s["start_mode"])
            for s in services
            if self._is_monitored(s["name"])
        }

        current_names: Set[str] = set(current.keys())
        previous_names: Set[str] = set(self._previous.keys())

        # --- New services ---
        if self._svc_config.alert_on_new_service:
            new_names = current_names - previous_names
            for name in sorted(new_names):
                state, mode = current[name]
                self._alert_store.info(
                    AlertType.SYSTEM,
                    f"[Service] New service created: {name}",
                    service_name=name,
                    state=state,
                    start_mode=mode,
                    group_key=f"service:new:{name}",
                )

        # --- Removed services ---
        removed_names = previous_names - current_names
        for name in sorted(removed_names):
            state, mode = self._previous[name]
            self._alert_store.warn(
                AlertType.SYSTEM,
                f"[Service] Service removed: {name}",
                service_name=name,
                last_state=state,
                group_key=f"service:removed:{name}",
            )

        # --- State changes ---
        if self._svc_config.alert_on_state_change:
            common = current_names & previous_names
            for name in sorted(common):
                old_state, _ = self._previous[name]
                new_state, _ = current[name]
                if old_state != new_state:
                    self._alert_store.warn(
                        AlertType.SYSTEM,
                        f"[Service] State changed: {name} → {new_state}",
                        service_name=name,
                        old_state=old_state,
                        new_state=new_state,
                        group_key=f"service:state:{name}",
                    )

        self._previous = current

    @property
    def latest_services(self) -> List[Dict[str, Any]]:
        return self._latest_services
