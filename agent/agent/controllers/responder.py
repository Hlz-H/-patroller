from __future__ import annotations

import logging
import time
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

from agent.alert import Alert, AlertSeverity, AlertStore, AlertType
from agent.config import SmartControlConfig

logger = logging.getLogger(__name__)


class ActionType(str, Enum):
    KILL_PROCESS = "kill_process"
    DISABLE_USB = "disable_usb"
    TRIGGER_SANDBOX = "trigger_sandbox"
    INCREASE_MONITORING = "increase_monitoring"
    CALL_LLM = "call_llm"
    LOG_ONLY = "log_only"


# Callback signatures for action execution.
KillProcessFn = Callable[[int], None]
DisableUsbFn = Callable[[], None]
SandboxFn = Callable[[str], None]
LlmAnalysisFn = Callable[[Alert], None]


class AlertResponder:
    """Matches incoming alerts against rules and executes actions.

    Critical alerts trigger automatic responses (kill process, disable USB,
    sandbox).  Repeated alerts of the same type invoke the LLM analyzer for
    deeper investigation.
    """

    def __init__(
        self,
        config: SmartControlConfig,
        alert_store: AlertStore,
        kill_process_fn: Optional[KillProcessFn] = None,
        disable_usb_fn: Optional[DisableUsbFn] = None,
        sandbox_fn: Optional[SandboxFn] = None,
        llm_analysis_fn: Optional[LlmAnalysisFn] = None,
    ) -> None:
        self._config = config
        self._alert_store = alert_store
        self._kill_process_fn = kill_process_fn
        self._disable_usb_fn = disable_usb_fn
        self._sandbox_fn = sandbox_fn
        self._llm_analysis_fn = llm_analysis_fn

        # Track alert type frequency for LLM escalation.
        self._type_frequencies: Dict[str, List[float]] = {}

    def process(self, state_alerts: List[Alert]) -> None:
        """Evaluate all recent alerts and execute matching actions."""
        self._clean_frequencies()

        for alert in state_alerts:
            action = self._match_rule(alert)
            if action == ActionType.LOG_ONLY:
                continue

            self._execute(alert, action)
            self._record_action(alert, action)

    def _match_rule(self, alert: Alert) -> ActionType:
        """Return the action that matches *alert* based on severity and type."""
        sev = alert.severity
        atype = alert.alert_type

        if not self._config.responder.enabled:
            return ActionType.LOG_ONLY

        if sev == AlertSeverity.CRITICAL and atype == AlertType.PROCESS:
            return ActionType.KILL_PROCESS

        if sev == AlertSeverity.CRITICAL and atype == AlertType.USB:
            if self._config.responder.auto_respond_critical:
                return ActionType.DISABLE_USB
            return ActionType.LOG_ONLY

        if sev == AlertSeverity.CRITICAL:
            if self._config.responder.auto_respond_critical:
                return ActionType.TRIGGER_SANDBOX
            return ActionType.LOG_ONLY

        if sev == AlertSeverity.WARN:
            self._track_type(alert)
            if self._exceeds_llm_threshold(alert):
                return ActionType.CALL_LLM
            if self._config.responder.auto_respond_warning:
                return ActionType.INCREASE_MONITORING
            return ActionType.LOG_ONLY

        return ActionType.LOG_ONLY

    def _execute(self, alert: Alert, action: ActionType) -> None:
        logger.info("Responder action=%s for alert=%s", action.value, alert.alert_id)

        try:
            if action == ActionType.KILL_PROCESS:
                pid = alert.details.get("pid", 0)
                if pid and self._kill_process_fn:
                    self._kill_process_fn(int(pid))

            elif action == ActionType.DISABLE_USB:
                if self._disable_usb_fn:
                    self._disable_usb_fn()

            elif action == ActionType.TRIGGER_SANDBOX:
                file_path = alert.details.get("file_path", "")
                if file_path and self._sandbox_fn:
                    self._sandbox_fn(str(file_path))

            elif action == ActionType.CALL_LLM:
                if self._llm_analysis_fn:
                    self._llm_analysis_fn(alert)

        except Exception:
            logger.exception("Responder action %s failed", action.value)

    def _record_action(self, alert: Alert, action: ActionType) -> None:
        """Store the action taken in the alert itself (side-effect on the alert)."""
        alert.details["action_taken"] = action.value

    def _track_type(self, alert: Alert) -> None:
        key = f"{alert.alert_type.value}|{alert.severity.value}"
        if key not in self._type_frequencies:
            self._type_frequencies[key] = []
        self._type_frequencies[key].append(time.time())

    def _clean_frequencies(self) -> None:
        now = time.time()
        for key in list(self._type_frequencies):
            self._type_frequencies[key] = [
                t for t in self._type_frequencies[key] if now - t < 300.0
            ]
            if not self._type_frequencies[key]:
                del self._type_frequencies[key]

    def _exceeds_llm_threshold(self, alert: Alert) -> bool:
        key = f"{alert.alert_type.value}|{alert.severity.value}"
        freq = self._type_frequencies.get(key, [])
        threshold = self._config.responder.llm_threshold
        return len(freq) >= threshold
