from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable, Dict, List, Optional

from agent.alert import Alert, AlertStore
from agent.config import SmartControlConfig
from agent.controllers.baseline import BaselineLearner
from agent.controllers.responder import AlertResponder
from agent.controllers.state import StateEvaluator, SystemState
from agent.controllers.tuner import AdaptiveTuner

logger = logging.getLogger(__name__)


class SmartControlEngine:
    """Orchestrates adaptive tuning and alert response.

    Runs a background evaluation loop that periodically:
      1. Collects system state (alerts, metrics)
      2. Computes a health score
      3. Adjusts monitor intervals via the tuner
      4. Processes alerts via the responder
    """

    def __init__(
        self,
        config: SmartControlConfig,
        alert_store: AlertStore,
        monitors: Optional[List[Any]] = None,
        kill_process_fn: Optional[Callable[[int], None]] = None,
        disable_usb_fn: Optional[Callable[[], None]] = None,
        sandbox_fn: Optional[Callable[[str], None]] = None,
        llm_analysis_fn: Optional[Callable[[Alert], None]] = None,
    ) -> None:
        self._config = config
        self._alert_store = alert_store
        self._monitors = monitors or []

        self._evaluator = StateEvaluator(alert_store)
        self._tuner = AdaptiveTuner(config)
        self._responder = AlertResponder(
            config, alert_store,
            kill_process_fn=kill_process_fn,
            disable_usb_fn=disable_usb_fn,
            sandbox_fn=sandbox_fn,
            llm_analysis_fn=llm_analysis_fn,
        )
        self._baseline = BaselineLearner(
            alert_store,
            storage_path=config.baseline.storage_path,
            learning_period=config.baseline.learning_period,
        )

        self._task: Optional[asyncio.Task[None]] = None
        self._stop_event = asyncio.Event()

    # -- Lifecycle --

    def start(self) -> None:
        if not self._config.enabled:
            logger.info("SmartControlEngine disabled in config")
            return
        if self._task is not None and not self._task.done():
            logger.warning("SmartControlEngine already running")
            return

        self._stop_event.clear()
        self._task = asyncio.create_task(self._run_loop())
        logger.info(
            "SmartControlEngine started (interval=%ds)",
            self._config.evaluation_interval,
        )

    async def stop(self) -> None:
        if self._task is None or self._task.done():
            return
        self._stop_event.set()
        try:
            await asyncio.wait_for(self._task, timeout=5.0)
        except (asyncio.TimeoutError, asyncio.CancelledError):
            self._task.cancel()
        self._task = None
        logger.info("SmartControlEngine stopped")

    # -- Evaluation loop --

    async def _run_loop(self) -> None:
        """Main loop: evaluate → tune → respond → sleep."""
        while not self._stop_event.is_set():
            try:
                state = self._evaluator.evaluate()
                self._apply_tuning(state)
                self._apply_response(state)
                logger.info("SmartControl: %s", state.summary)
            except Exception:
                logger.exception("SmartControlEngine evaluation error")

            await asyncio.sleep(self._config.evaluation_interval)

    def _apply_tuning(self, state: SystemState) -> None:
        if not self._config.tuner.enabled:
            return
        self._tuner.adjust(state.health_score)

    def _apply_response(self, state: SystemState) -> None:
        if not self._config.responder.enabled:
            return
        self._responder.process(state.recent_alerts)

    # -- Accessors for testing / API --

    @property
    def tuner(self) -> AdaptiveTuner:
        return self._tuner

    @property
    def responder(self) -> AlertResponder:
        return self._responder

    @property
    def baseline_learner(self) -> BaselineLearner:
        return self._baseline

    @property
    def running(self) -> bool:
        return self._task is not None and not self._task.done()
