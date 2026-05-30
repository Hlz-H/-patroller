"""Process monitor for 巡查者 agent.

Tracks running processes, detects new process creation (by polling
diffs), enforces whitelist/blacklist rules, and kills blacklisted
processes. Alerts are raised via the agent's AlertStore.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

import psutil

from agent.alert import AlertSeverity, AlertStore, AlertType
from agent.config import MonitorConfig, ProcessConfig

logger = logging.getLogger(__name__)

# Callback when a list of process dicts is ready.
ProcessSnapshotCallback = Callable[[List[Dict[str, Any]]], None]


class ProcessMonitor:
    """Async background monitor for process management.

    Parameters
    ----------
    mon_config : MonitorConfig
    proc_config : ProcessConfig
    alert_store : AlertStore
        Alert system for raising process-related alerts.
    """

    def __init__(
        self,
        mon_config: MonitorConfig,
        proc_config: ProcessConfig,
        alert_store: AlertStore,
    ) -> None:
        self._mon_config = mon_config
        self._proc_config = proc_config
        self._alert_store = alert_store

        self._callback: Optional[ProcessSnapshotCallback] = None
        self._running = False
        self._task: Optional[asyncio.Task[None]] = None

        # Track PIDs from the previous polling cycle for new-process detection.
        self._previous_pids: Set[int] = set()
        self._latest_snapshot: List[Dict[str, Any]] = []

        # Cache whitelist / blacklist as lower-case sets for fast lookup.
        self._whitelist: Set[str] = set()
        self._blacklist: Set[str] = set()
        self._refresh_lists()

    # -- Control

    def set_callback(self, cb: ProcessSnapshotCallback) -> None:
        self._callback = cb

    def update_config(self, proc_config: ProcessConfig) -> None:
        self._proc_config = proc_config
        self._refresh_lists()
        logger.info("Process config updated: whitelist=%s, blacklist=%s",
                     self._whitelist, self._blacklist)

    async def run(self) -> None:
        if self._running:
            return
        self._running = True
        logger.info("ProcessMonitor started (interval=%.1fs)", self._mon_config.interval_seconds)

        # Prime the previous PID set with current processes.
        self._previous_pids = {p.pid for p in psutil.process_iter(["pid"])}

        while self._running:
            try:
                self._poll()
            except Exception:
                logger.exception("Error in process polling cycle")
            await asyncio.sleep(self._mon_config.interval_seconds)

    async def stop(self) -> None:
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("ProcessMonitor stopped")

    def status(self) -> Dict[str, Any]:
        return {
            "running": self._running,
            "enabled": self._mon_config.enabled,
            "tracked_processes": len(self._latest_snapshot),
            "blacklist_entries": len(self._blacklist),
        }

    # -- Data collection

    def _poll(self) -> List[Dict[str, Any]]:
        current_pids: Set[int] = set()
        snapshot: List[Dict[str, Any]] = []

        for proc in psutil.process_iter(
            ["pid", "name", "exe", "cpu_percent", "memory_percent", "status"]
        ):
            try:
                info = proc.info
                pid = info["pid"]
                name = info["name"] or ""
                exe = info["exe"] or ""

                if pid is None:
                    continue
                current_pids.add(pid)

                proc_dict: Dict[str, Any] = {
                    "pid": pid,
                    "name": name,
                    "exe": exe,
                    "cpu_percent": info.get("cpu_percent", 0.0),
                    "memory_percent": info.get("memory_percent", 0.0),
                    "status": info.get("status", ""),
                }
                snapshot.append(proc_dict)

                if self._is_blacklisted(name, exe) and not self._is_whitelisted(name, exe):
                    self._handle_blacklisted(proc, name, exe, pid)

            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue

        new_pids = current_pids - self._previous_pids
        if new_pids:
            # Only report new processes that aren't blacklisted (those already alerted).
            for pid in new_pids:
                try:
                    p = psutil.Process(pid)
                    pname = p.name() or ""
                    pexe = p.exe() or ""
                    if not self._is_blacklisted(pname, pexe):
                        self._alert_store.info(
                            AlertType.PROCESS,
                            f"New process started: {pname}",
                            pid=pid,
                            name=pname,
                            exe=pexe,
                            group_key=f"process:new:{pname}",
                        )
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass

        self._previous_pids = current_pids
        self._latest_snapshot = snapshot

        if self._callback:
            self._callback(snapshot)

        return snapshot

    # -- Blacklist / whitelist logic

    def _refresh_lists(self) -> None:
        self._whitelist = {n.lower() for n in self._proc_config.whitelist}
        self._blacklist = {n.lower() for n in self._proc_config.blacklist}

    def _is_whitelisted(self, name: str, exe: str) -> bool:
        name_l = name.lower()
        return name_l in self._whitelist

    def _is_blacklisted(self, name: str, exe: str) -> bool:
        name_l = name.lower()
        return name_l in self._blacklist

    def _handle_blacklisted(
        self, proc: psutil.Process, name: str, exe: str, pid: int
    ) -> None:
        self._alert_store.critical(
            AlertType.PROCESS,
            f"Blacklisted process detected: {name}",
            pid=pid,
            name=name,
            exe=exe,
            group_key=f"process:blacklisted:{name}",
        )

        try:
            proc.kill()
            logger.info("Killed blacklisted process %s (PID %d)", name, pid)
            self._alert_store.info(
                AlertType.PROCESS,
                f"Killed blacklisted process: {name} (PID {pid})",
                pid=pid,
                name=name,
                group_key=f"process:killed:{name}",
            )
        except (psutil.NoSuchProcess, psutil.AccessDenied) as exc:
            logger.warning("Failed to kill %s (PID %d): %s", name, pid, exc)

    # -- Public helpers

    def kill_process(self, pid: int) -> Tuple[bool, str]:
        try:
            proc = psutil.Process(pid)
            name = proc.name()
            proc.kill()
            msg = f"Process {name} (PID {pid}) killed"
            logger.info(msg)
            self._alert_store.info(AlertType.PROCESS, msg, pid=pid, name=name, group_key=f"process:killed:{name}")
            self._previous_pids.discard(pid)
            return True, msg
        except psutil.NoSuchProcess:
            return False, f"No such process: PID {pid}"
        except psutil.AccessDenied:
            return False, f"Access denied when killing PID {pid}"

    @property
    def latest_snapshot(self) -> List[Dict[str, Any]]:
        return self._latest_snapshot
