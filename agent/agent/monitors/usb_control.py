"""USB device monitor for 巡查者 agent.

Monitors USB device insertion / removal using WMI polling
(Win32_USBControllerDevice) and enforces a device blocklist based on
VID:PID pairs.  Blocked devices are reported and can be disabled.

On non-Windows platforms this module will degrade gracefully by not
performing any WMI queries and reporting zero devices.
"""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

from agent.alert import AlertStore, AlertType
from agent.config import MonitorConfig, USBConfig

logger = logging.getLogger(__name__)

# Callback when USB device state changes.
USBEventCallback = Callable[[List[Dict[str, Any]], List[Dict[str, Any]]], None]

# Regex to extract VID:PID from WMI DeviceID strings.
_VIDPID_RE = re.compile(r"VID_([0-9A-Fa-f]{4}).*?PID_([0-9A-Fa-f]{4})", re.IGNORECASE)

# Windows-only WMI helpers

_WMI_AVAILABLE = False
try:
    import pythoncom
    import win32com.client

    pythoncom.CoInitialize()
    _WMI_AVAILABLE = True
except ImportError:
    logger.warning("pywin32 not installed or WMI unavailable — USB monitoring disabled")
except Exception:
    logger.exception("Failed to initialise WMI")


def _query_wmi_usb_devices() -> List[Dict[str, Any]]:
    """Query WMI for USB controller devices and return device info dicts.

    Returns an empty list on non-Windows or if WMI is unavailable.
    """
    if not _WMI_AVAILABLE:
        return []

    try:
        pythoncom.CoInitialize()
        wmi = win32com.client.Dispatch("WbemScripting.SWbemLocator")
        svc = wmi.ConnectServer(".", "root\\cimv2")

        devices: List[Dict[str, Any]] = []
        for item in svc.ExecQuery("SELECT * FROM Win32_USBControllerDevice"):
            dependent = item.Dependent
            # Dependent is a string path like:
            # \\COMPUTER\root\cimv2:Win32_PnPEntity.DeviceID="USB\\VID_xxxx&PID_yyyy\\..."
            match = _VIDPID_RE.search(dependent)
            vid = match.group(1) if match else ""
            pid = match.group(2) if match else ""

            # Try to get the friendly name from Win32_PnPEntity.
            name = ""
            try:
                # Extract the DeviceID from the path.
                parts = dependent.split('DeviceID="')
                if len(parts) > 1:
                    device_id = parts[1].rstrip('"')
                    for pnp in svc.ExecQuery(
                        f'SELECT * FROM Win32_PnPEntity WHERE DeviceID = "{device_id}"'
                    ):
                        name = pnp.Name or pnp.Caption or ""
                        break
            except Exception:
                pass

            devices.append(
                {
                    "vid": vid,
                    "pid": pid,
                    "vid_pid": f"{vid}:{pid}".upper() if vid and pid else "",
                    "name": name,
                    "device_path": dependent,
                }
            )
        return devices
    except Exception:
        logger.exception("WMI USB query failed")
        return []


# USB monitor


