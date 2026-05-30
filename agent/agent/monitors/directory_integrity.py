"""Directory integrity monitor for 巡查者 agent.

Monitors critical directories for file changes — additions, modifications,
and deletions.  Uses polling with stat-based diffs (ctime, mtime, size) or
optional SHA-256 hashing.

Target directories include:
  - ``C:\\Windows\\System32\\drivers\\etc`` — hosts file tampering
  - ``C:\\Program Files`` — program install/removal
  - User-configurable paths
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from agent.alert import AlertStore, AlertType
from agent.config import DirectoryIntegrityConfig, MonitorConfig

logger = logging.getLogger(__name__)


@dataclass
class FileEntry:
    """Snapshot of a single file's identity."""

    path: str
    size: int
    mtime: float  # modification time
    hash: str = ""  # SHA-256 (empty if check_hash is False)


def _scan_directory(
    path: Path, recursive: bool, compute_hash: bool
) -> Dict[str, FileEntry]:
    """Scan a directory and return a dict of {file_path: FileEntry}.

    Only regular files are included.
    """
    entries: Dict[str, FileEntry] = {}
    if not path.is_dir():
        logger.warning("Directory not found, skipping: %s", path)
        return entries

    try:
        it = path.rglob("*") if recursive else path.glob("*")
        for entry in it:
            try:
                if not entry.is_file():
                    continue
                stat = entry.stat()
                file_hash = ""
                if compute_hash:
                    try:
                        file_hash = hashlib.sha256(
                            entry.read_bytes()
                        ).hexdigest()[:16]  # short hash for perf
                    except (IOError, PermissionError):
                        file_hash = "<error>"
                entries[str(entry)] = FileEntry(
                    path=str(entry),
                    size=stat.st_size,
                    mtime=stat.st_mtime,
                    hash=file_hash,
                )
            except (PermissionError, OSError):
                continue
    except (PermissionError, FileNotFoundError):
        logger.warning("Permission denied scanning: %s", path)
    return entries


# Directory integrity monitor


class DirectoryIntegrityMonitor:
    """Async background monitor for critical directory integrity.

    Parameters
    ----------
    mon_config : MonitorConfig
    dir_config : DirectoryIntegrityConfig
    alert_store : AlertStore
    """

    def __init__(
        self,
        mon_config: MonitorConfig,
        dir_config: DirectoryIntegrityConfig,
        alert_store: AlertStore,
    ) -> None:
        self._mon_config = mon_config
        self._dir_config = dir_config
        self._alert_store = alert_store

        self._running = False
        self._task: Optional[asyncio.Task[None]] = None

        # Per-directory snapshots: {dir_path: {file_path: FileEntry}}
        self._previous: Dict[str, Dict[str, FileEntry]] = {}
        self._latest: Dict[str, Dict[str, FileEntry]] = {}

    # -- Control

    async def run(self) -> None:
        if self._running:
            return
        self._running = True
        paths = self._dir_config.monitored_paths

        logger.info(
            "DirectoryIntegrityMonitor started (interval=%.1fs, paths=%d)",
            self._mon_config.interval_seconds,
            len(paths),
        )

        # Prime the snapshots.
        for p in paths:
            pp = Path(p)
            if pp.is_dir():
                self._previous[p] = _scan_directory(
                    pp, self._dir_config.watch_recursive, self._dir_config.check_hash
                )
            else:
                logger.warning("Monitored path not found: %s", p)

        while self._running:
            try:
                self._poll()
            except Exception:
                logger.exception("Error in directory integrity polling cycle")
            await asyncio.sleep(self._mon_config.interval_seconds)

    async def stop(self) -> None:
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("DirectoryIntegrityMonitor stopped")

    def status(self) -> Dict[str, Any]:
        total_files = sum(len(e) for e in self._latest.values())
        return {
            "running": self._running,
            "enabled": self._mon_config.enabled,
            "monitored_paths": len(self._dir_config.monitored_paths),
            "tracked_files": total_files,
        }

    # -- Polling

    def _poll(self) -> None:
        current: Dict[str, Dict[str, FileEntry]] = {}

        for p in self._dir_config.monitored_paths:
            pp = Path(p)
            if not pp.is_dir():
                continue
            current[p] = _scan_directory(
                pp, self._dir_config.watch_recursive, self._dir_config.check_hash
            )

            old_files = self._previous.get(p, {})
            new_files = current[p]

            old_keys: Set[str] = set(old_files.keys())
            new_keys: Set[str] = set(new_files.keys())

            # --- New files ---
            added = new_keys - old_keys
            for f in sorted(added):
                entry = new_files[f]
                self._alert_store.warn(
                    AlertType.SYSTEM,
                    f"[DirIntegrity] File created: {f}",
                    directory=p,
                    file_path=f,
                    size=entry.size,
                    group_key=f"dir:created:{f}",
                )

            # --- Deleted files ---
            deleted = old_keys - new_keys
            for f in sorted(deleted):
                entry = old_files[f]
                self._alert_store.critical(
                    AlertType.SYSTEM,
                    f"[DirIntegrity] File deleted: {f}",
                    directory=p,
                    file_path=f,
                    last_size=entry.size,
                    group_key=f"dir:deleted:{f}",
                )

            # --- Modified files ---
            common = old_keys & new_keys
            for f in sorted(common):
                old_entry = old_files[f]
                new_entry = new_files[f]
                change_signals: List[str] = []
                if old_entry.size != new_entry.size:
                    change_signals.append(f"size {old_entry.size}→{new_entry.size}")
                if abs(old_entry.mtime - new_entry.mtime) > 0.5:
                    change_signals.append("mtime changed")
                if self._dir_config.check_hash and old_entry.hash != new_entry.hash:
                    change_signals.append("hash mismatch")

                if change_signals:
                    self._alert_store.warn(
                        AlertType.SYSTEM,
                        f"[DirIntegrity] File modified: {f}",
                        directory=p,
                        file_path=f,
                        changes=", ".join(change_signals),
                        group_key=f"dir:modified:{f}",
                    )

        self._previous = current
        self._latest = current

    @property
    def latest_snapshot(self) -> Dict[str, Dict[str, Any]]:
        result: Dict[str, Dict[str, Any]] = {}
        for dir_path, files in self._latest.items():
            result[dir_path] = {
                f: {"size": e.size, "mtime": e.mtime, "hash": e.hash}
                for f, e in files.items()
            }
        return result
