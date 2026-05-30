from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List

from agent.alert import Alert, AlertSeverity, AlertStore

logger = logging.getLogger(__name__)


@dataclass
class SystemState:
    """Snapshot of system health and alert status."""

    health_score: float = 100.0  # 0 (critical) → 100 (perfect)
    recent_alerts: List[Alert] = field(default_factory=list)
    alert_count_critical: int = 0
    alert_count_warning: int = 0
    alert_count_info: int = 0
    summary: str = ""


class StateEvaluator:
    """Collects monitor metrics and alerts, computes a health score."""

    def __init__(self, alert_store: AlertStore) -> None:
        self._alert_store = alert_store

    def evaluate(self) -> SystemState:
        """Take a snapshot: assess recent alerts and return a SystemState."""
        now = time.time()
        recent = [
            a for a in self._alert_store.get_all()
            if now - a.timestamp < 60.0
        ]

        crit = sum(1 for a in recent if a.severity == AlertSeverity.CRITICAL)
        warn = sum(1 for a in recent if a.severity == AlertSeverity.WARN)
        info = sum(1 for a in recent if a.severity == AlertSeverity.INFO)

        score = 100.0
        score -= crit * 30.0
        score -= warn * 15.0
        score -= info * 5.0
        score = max(0.0, min(100.0, score))

        if score >= 80:
            label = "healthy"
        elif score >= 50:
            label = "mild"
        elif score >= 20:
            label = "stressed"
        else:
            label = "critical"

        summary = (
            f"health={label}({score:.0f}) "
            f"alerts={len(recent)}[crit:{crit} warn:{warn} info:{info}]"
        )

        return SystemState(
            health_score=score,
            recent_alerts=recent,
            alert_count_critical=crit,
            alert_count_warning=warn,
            alert_count_info=info,
            summary=summary,
        )