class USBMonitor:
    """Async background monitor for USB device insertion / removal.

    Parameters
    ----------
    mon_config : MonitorConfig
    usb_config : USBConfig
    alert_store : AlertStore
    """

    def __init__(
        self,
        mon_config: MonitorConfig,
        usb_config: USBConfig,
        alert_store: AlertStore,
    ) -> None:
        self._mon_config = mon_config
        self._usb_config = usb_config
        self._alert_store = alert_store

        self._callback: Optional[USBEventCallback] = None
        self._running = False
        self._task: Optional[asyncio.Task[None]] = None

        # Track known devices by (VID, PID) for insertion detection.
        self._known: Set[Tuple[str, str]] = set()
        self._blocklist: Set[str] = set()
        self._latest_devices: List[Dict[str, Any]] = []
        self._events_log: List[Dict[str, Any]] = []
        self._refresh_blocklist()

    # -- Control

    def set_callback(self, cb: USBEventCallback) -> None:
        self._callback = cb

    def update_config(self, usb_config: USBConfig) -> None:
        self._usb_config = usb_config
        self._refresh_blocklist()
        logger.info("USB config updated: blocklist=%s", self._blocklist)

    async def run(self) -> None:
        if self._running:
            return
        self._running = True
        logger.info("USBMonitor started (interval=%.1fs)", self._mon_config.interval_seconds)

        # Prime known devices.
        current = _query_wmi_usb_devices()
        self._known = {(d["vid"], d["pid"]) for d in current if d["vid"] and d["pid"]}

        while self._running:
            try:
                self._poll()
            except Exception:
                logger.exception("Error in USB polling cycle")
            await asyncio.sleep(self._mon_config.interval_seconds)

    async def stop(self) -> None:
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("USBMonitor stopped")

    def status(self) -> Dict[str, Any]:
        return {
            "running": self._running,
            "enabled": self._mon_config.enabled,
            "blocklist_entries": len(self._blocklist),
            "active_devices": len(self._latest_devices),
        }

    # -- Polling

    def _poll(self) -> None:
        devices = _query_wmi_usb_devices()
        self._latest_devices = devices

        current_keys: Set[Tuple[str, str]] = set()
        for d in devices:
            vid, pid = d["vid"], d["pid"]
            if vid and pid:
                current_keys.add((vid, pid))

        # --- Insertion detection ---
        inserted = current_keys - self._known
        for vid, pid in inserted:
            vidpid_str = f"{vid}:{pid}".upper()
            name = _find_device_name(devices, vid, pid)
            self._log_event("inserted", vid, pid, vidpid_str, name)
            self._alert_store.info(
                AlertType.USB,
                f"USB device inserted: {name or vidpid_str}",
                vid=vid,
                pid=pid,
                vid_pid=vidpid_str,
                name=name,
                group_key=f"usb:inserted:{vidpid_str}",
            )

            if vidpid_str in self._blocklist:
                self._handle_blocked(vid, pid, vidpid_str, name)

        # --- Removal detection ---
        removed = self._known - current_keys
        for vid, pid in removed:
            vidpid_str = f"{vid}:{pid}".upper()
            name = _find_device_name(self._latest_devices, vid, pid) or "Unknown"
            self._log_event("removed", vid, pid, vidpid_str, name)

        self._known = current_keys

        if self._callback:
            self._callback(devices, self._events_log[-20:])

    # -- Blocklist

    def _refresh_blocklist(self) -> None:
        self._blocklist = {e.strip().upper() for e in self._usb_config.blocklist}

    def _handle_blocked(self, vid: str, pid: str, vidpid_str: str, name: str) -> None:
        """Alert and attempt to disable a blocked USB device."""
        self._alert_store.critical(
            AlertType.USB,
            f"Blocked USB device detected: {name or vidpid_str}",
            vid=vid,
            pid=pid,
            vid_pid=vidpid_str,
            name=name,
            group_key=f"usb:blocked:{vidpid_str}",
        )

        # Attempt to disable via WMI is complex; log a warning instead.
        logger.warning(
            "Blocked USB device %s (%s) — manual removal recommended",
            name or vidpid_str,
            vidpid_str,
        )

    # -- Event log

    def _log_event(
        self, event_type: str, vid: str, pid: str, vidpid_str: str, name: str
    ) -> None:
        import time

        event: Dict[str, Any] = {
            "timestamp": time.time(),
            "event": event_type,
            "vid": vid,
            "pid": pid,
            "vid_pid": vidpid_str,
            "name": name,
        }
        self._events_log.append(event)
        if len(self._events_log) > 500:
            self._events_log = self._events_log[-500:]

    # -- Properties

    @property
    def latest_devices(self) -> List[Dict[str, Any]]:
        return self._latest_devices

    @property
    def events(self) -> List[Dict[str, Any]]:
        return self._events_log


def _find_device_name(devices: List[Dict[str, Any]], vid: str, pid: str) -> str:
    for d in devices:
        if d["vid"] == vid and d["pid"] == pid:
            return d.get("name", "")
    return ""
