"""Tests for AI Smart Control Engine — controllers module.

Covers: StateEvaluator, AdaptiveTuner, AlertResponder, BaselineLearner,
SmartControlEngine lifecycle and evaluation loop.
"""

from __future__ import annotations

import asyncio
import json
import sys
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Ensure project root is on path
sys.path.insert(0, str(Path(__file__).parent.parent / "agent"))

from agent.alert import Alert, AlertSeverity, AlertStore, AlertType
from agent.config import (
    BaselineConfig,
    ResponderConfig,
    SmartControlConfig,
    TunerConfig,
)
from agent.controllers.baseline import BaselineLearner
from agent.controllers.responder import ActionType, AlertResponder
from agent.controllers.smart_control import SmartControlEngine
from agent.controllers.state import StateEvaluator, SystemState
from agent.controllers.tuner import AdaptiveTuner


# ===========================================================================
# Helpers
# ===========================================================================


def _make_alert(
    severity: AlertSeverity = AlertSeverity.INFO,
    alert_type: AlertType = AlertType.SYSTEM,
    message: str = "",
    pid: int = 0,
    file_path: str = "",
) -> Alert:
    return Alert(
        alert_id=f"test-{time.time_ns()}",
        timestamp=time.time(),
        severity=severity,
        alert_type=alert_type,
        message=message or f"test-{severity.value}",
        details={"pid": pid, "file_path": file_path} if pid or file_path else {},
    )


def _default_config() -> SmartControlConfig:
    return SmartControlConfig(
        enabled=True,
        evaluation_interval=60,
        tuner=TunerConfig(enabled=True, idle_multiplier=2.0, stress_multiplier=0.25),
        responder=ResponderConfig(
            enabled=True,
            auto_respond_critical=True,
            auto_respond_warning=True,
            llm_threshold=3,
        ),
        baseline=BaselineConfig(enabled=True, learning_period=7200, storage_path=""),
    )


# ===========================================================================
# StateEvaluator tests
# ===========================================================================


class TestStateEvaluator:
    def test_evaluate_no_alerts(self):
        """Health is 100 with no recent alerts."""
        store = AlertStore()
        evaluator = StateEvaluator(store)

        state = evaluator.evaluate()
        assert isinstance(state, SystemState)
        assert state.health_score == 100.0
        assert state.recent_alerts == []
        assert "healthy" in state.summary

    def test_evaluate_critical_penalty(self):
        """Each critical alert deducts 30 from health score."""
        store = AlertStore()
        store.add(_make_alert(AlertSeverity.CRITICAL, AlertType.PROCESS, "crit-1"))
        store.add(_make_alert(AlertSeverity.CRITICAL, AlertType.PROCESS, "crit-2"))
        evaluator = StateEvaluator(store)

        state = evaluator.evaluate()
        assert state.health_score == pytest.approx(100.0 - 2 * 30.0)
        assert state.alert_count_critical == 2

    def test_evaluate_mixed_penalties(self):
        """Crit=30, warn=15, info=5 per alert."""
        store = AlertStore()
        store.critical(AlertType.PROCESS, "c1")
        store.warn(AlertType.USB, "w1")
        store.info(AlertType.SYSTEM, "i1")
        store.info(AlertType.SYSTEM, "i2")
        evaluator = StateEvaluator(store)

        state = evaluator.evaluate()
        assert state.health_score == pytest.approx(100.0 - 30 - 15 - 5 - 5)
        assert state.alert_count_critical == 1
        assert state.alert_count_warning == 1
        assert state.alert_count_info == 2

    def test_health_score_clamped(self):
        """Health score is clamped to [0, 100]."""
        store = AlertStore()
        for i in range(5):
            store.add(_make_alert(AlertSeverity.CRITICAL, AlertType.PROCESS, f"c-{i}"))
        evaluator = StateEvaluator(store)

        state = evaluator.evaluate()
        assert state.health_score == 0.0  # 100 - 5*30 = -50 → clamped to 0

    def test_summary_labels(self):
        """Summary string uses the correct label for each health band."""
        store = AlertStore()
        evaluator = StateEvaluator(store)

        # healthy (>=80)
        s1 = evaluator.evaluate()
        assert "healthy" in s1.summary

        # stressed (>=20) — 2 criticals = health=40 → "stressed" band
        store.add(_make_alert(AlertSeverity.CRITICAL, AlertType.PROCESS, "s-c1"))
        store.add(_make_alert(AlertSeverity.CRITICAL, AlertType.PROCESS, "s-c2"))
        s3 = evaluator.evaluate()
        assert "stressed" in s3.summary

        # critical (<20) — add more criticals to push below 20
        store.add(_make_alert(AlertSeverity.CRITICAL, AlertType.PROCESS, "s-c4"))
        s4 = evaluator.evaluate()
        assert "critical" in s4.summary

    def test_only_recent_alerts_considered(self):
        """Alerts older than 60 seconds are excluded."""
        store = AlertStore()
        old = Alert(
            severity=AlertSeverity.CRITICAL,
            alert_type=AlertType.PROCESS,
            message="old",
            timestamp=time.time() - 120.0,
        )
        store.add(old)
        evaluator = StateEvaluator(store)

        state = evaluator.evaluate()
        assert state.health_score == 100.0


