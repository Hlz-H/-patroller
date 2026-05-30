"""Alert engine for 巡查者 agent.

Provides alert data models, an in-memory alert store, and a callback
system so that multiple consumers (API WebSocket, system tray, future
notification services) can subscribe to new alerts.
"""

from __future__ import annotations

import hashlib
import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

# -- Enums & data model --


class AlertSeverity(str, Enum):
    """Severity level for an alert."""

    INFO = "info"
    WARN = "warn"
    CRITICAL = "critical"


class AlertType(str, Enum):
    """Category of the alert."""

    PROCESS = "process"
    USB = "usb"
    SYSTEM = "system"
    SANDBOX = "sandbox"


@dataclass
class Alert:
    """A single alert raised by the agent."""

    alert_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: float = field(default_factory=time.time)
    alert_type: AlertType = AlertType.SYSTEM
    severity: AlertSeverity = AlertSeverity.INFO
    message: str = ""
    details: Dict[str, Any] = field(default_factory=dict)
    count: int = 1
    group_key: str = ""
    action_taken: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert alert to a serialisable dict (for API / WebSocket)."""
        return {
            "alert_id": self.alert_id,
            "timestamp": self.timestamp,
            "type": self.alert_type.value,
            "severity": self.severity.value,
            "message": self.message,
            "details": self.details,
            "count": self.count,
        }


# Type alias for alert callbacks.
AlertCallback = Callable[[Alert], None]


# -- Alert store --


class AlertStore:
    """In-memory alert history with a configurable max size.

    Also manages a list of callbacks that are invoked for every new alert.
    """

    _MAX_ALERTS = 1000

    def __init__(self, dedup_window: float = 60.0, aggregation_window: float = 60.0) -> None:
        self._alerts: List[Alert] = []
        self._callbacks: List[AlertCallback] = []
        self._suppressed: Dict[str, float] = {}
        self._recent_fingerprints: Dict[str, float] = {}
        self._dedup_window = dedup_window
        self._aggregation_window = aggregation_window

    # -- Alert management --

    def add(self, alert: Alert) -> None:
        self._alerts.append(alert)
        if len(self._alerts) > self._MAX_ALERTS:
            self._alerts = self._alerts[-self._MAX_ALERTS :]

        logger.debug(
            "Alert [%s] %s: %s",
            alert.severity.value.upper(),
            alert.alert_type.value,
            alert.message,
        )

        for cb in self._callbacks:
            try:
                cb(alert)
            except Exception:
                logger.exception("Alert callback raised an exception")

    def get_all(self) -> List[Alert]:
        """Return all stored alerts (most recent last)."""
        return list(self._alerts)

    def get_recent(self, count: int = 50) -> List[Alert]:
        return self._alerts[-count:]

    def get_by_severity(self, severity: AlertSeverity) -> List[Alert]:
        return [a for a in self._alerts if a.severity == severity]

    # -- Callback management --

    def subscribe(self, callback: AlertCallback) -> None:
        self._callbacks.append(callback)

    def unsubscribe(self, callback: AlertCallback) -> None:
        self._callbacks.remove(callback)

    # -- Convenience helpers --

    def info(self, alert_type: AlertType, message: str, group_key: str = "", **details: Any) -> Alert:
        """Create and store an INFO-level alert with optional aggregation group_key."""
        alert = Alert(
            alert_type=alert_type,
            severity=AlertSeverity.INFO,
            message=message,
            details=details,
            group_key=group_key,
        )
        self.add_with_policy(alert)
        return alert

    def warn(self, alert_type: AlertType, message: str, group_key: str = "", **details: Any) -> Alert:
        """Create and store a WARN-level alert with optional aggregation group_key."""
        alert = Alert(
            alert_type=alert_type,
            severity=AlertSeverity.WARN,
            message=message,
            details=details,
            group_key=group_key,
        )
        self.add_with_policy(alert)
        return alert

    def critical(self, alert_type: AlertType, message: str, group_key: str = "", **details: Any) -> Alert:
        """Create and store a CRITICAL-level alert with optional aggregation group_key."""
        alert = Alert(
            alert_type=alert_type,
            severity=AlertSeverity.CRITICAL,
            message=message,
            details=details,
            group_key=group_key,
        )
        self.add_with_policy(alert)
        return alert

    # -- Suppression (manual silence) --

    def suppress(self, key: str, duration: float) -> None:
        self._suppressed[key] = time.time() + duration

    def unsuppress(self, key: str) -> None:
        self._suppressed.pop(key, None)

    def get_suppressed(self) -> Dict[str, float]:
        """Return current suppression rules (key → expiry timestamp)."""
        self._clean_expired_suppressions()
        return dict(self._suppressed)

    def _clean_expired_suppressions(self) -> None:
        now = time.time()
        expired = [k for k, v in self._suppressed.items() if v <= now]
        for k in expired:
            del self._suppressed[k]

    def _is_suppressed(self, alert: Alert) -> bool:
        self._clean_expired_suppressions()
        if not self._suppressed:
            return False
        now = time.time()
        for key, expiry in self._suppressed.items():
            if expiry > now:
                if key in alert.alert_type.value or key in alert.message.lower():
                    return True
        return False

    # -- Deduplication & aggregation --

    def _fingerprint(self, alert: Alert) -> str:
        """Produce a stable hash used for exact-match deduplication."""
        raw = f"{alert.alert_type.value}|{alert.severity.value}|{alert.message}"
        return hashlib.md5(raw.encode()).hexdigest()

    def _clean_old_fingerprints(self) -> None:
        now = time.time()
        self._recent_fingerprints = {
            k: v for k, v in self._recent_fingerprints.items()
            if now - v < self._dedup_window * 2
        }

    def add_with_policy(
        self,
        alert: Alert,
        dedup_window: float | None = None,
        aggregation_window: float | None = None,
    ) -> Alert | None:
        """Add *alert* applying suppression, dedup, then aggregation.

        Parameters
        ----------
        alert:
            The alert to add.
        dedup_window:
            Seconds for exact-match dedup.  ``None`` → use instance default.
        aggregation_window:
            Seconds for group-key aggregation.  ``None`` → use instance default.
            When ``0`` aggregation is skipped even if *group_key* is set.

        Returns
        -------
        The :class:`Alert` that was actually stored, or ``None`` when the alert
        was entirely suppressed.
        """
        # 1 — Suppression check
        if self._is_suppressed(alert):
            logger.debug("Alert suppressed: %s", alert.message)
            return None

        dw = dedup_window if dedup_window is not None else self._dedup_window
        aw = aggregation_window if aggregation_window is not None else self._aggregation_window
        now = time.time()

        # 2 — Exact-match dedup
        fp = self._fingerprint(alert)
        if dw > 0 and fp in self._recent_fingerprints:
            age = now - self._recent_fingerprints[fp]
            if age < dw:
                logger.debug("Alert deduplicated: %s (age=%.1fs)", alert.message, age)
                return None  # silently dropped – exact duplicate

        # 3 — Group-key aggregation
        if aw > 0 and alert.group_key:
            for existing in reversed(self._alerts):
                if existing.group_key == alert.group_key:
                    age = now - existing.timestamp
                    if age < aw:
                        # Merge into existing alert
                        existing.count += 1
                        existing.timestamp = now
                        # Merge detail lists
                        for k, v in alert.details.items():
                            if k not in existing.details:
                                existing.details[k] = v
                            elif isinstance(existing.details[k], list) and isinstance(v, list):
                                existing.details[k].extend(v)
                        logger.debug(
                            "Alert aggregated into %s (count=%d, group=%s)",
                            existing.alert_id, existing.count, alert.group_key,
                        )
                        for cb in self._callbacks:
                            try:
                                cb(existing)
                            except Exception:
                                logger.exception("Alert aggregation callback error")
                        return existing
                    break  # only check the most recent matching alert

        # 4 — Record fingerprint for future dedup
        self._recent_fingerprints[fp] = now
        self._clean_old_fingerprints()

        # 5 — Normal add
        self.add(alert)
        return alert
