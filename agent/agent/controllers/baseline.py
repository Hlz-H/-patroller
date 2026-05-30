from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from agent.alert import AlertStore

logger = logging.getLogger(__name__)

_METRIC_KEYS = ("cpu_percent", "memory_percent", "disk_io_read_bytes", "disk_io_write_bytes")


class BaselineLearner:
    """Learns normal system metric baselines during quiet periods.

    A quiet period is defined as a contiguous window (``learning_period``
    seconds) during which no alerts were raised.  When such a period is
    detected the learner collects metric samples, computes mean and
    standard deviation, and persists the result so it can be loaded across
    agent restarts.
    """

    def __init__(self, alert_store: AlertStore, storage_path: str, learning_period: int = 7200) -> None:
        self._alert_store = alert_store
        self._storage_path = Path(storage_path)
        self._learning_period = learning_period
        self._samples: List[Dict[str, float]] = []
        self._baseline: Dict[str, Dict[str, float]] = {}
        self._quiet_start: Optional[float] = None

        self._load()

    # -- Public API --

    @property
    def baseline(self) -> Dict[str, Dict[str, float]]:
        return dict(self._baseline)

    def record_sample(self, metrics: Dict[str, Any]) -> None:
        """Feed a metric snapshot to the learner.

        The method checks whether the system is in a quiet period.  If it
        has been quiet long enough it collects the sample; otherwise it
        resets the quiet timer.
        """
        now = time.time()
        recent = [a for a in self._alert_store.get_all() if now - a.timestamp < self._learning_period]

        if not recent:
            if self._quiet_start is None:
                self._quiet_start = now
                self._samples.clear()

            elapsed = now - self._quiet_start
            if elapsed >= self._learning_period:
                sample = {k: metrics.get(k, 0.0) for k in _METRIC_KEYS}
                self._samples.append(sample)
                logger.debug("Baseline sample #%d collected", len(self._samples))

                if len(self._samples) >= 30:
                    self._compute_baseline()
        else:
            self._quiet_start = None

    def is_baseline_ready(self) -> bool:
        return bool(self._baseline)

    # -- Internals --

    def _compute_baseline(self) -> None:
        if not self._samples:
            return

        baseline: Dict[str, Dict[str, float]] = {}
        for key in _METRIC_KEYS:
            values = [s[key] for s in self._samples]
            n = len(values)
            if n < 2:
                continue
            mean = sum(values) / n
            variance = sum((v - mean) ** 2 for v in values) / (n - 1)
            std = variance ** 0.5
            baseline[key] = {"mean": round(mean, 2), "std": round(std, 2)}

        self._baseline = baseline
        self._persist()

        logger.info("Baseline computed from %d samples: %s", len(self._samples), baseline)

    def _persist(self) -> None:
        try:
            self._storage_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self._storage_path, "w", encoding="utf-8") as fh:
                json.dump(self._baseline, fh, indent=2)
        except OSError:
            logger.exception("Failed to persist baseline to %s", self._storage_path)

    def _load(self) -> None:
        if not self._storage_path.exists():
            return

        try:
            with open(self._storage_path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except (json.JSONDecodeError, OSError):
            logger.warning("Baseline file corrupted, ignoring")
            return

        if not self._validate(data):
            logger.warning("Baseline file failed validation, ignoring")
            return

        self._baseline = data
        logger.info("Loaded baseline from %s (%d metrics)", self._storage_path, len(data))

    def _validate(self, data: Any) -> bool:
        if not isinstance(data, dict):
            return False
        for key, val in data.items():
            if not isinstance(val, dict):
                return False
            if "mean" not in val or "std" not in val:
                return False
            if not isinstance(val["mean"], (int, float)):
                return False
            if not isinstance(val["std"], (int, float)):
                return False
            if val["mean"] < 0 or val["std"] < 0:
                return False
            if val["std"] > 100:
                return False  # unreasonably large std
        return True