# ===========================================================================
# AdaptiveTuner tests
# ===========================================================================


class TestAdaptiveTuner:
    def test_default_multiplier(self):
        tuner = AdaptiveTuner(_default_config())
        assert tuner.multiplier == 1.0

    def test_idle_multiplier(self):
        """Health >= 80 uses idle_multiplier."""
        tuner = AdaptiveTuner(_default_config())
        m = tuner.adjust(90.0)
        assert m == 2.0
        assert tuner.multiplier == 2.0

    def test_normal_multiplier(self):
        """Health [50, 80) uses 1.0."""
        tuner = AdaptiveTuner(_default_config())
        m = tuner.adjust(65.0)
        assert m == 1.0

    def test_stress_multiplier(self):
        """Health [20, 50) uses 0.5."""
        tuner = AdaptiveTuner(_default_config())
        m = tuner.adjust(30.0)
        assert m == 0.5

    def test_critical_multiplier(self):
        """Health < 20 uses stress_multiplier."""
        tuner = AdaptiveTuner(_default_config())
        m = tuner.adjust(10.0)
        assert m == 0.25

    def test_adjusted_interval_scales(self):
        """adjusted_interval applies multiplier to base interval."""
        tuner = AdaptiveTuner(_default_config())
        tuner.adjust(90.0)  # idle → 2.0
        assert tuner.adjusted_interval(10.0) == 20.0

    def test_adjusted_interval_minimum(self):
        """adjusted_interval floor is 1.0."""
        tuner = AdaptiveTuner(_default_config())
        tuner.adjust(10.0)  # critical → 0.25
        assert tuner.adjusted_interval(1.0) == 1.0  # 1.0 * 0.25 = 0.25 → 1.0

    def test_custom_config_multipliers(self):
        config = _default_config()
        config.tuner.idle_multiplier = 3.0
        config.tuner.stress_multiplier = 0.1
        tuner = AdaptiveTuner(config)
        assert tuner.adjust(95.0) == 3.0
        assert tuner.adjust(5.0) == 0.1


# ===========================================================================
# AlertResponder tests
# ===========================================================================


