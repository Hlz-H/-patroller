from __future__ import annotations

import logging
from typing import Dict, Optional

from agent.config import SmartControlConfig

logger = logging.getLogger(__name__)

# Thresholds for health-score-based scaling.
_IDLE_THRESHOLD = 80.0
_STRESS_THRESHOLD = 50.0
_CRITICAL_THRESHOLD = 20.0


class AdaptiveTuner:
    """Adjusts monitor polling intervals based on system health score.

    The tuner computes an interval multiplier per health band so that
    monitors run less often during idle periods and more often under
    stress, conserving resources when they are not needed.
    """

    def __init__(self, config: SmartControlConfig) -> None:
        self._config = config
        self._multiplier: float = 1.0

    @property
    def multiplier(self) -> float:
        return self._multiplier

    def adjust(self, health_score: float) -> float:
        """Compute and store a new interval multiplier for *health_score*.

        Returns the new multiplier for callers that want to log it.
        """
        if health_score >= _IDLE_THRESHOLD:
            self._multiplier = self._config.tuner.idle_multiplier
        elif health_score >= _STRESS_THRESHOLD:
            self._multiplier = 1.0
        elif health_score >= _CRITICAL_THRESHOLD:
            self._multiplier = 0.5
        else:
            self._multiplier = self._config.tuner.stress_multiplier

        logger.debug("Tuner multiplier=%.2f (health=%.0f)", self._multiplier, health_score)
        return self._multiplier

    def adjusted_interval(self, base_interval: float) -> float:
        """Return *base_interval* scaled by the current multiplier."""
        return max(1.0, base_interval * self._multiplier)
