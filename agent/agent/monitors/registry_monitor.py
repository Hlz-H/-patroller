"""Registry monitor for 巡查者 agent.

Monitors critical Windows registry keys for changes — additions, deletions,
and value modifications.  Uses polling with snapshot diffs via the built-in
``winreg`` module so no extra dependencies are needed.

Key areas watched by default:
  - ``HKLM\\...\\Run``, ``RunOnce`` — auto-start entries
  - ``HKCU\\...\\Run`` — user auto-start entries
  - ``HKLM\\...\\ShellServiceObjectDelayLoad`` — browser helper objects
  - ``HKLM\\System\\CurrentControlSet\\Services`` — service entries

On non-Windows platforms this monitor degrades gracefully (no-op).
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List, Optional, Set, Tuple

from agent.alert import AlertStore, AlertType
from agent.config import MonitorConfig, RegistryConfig

logger = logging.getLogger(__name__)

# Windows registry helpers

_HIVE_MAP: Dict[str, int] = {}
_REG_AVAILABLE = False

try:
    import winreg

    _HIVE_MAP = {
        "HKEY_LOCAL_MACHINE": winreg.HKEY_LOCAL_MACHINE,
        "HKEY_CURRENT_USER": winreg.HKEY_CURRENT_USER,
        "HKEY_USERS": winreg.HKEY_USERS,
        "HKEY_CLASSES_ROOT": winreg.HKEY_CLASSES_ROOT,
        "HKEY_CURRENT_CONFIG": winreg.HKEY_CURRENT_CONFIG,
    }
    _REG_AVAILABLE = True
except ImportError:
    logger.warning("winreg not available — registry monitoring disabled")


def _parse_key_path(path: str) -> Optional[Tuple[int, str]]:
    """Parse a config key path like ``HKLM\\Software\\Run`` into (hive, subkey).

    Returns ``None`` if the hive prefix is unknown.
    """
    parts = path.split("\\", 1)
    if len(parts) < 1:
        return None
    hive_str = parts[0].upper()
    alias = {
        "HKLM": "HKEY_LOCAL_MACHINE",
        "HKCU": "HKEY_CURRENT_USER",
        "HKU": "HKEY_USERS",
        "HKCR": "HKEY_CLASSES_ROOT",
    }
    hive_str = alias.get(hive_str, hive_str)
    hive = _HIVE_MAP.get(hive_str)
    if hive is None:
        logger.warning("Unknown registry hive: %s", hive_str)
        return None
    subkey = parts[1] if len(parts) > 1 else ""
    return (hive, subkey)


def _read_key_values(hive: int, subkey: str) -> Dict[str, Any]:
    """Read all value names + data under a registry key.

    Returns a dict of ``{value_name: value_data}``.  On error returns empty.
    """
    result: Dict[str, Any] = {}
    if not _REG_AVAILABLE:
        return result
    try:
        with winreg.OpenKey(hive, subkey, 0, winreg.KEY_READ) as key:
            i = 0
            while True:
                try:
                    name, data, _ = winreg.EnumValue(key, i)
                    # Make data JSON-safe
                    if isinstance(data, bytes):
                        data = data.hex()
                    elif isinstance(data, int):
                        data = str(data)
                    result[name] = data
                    i += 1
                except OSError:
                    break
    except (FileNotFoundError, OSError):
        pass
    return result


def _snapshot(keys: List[str]) -> Dict[str, Dict[str, Any]]:
    """Take a full snapshot of all configured keys as ``{path: {values}}``."""
    snap: Dict[str, Dict[str, Any]] = {}
    for path in keys:
        parsed = _parse_key_path(path)
        if parsed is not None:
            hive, subkey = parsed
            snap[path] = _read_key_values(hive, subkey)
    return snap


# Registry monitor


class RegistryMonitor:
    """Async background monitor for Windows registry changes.

    Parameters
    ----------
    mon_config : MonitorConfig
    reg_config : RegistryConfig
    alert_store : AlertStore
    """

    def __init__(
        self,
        mon_config: MonitorConfig,
        reg_config: RegistryConfig,
        alert_store: AlertStore,
    ) -> None:
        self._mon_config = mon_config
        self._reg_config = reg_config
        self._alert_store = alert_store

        self._running = False
        self._task: Optional[asyncio.Task[None]] = None

        # Previous snapshot for diffing
        self._previous: Dict[str, Dict[str, Any]] = {}
        self._latest: Dict[str, Dict[str, Any]] = {}

    # -- Control

    async def run(self) -> None:
        if self._running:
            return
        self._running = True

        if not _REG_AVAILABLE:
            logger.warning("Registry monitoring not available on this platform")
            self._running = False
            return

        keys = self._reg_config.monitored_keys
        logger.info(
            "RegistryMonitor started (interval=%.1fs, keys=%d)",
            self._mon_config.interval_seconds,
            len(keys),
        )

        # Prime the snapshot.
        self._previous = _snapshot(keys)

        while self._running:
            try:
                self._poll()
            except Exception:
                logger.exception("Error in registry polling cycle")
            await asyncio.sleep(self._mon_config.interval_seconds)

    async def stop(self) -> None:
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("RegistryMonitor stopped")

    def status(self) -> Dict[str, Any]:
        return {
            "running": self._running,
            "enabled": self._mon_config.enabled,
            "tracked_keys": len(self._reg_config.monitored_keys),
            "available": _REG_AVAILABLE,
        }

    # -- Polling

    def _poll(self) -> None:
        """Execute one polling cycle: snapshot → diff → alert."""
        keys = self._reg_config.monitored_keys
        current = _snapshot(keys)
        self._latest = current

        for path in keys:
            old = self._previous.get(path, {})
            new = current.get(path, {})

            old_keys: Set[str] = set(old.keys())
            new_keys: Set[str] = set(new.keys())

            added = new_keys - old_keys
            for name in sorted(added):
                self._alert_store.warn(
                    AlertType.SYSTEM,
                    f"[Registry] New value added: {path}\\{name}",
                    registry_key=path,
                    value_name=name,
                    value=str(new[name])[:200],
                    group_key=f"registry:added:{path}\\{name}",
                )

            removed = old_keys - new_keys
            for name in sorted(removed):
                self._alert_store.warn(
                    AlertType.SYSTEM,
                    f"[Registry] Value removed: {path}\\{name}",
                    registry_key=path,
                    value_name=name,
                    group_key=f"registry:removed:{path}\\{name}",
                )

            common = old_keys & new_keys
            for name in sorted(common):
                if old[name] != new[name]:
                    self._alert_store.warn(
                        AlertType.SYSTEM,
                        f"[Registry] Value modified: {path}\\{name}",
                        registry_key=path,
                        value_name=name,
                        old_value=str(old[name])[:200],
                        new_value=str(new[name])[:200],
                        group_key=f"registry:modified:{path}\\{name}",
                    )

        self._previous = current

    @property
    def latest_snapshot(self) -> Dict[str, Dict[str, Any]]:
        return self._latest