class TestAlertResponder:
    def test_disabled_responder_logs_only(self):
        config = _default_config()
        config.responder.enabled = False
        store = AlertStore()
        responder = AlertResponder(config, store)

        alerts = [_make_alert(AlertSeverity.CRITICAL, AlertType.PROCESS)]
        responder.process(alerts)

        # No action callback was called — simply no crash
        assert len(alerts) == 1
        assert alerts[0].details.get("action_taken") is None

    def test_critical_process_kills(self):
        kill_fn = MagicMock()
        responder = AlertResponder(
            _default_config(), AlertStore(), kill_process_fn=kill_fn,
        )
        alert = _make_alert(AlertSeverity.CRITICAL, AlertType.PROCESS, pid=1337)
        responder.process([alert])

        kill_fn.assert_called_once_with(1337)
        assert alert.details.get("action_taken") == "kill_process"

    def test_critical_usb_disables(self):
        disable_fn = MagicMock()
        responder = AlertResponder(
            _default_config(), AlertStore(), disable_usb_fn=disable_fn,
        )
        alert = _make_alert(AlertSeverity.CRITICAL, AlertType.USB)
        responder.process([alert])

        disable_fn.assert_called_once()
        assert alert.details.get("action_taken") == "disable_usb"

    def test_critical_usb_auto_disabled_off(self):
        config = _default_config()
        config.responder.auto_respond_critical = False
        disable_fn = MagicMock()
        responder = AlertResponder(
            config, AlertStore(), disable_usb_fn=disable_fn,
        )
        alert = _make_alert(AlertSeverity.CRITICAL, AlertType.USB)
        responder.process([alert])

        disable_fn.assert_not_called()
        assert alert.details.get("action_taken") is None

    def test_critical_system_triggers_sandbox(self):
        sandbox_fn = MagicMock()
        responder = AlertResponder(
            _default_config(), AlertStore(), sandbox_fn=sandbox_fn,
        )
        alert = _make_alert(AlertSeverity.CRITICAL, AlertType.SYSTEM, file_path="C:\\malware.exe")
        responder.process([alert])

        sandbox_fn.assert_called_once_with("C:\\malware.exe")
        assert alert.details.get("action_taken") == "trigger_sandbox"

    def test_warning_increases_monitoring(self):
        config = _default_config()
        config.responder.auto_respond_warning = True
        responder = AlertResponder(config, AlertStore())
        alert = _make_alert(AlertSeverity.WARN, AlertType.PROCESS)
        responder.process([alert])

        assert alert.details.get("action_taken") == "increase_monitoring"

    def test_warning_auto_respond_off_logs(self):
        config = _default_config()
        config.responder.auto_respond_warning = False
        responder = AlertResponder(config, AlertStore())
        alert = _make_alert(AlertSeverity.WARN, AlertType.PROCESS)
        responder.process([alert])

        assert alert.details.get("action_taken") is None

    def test_llm_escalation_after_threshold(self):
        """Same-type warning alerts escalate to LLM analysis after N occurrences.

        _track_type() is called BEFORE _exceeds_llm_threshold(), so the
        current alert is already counted — threshold=N means the N-th
        occurrence triggers CALL_LLM.
        """
        llm_fn = MagicMock()
        config = _default_config()
        config.responder.llm_threshold = 2
        responder = AlertResponder(config, AlertStore(), llm_analysis_fn=llm_fn)

        # 1st warn — tracked, freq < threshold → increase_monitoring
        a1 = _make_alert(AlertSeverity.WARN, AlertType.PROCESS, message="dup")
        responder.process([a1])
        assert a1.details.get("action_taken") == "increase_monitoring"

        # 2nd warn — tracked, freq >= threshold (2) → CALL_LLM
        a2 = _make_alert(AlertSeverity.WARN, AlertType.PROCESS, message="dup")
        responder.process([a2])
        assert a2.details.get("action_taken") == "call_llm"
        llm_fn.assert_called_once()

    def test_llm_fn_exception_handled(self):
        """Exception in LLM callback is caught without crashing."""
        llm_fn = MagicMock(side_effect=ValueError("LLM failed"))
        config = _default_config()
        config.responder.llm_threshold = 1
        responder = AlertResponder(config, AlertStore(), llm_analysis_fn=llm_fn)

        # Sending 1 alert with threshold=1 → triggers CALL_LLM → exception caught
        responder.process([_make_alert(AlertSeverity.WARN, AlertType.PROCESS)])
        llm_fn.assert_called_once()  # exception caught, no crash

    def test_kill_fn_exception_handled(self):
        kill_fn = MagicMock(side_effect=RuntimeError("Access denied"))
        responder = AlertResponder(
            _default_config(), AlertStore(), kill_process_fn=kill_fn,
        )
        alert = _make_alert(AlertSeverity.CRITICAL, AlertType.PROCESS, pid=999)
        responder.process([alert])  # no crash
        kill_fn.assert_called_once_with(999)

    def test_info_alerts_logged_only(self):
        responder = AlertResponder(_default_config(), AlertStore())
        info = _make_alert(AlertSeverity.INFO, AlertType.SYSTEM)
        responder.process([info])
        assert info.details.get("action_taken") is None

    def test_frequency_cleanup(self):
        """Old entries in _type_frequencies are cleaned after 300s."""
        responder = AlertResponder(_default_config(), AlertStore())
        # Simulate a frequency entry with a very old timestamp
        responder._type_frequencies["process|warn"] = [time.time() - 600.0]

        alert = _make_alert(AlertSeverity.WARN, AlertType.PROCESS)
        responder.process([alert])

        # The old entry should have been cleaned
        assert "process|warn" in responder._type_frequencies
        assert len(responder._type_frequencies["process|warn"]) == 1  # only the new one


