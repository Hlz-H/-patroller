"""System resource monitor for 巡查者 agent.

Collects CPU, memory, disk, and network metrics using psutil and
publishes them via an async callback. Runs as a background task
with a configurable polling interval.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

import psutil

from agent.config import MonitorConfig

logger = logging.getLogger(__name__)

# Callback type: receives a dict of metrics each poll cycle.
MetricsCallback = Callable[[Dict[str, Any]], None]


@dataclass
class SystemResourceMetrics:
    """Snapshot of system resource usage at a point in time."""

    # CPU
    cpu_percent: float = 0.0
    cpu_per_core: List[float] = field(default_factory=list)
    cpu_count_logical: int = 0
    cpu_count_physical: int = 0

    # Memory (bytes, unless noted)
    memory_total: int = 0
    memory_available: int = 0
    memory_used: int = 0
    memory_percent: float = 0.0

    # Swap
    swap_total: int = 0
    swap_used: int = 0
    swap_percent: float = 0.0

    # Disk (bytes)
    disk_partitions: List[Dict[str, Any]] = field(default_factory=list)
    disk_io_read_bytes: int = 0
    disk_io_write_bytes: int = 0

    # Network (bytes)
    net_bytes_sent: int = 0
    net_bytes_recv: int = 0
    net_connections: int = 0

    def to_dict(self) -> Dict[str, Any]:
        """Serialize all metrics to a JSON-safe dictionary."""
        return {
            "cpu": {
                "percent": round(self.cpu_percent, 1),
                "per_core": [round(v, 1) for v in self.cpu_per_core],
                "count_logical": self.cpu_count_logical,
                "count_physical": self.cpu_count_physical,
            },
            "memory": {
                "total": self.memory_total,
                "available": self.memory_available,
                "used": self.memory_used,
                "percent": round(self.memory_percent, 1),
            },
            "swap": {
                "total": self.swap_total,
                "used": self.swap_used,
                "percent": round(self.swap_percent, 1),
            },
            "disk": {
                "partitions": self.disk_partitions,
                "io_read_bytes": self.disk_io_read_bytes,
                "io_write_bytes": self.disk_io_write_bytes,
            },
            "network": {
                "bytes_sent": self.net_bytes_sent,
                "bytes_recv": self.net_bytes_recv,
                "connections": self.net_connections,
            },
        }


# System resource monitor


class SystemResourceMonitor:
    """Async background monitor for CPU / memory / disk / network metrics.

    Parameters
    ----------
    config : MonitorConfig
        Enable/interval configuration.

    Usage::

        monitor = SystemResourceMonitor(config)
        monitor.set_callback(my_handler)
        task = asyncio.create_task(monitor.run())
        # ... later ...
        await monitor.stop()
        await task
    """

    def __init__(self, config: MonitorConfig) -> None:
        self._config = config
        self._callback: Optional[MetricsCallback] = None
        self._running = False
        self._task: Optional[asyncio.Task[None]] = None
        self._latest: Optional[SystemResourceMetrics] = None

    # -- Control -------------------------------------------------------------

    def set_callback(self, cb: MetricsCallback) -> None:
        self._callback = cb

    async def run(self) -> None:
        if self._running:
            return
        self._running = True
        logger.info("SystemResourceMonitor started (interval=%.1fs)", self._config.interval_seconds)

        while self._running:
            try:
                metrics = self._collect()
                self._latest = metrics
                if self._callback:
                    self._callback(metrics.to_dict())
            except Exception:
                logger.exception("Error collecting system metrics")

            await asyncio.sleep(self._config.interval_seconds)

    async def stop(self) -> None:
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("SystemResourceMonitor stopped")

    def status(self) -> Dict[str, Any]:
        return {
            "running": self._running,
            "enabled": self._config.enabled,
            "interval_seconds": self._config.interval_seconds,
        }

    # -- Data collection

    def _collect(self) -> SystemResourceMetrics:
        """Gather all metrics in a single blocking call (OK for psutil)."""
        m = SystemResourceMetrics()

        # --- CPU ---
        m.cpu_percent = psutil.cpu_percent(interval=0.1)
        m.cpu_per_core = psutil.cpu_percent(interval=None, percpu=True)
        m.cpu_count_logical = psutil.cpu_count(logical=True) or 0
        m.cpu_count_physical = psutil.cpu_count(logical=False) or 0

        # --- Memory ---
        mem = psutil.virtual_memory()
        m.memory_total = mem.total
        m.memory_available = mem.available
        m.memory_used = mem.used
        m.memory_percent = mem.percent

        # --- Swap ---
        swap = psutil.swap_memory()
        m.swap_total = swap.total
        m.swap_used = swap.used
        m.swap_percent = swap.percent

        # --- Disk ---
        partitions: List[Dict[str, Any]] = []
        for part in psutil.disk_partitions(all=False):
            try:
                usage = psutil.disk_usage(part.mountpoint)
                partitions.append(
                    {
                        "device": part.device,
                        "mountpoint": part.mountpoint,
                        "fstype": part.fstype,
                        "total": usage.total,
                        "used": usage.used,
                        "free": usage.free,
                        "percent": usage.percent,
                    }
                )
            except PermissionError:
                partitions.append(
                    {
                        "device": part.device,
                        "mountpoint": part.mountpoint,
                        "fstype": part.fstype,
                        "total": 0,
                        "used": 0,
                        "free": 0,
                        "percent": 0.0,
                    }
                )
        m.disk_partitions = partitions

        # Disk I/O counters (cumulative since boot).
        try:
            io = psutil.disk_io_counters()
            if io:
                m.disk_io_read_bytes = io.read_bytes
                m.disk_io_write_bytes = io.write_bytes
        except Exception:
            pass

        # --- Network ---
        try:
            net = psutil.net_io_counters()
            if net:
                m.net_bytes_sent = net.bytes_sent
                m.net_bytes_recv = net.bytes_recv
        except Exception:
            pass

        try:
            m.net_connections = len(psutil.net_connections(kind="inet"))
        except Exception:
            pass

        return m

    @property
    def latest_metrics(self) -> Optional[Dict[str, Any]]:
        """Return the most recent metrics snapshot, or None."""
        if self._latest:
            return self._latest.to_dict()
        return None