# ===========================================================================
# BaselineLearner tests
# ===========================================================================


class TestBaselineLearner:
    def test_no_baseline_initially(self, tmp_path):
        learner = BaselineLearner(AlertStore(), str(tmp_path / "baseline.json"))
        assert not learner.is_baseline_ready()
        assert learner.baseline == {}

    def test_records_during_quiet_period(self, tmp_path):
        store = AlertStore()
        learner = BaselineLearner(
            store, str(tmp_path / "baseline.json"), learning_period=0,  # immediate collect
        )
        assert not learner.is_baseline_ready()

        # Feed enough samples to trigger baseline computation
        for i in range(30):
            learner.record_sample({
                "cpu_percent": 30.0 + i,
                "memory_percent": 60.0,
                "disk_io_read_bytes": 1000.0,
                "disk_io_write_bytes": 500.0,
            })

        assert learner.is_baseline_ready()
        bl = learner.baseline
        assert "cpu_percent" in bl
        assert "memory_percent" in bl
        assert "disk_io_read_bytes" in bl
        assert "disk_io_write_bytes" in bl
        assert isinstance(bl["cpu_percent"]["mean"], float)
        assert isinstance(bl["cpu_percent"]["std"], float)
        assert bl["cpu_percent"]["std"] >= 0

    def test_alert_resets_quiet_timer(self, tmp_path):
        store = AlertStore()
        learner = BaselineLearner(
            store, str(tmp_path / "baseline.json"), learning_period=0,
        )
        # Start quiet
        learner.record_sample({"cpu_percent": 10.0, "memory_percent": 50.0,
                               "disk_io_read_bytes": 0.0, "disk_io_write_bytes": 0.0})

        # Add an alert — should reset quiet period
        store.add(_make_alert(AlertSeverity.WARN, AlertType.SYSTEM))

        # This sample should not be collected because alert reset quiet timer
        learner.record_sample({"cpu_percent": 10.0, "memory_percent": 50.0,
                               "disk_io_read_bytes": 0.0, "disk_io_write_bytes": 0.0})

        assert not learner.is_baseline_ready()

    def test_persist_and_load(self, tmp_path):
        """Baseline saved to disk can be loaded by a new learner instance."""
        p = tmp_path / "baseline.json"
        store = AlertStore()

        # Create and compute baseline
        learner = BaselineLearner(store, str(p), learning_period=0)
        for i in range(30):
            learner.record_sample({"cpu_percent": 40.0 + i, "memory_percent": 50.0,
                                   "disk_io_read_bytes": 2000.0, "disk_io_write_bytes": 1000.0})
        assert learner.is_baseline_ready()

        # New learner loads from the same file
        learner2 = BaselineLearner(store, str(p), learning_period=0)
        assert learner2.is_baseline_ready()
        assert learner2.baseline == learner.baseline

    def test_load_corrupted_file(self, tmp_path):
        p = tmp_path / "baseline.json"
        p.write_text("{invalid json")
        store = AlertStore()
        learner = BaselineLearner(store, str(p), learning_period=0)
        assert not learner.is_baseline_ready()  # gracefully degraded

    def test_load_invalid_schema(self, tmp_path):
        p = tmp_path / "baseline.json"
        p.write_text(json.dumps({"cpu_percent": {"mean": "not-a-number", "std": 5.0}}))
        store = AlertStore()
        learner = BaselineLearner(store, str(p), learning_period=0)
        assert not learner.is_baseline_ready()

    def test_validate_rejects_negative_std(self):
        learner = BaselineLearner(AlertStore(), str(tmp_path) if False else "", learning_period=0)
        # Access _validate directly
        assert not learner._validate({"cpu": {"mean": 50.0, "std": -1.0}})
        assert not learner._validate({"cpu": {"mean": 50.0, "std": 999.0}})  # >100 std
        assert learner._validate({"cpu": {"mean": 50.0, "std": 15.0}})


# ===========================================================================
# SmartControlEngine tests
# ===========================================================================


class TestSmartControlEngine:
    def test_start_disabled_engine(self):
        """Disabled engine does not start the background task."""
        config = _default_config()
        config.enabled = False
        engine = SmartControlEngine(config, AlertStore())
        engine.start()
        assert not engine.running

    @pytest.mark.asyncio
    async def test_start_stop_lifecycle(self):
        """Start → running → double start is no-op → stop."""
        engine = SmartControlEngine(_default_config(), AlertStore())
        assert not engine.running

        engine.start()
        assert engine.running

        # Double start is a no-op
        engine.start()
        assert engine.running

        await engine.stop()
        assert not engine.running

    @pytest.mark.asyncio
    async def test_evaluation_loop_updates_tuner(self):
        """Evaluation loop computes health and updates the tuner."""
        config = _default_config()
        config.evaluation_interval = 0.1
        store = AlertStore()
        engine = SmartControlEngine(config, store)

        engine.start()
        await asyncio.sleep(0.3)
        # No alerts → health=100 → idle multiplier=2.0
        assert engine.tuner.multiplier == 2.0
        await engine.stop()

    @pytest.mark.asyncio
    async def test_evaluation_loop_alerts_affect_tuning(self):
        """Critical alerts cause lower health → stress multiplier."""
        config = _default_config()
        config.evaluation_interval = 0.1
        store = AlertStore()
        engine = SmartControlEngine(config, store)

        # Seed 3 unique critical alerts (avoid AlertStore dedup)
        store.add(_make_alert(AlertSeverity.CRITICAL, AlertType.PROCESS, "a1"))
        store.add(_make_alert(AlertSeverity.CRITICAL, AlertType.PROCESS, "a2"))
        store.add(_make_alert(AlertSeverity.CRITICAL, AlertType.PROCESS, "a3"))

        engine.start()
        await asyncio.sleep(0.3)
        # health=100-(3*30)=10 → critical → multiplier=stress(0.25)
        assert engine.tuner.multiplier == pytest.approx(0.25)
        await engine.stop()

    @pytest.mark.asyncio
    async def test_evaluation_loop_respects_tuner_disabled(self):
        """When tuner is disabled, multiplier stays at 1.0."""
        config = _default_config()
        config.tuner.enabled = False
        config.evaluation_interval = 0.1
        store = AlertStore()
        engine = SmartControlEngine(config, store)

        engine.start()
        await asyncio.sleep(0.3)
        assert engine.tuner.multiplier == 1.0
        await engine.stop()

    @pytest.mark.asyncio
    async def test_responder_integration(self):
        """Engine calls responder.process with alert info."""
        config = _default_config()
        config.responder.auto_respond_critical = True
        config.evaluation_interval = 0.1
        store = AlertStore()
        kill_fn = MagicMock()
        engine = SmartControlEngine(
            config, store, kill_process_fn=kill_fn,
        )

        # Seed a critical process alert with pid (unique msg avoids dedup)
        store.add(_make_alert(AlertSeverity.CRITICAL, AlertType.PROCESS,
                              "malware found", pid=42))

        engine.start()
        await asyncio.sleep(0.3)
        # Responder should have killed process — loop runs ~3 iterations
        kill_fn.assert_called_with(42)  # at least called with 42
        await engine.stop()

    def test_baseline_learner_exposed(self):
        """baseline_learner property returns the instance."""
        engine = SmartControlEngine(_default_config(), AlertStore())
        assert engine.baseline_learner is not None
        assert hasattr(engine.baseline_learner, "is_baseline_ready")

    @pytest.mark.asyncio
    async def test_stop_when_not_running(self):
        """Stopping an already stopped engine is a no-op."""
        engine = SmartControlEngine(_default_config(), AlertStore())
        await engine.stop()
        assert not engine.running

    @pytest.mark.asyncio
    async def test_running_property(self):
        """Running property reflects engine state correctly."""
        engine = SmartControlEngine(_default_config(), AlertStore())
        assert not engine.running
        engine.start()
        assert engine.running
        await engine.stop()
        assert not engine.running
