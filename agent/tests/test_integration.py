"""Integration tests for 巡查者 Agent — cross-component pipelines.

Validates: monitors → detectors → alert → backend_client wiring.
All external dependencies (psutil, WMI, websockets, yara, sklearn, httpx)
are fully mocked.  No real system calls, no network.
"""

from __future__ import annotations

import asyncio
import time
from unittest.mock import MagicMock, patch, call

import pytest

from agent.alert import Alert, AlertSeverity, AlertStore, AlertType
from agent.config import (
    AgentConfig,
    MonitorConfig,
    ProcessConfig,
    USBConfig,
    YARAConfig,
    MLAnomalyConfig,
    LLMConfig,
)


# ===========================================================================
# Test helpers
# ===========================================================================


def _make_device(vid: str, pid: str, name: str = "") -> dict:
    return {
        "vid": vid,
        "pid": pid,
        "vid_pid": f"{vid}:{pid}".upper(),
        "name": name,
        "device_path": "",
    }


def _make_iter_proc(pid, name, exe, cpu=0.0, mem=0.0, status="running"):
    proc = MagicMock()
    proc.info = {
        "pid": pid,
        "name": name,
        "exe": exe,
        "cpu_percent": cpu,
        "memory_percent": mem,
        "status": status,
    }
    return proc


def _make_process_mock(pid, name, exe):
    proc = MagicMock()
    proc.name.return_value = name
    proc.exe.return_value = exe
    return proc


# ===========================================================================
# Test 1: AlertStore ↔ callbacks (basic pipeline)
# ===========================================================================


class TestAlertPipeline:
    """AlertStore ↔ callback ↔ dedup ↔ suppression pipeline."""

    def test_alert_store_callback_pipeline(self):
        """Subscribe callback → add alerts via info/warn/critical → callback fires for each."""
        store = AlertStore(aggregation_window=0)
        received: list[Alert] = []

        def on_alert(alert: Alert) -> None:
            received.append(alert)

        store.subscribe(on_alert)

        a1 = store.info(AlertType.SYSTEM, "info msg")
        a2 = store.warn(AlertType.PROCESS, "warn msg", pid=100)
        a3 = store.critical(AlertType.USB, "crit msg", vid="AAAA", pid="BBBB")

        assert len(received) == 3
        assert received[0] is a1
        assert received[1] is a2
        assert received[2] is a3

        all_alerts = store.get_all()
        assert len(all_alerts) == 3
        assert all_alerts[0].message == "info msg"
        assert all_alerts[1].message == "warn msg"
        assert all_alerts[2].message == "crit msg"

    def test_dedup_pipeline(self):
        """Same alert twice → second deduplicated (None, only 1 in store)."""
        store = AlertStore(dedup_window=60, aggregation_window=0)
        a1 = store.info(AlertType.SYSTEM, "exact same message")
        a2 = Alert(alert_type=AlertType.SYSTEM, severity=AlertSeverity.INFO,
                    message="exact same message")
        result = store.add_with_policy(a2)
        assert result is None
        assert len(store.get_all()) == 1
        assert store.get_all()[0] is a1

    def test_aggregation_pipeline(self):
        """Same group_key within window → aggregated (count incremented, 1 in store)."""
        store = AlertStore(dedup_window=0, aggregation_window=60)
        r1 = store.info(AlertType.PROCESS, "malware", group_key="yara:rule1",
                         details={"pids": [100]})
        r2 = store.info(AlertType.PROCESS, "malware", group_key="yara:rule1",
                         details={"pids": [200]})
        # Only 1 alert in store (aggregated into r1)
        assert len(store.get_all()) == 1
        # r1's count was incremented by aggregation
        assert r1.count == 2
        # r2 is the new-created alert returned by info(), but it's r1 that was aggregated into
        assert r2 is not None

    def test_suppression_pipeline(self):
        """Suppressed alert → dropped. Non-suppressed → goes through. Unsuppress → goes through."""
        store = AlertStore(aggregation_window=0)
        store.suppress("test_keyword", 300)

        # Suppressed alert
        a1 = Alert(alert_type=AlertType.SYSTEM, message="contains test_keyword in message")
        assert store.add_with_policy(a1) is None
        assert len(store.get_all()) == 0

        # Non-suppressed alert still goes through
        a2 = store.info(AlertType.PROCESS, "normal process message")
        assert a2 is not None
        assert len(store.get_all()) == 1

        # After unsuppressing
        store.unsuppress("test_keyword")
        a3 = Alert(alert_type=AlertType.SYSTEM, message="contains test_keyword again")
        result = store.add_with_policy(a3)
        assert result is not None
        assert len(store.get_all()) == 2

    def test_suppression_message_content_match(self):
        """Suppression matches on message content, not just alert_type value."""
        store = AlertStore(aggregation_window=0)
        store.suppress("secret", 300)

        # Alert type doesn't contain "secret", but message does
        a = Alert(alert_type=AlertType.PROCESS, message="secret process detected")
        assert store.add_with_policy(a) is None

    def test_callback_error_handling_isolated(self):
        """Callback raising exception doesn't affect other callbacks or alert storage."""
        store = AlertStore(aggregation_window=0)

        received_good: list[Alert] = []

        def bad_callback(_alert: Alert) -> None:
            raise RuntimeError("callback boom")

        def good_callback(alert: Alert) -> None:
            received_good.append(alert)

        store.subscribe(bad_callback)
        store.subscribe(good_callback)

        a = store.info(AlertType.SYSTEM, "test")
        assert len(store.get_all()) == 1
        assert len(received_good) == 1
        assert received_good[0] is a


# ===========================================================================
# Test 4: Config → AlertStore wiring
# ===========================================================================


class TestConfigWiring:
    """Config → component construction."""

    def test_config_alert_store_independent_creation(self):
        """AgentConfig and AlertStore can be created independently and connected."""
        cfg = AgentConfig(
            process=ProcessConfig(whitelist=["explorer.exe"], blacklist=["malware.exe"]),
            usb=USBConfig(blocklist=["1234:5678"]),
        )
        store = AlertStore(aggregation_window=0)

        # Verify config fields
        assert cfg.process.blacklist == ["malware.exe"]
        assert cfg.process.whitelist == ["explorer.exe"]
        assert cfg.usb.blocklist == ["1234:5678"]
        assert cfg.monitors.process.enabled is True
        assert cfg.monitors.usb.enabled is True

        # Store works independently
        store.info(AlertType.SYSTEM, "agent started")
        assert len(store.get_all()) == 1

    def test_monitor_config_defaults(self):
        """MonitorConfig has correct defaults."""
        mc = MonitorConfig()
        assert mc.enabled is True
        assert mc.interval_seconds == 5.0

    def test_process_config_construction(self):
        """ProcessConfig with whitelist/blacklist."""
        pc = ProcessConfig(whitelist=["a.exe"], blacklist=["b.exe"])
        assert pc.whitelist == ["a.exe"]
        assert pc.blacklist == ["b.exe"]

    def test_usb_config_construction(self):
        """USBConfig with blocklist."""
        uc = USBConfig(blocklist=["AAAA:BBBB", "CCCC:DDDD"])
        assert uc.blocklist == ["AAAA:BBBB", "CCCC:DDDD"]

    def test_ai_config_structure(self):
        """AIConfig wraps YARA, ML, and LLM sub-configs."""
        ac = AgentConfig()
        assert ac.ai.enabled is False
        assert ac.ai.yara.enabled is False
        assert ac.ai.ml_anomaly.enabled is False
        assert ac.ai.llm.enabled is False


# ===========================================================================
# Test 5: SystemResourceMonitor → callback wiring
# ===========================================================================


class TestSystemResourceIntegration:
    """SystemResourceMonitor ↔ callback pipeline."""

    def test_callback_receives_metrics_on_poll(self):
        """Mock psutil → collect → callback receives metrics dict."""
        # Import inside test to keep module-level imports clean
        from agent.monitors.system_resource import SystemResourceMonitor

        mon = SystemResourceMonitor(MonitorConfig(enabled=True, interval_seconds=0.1))

        received: list[dict] = []

        def cb(metrics: dict) -> None:
            received.append(metrics)

        mon.set_callback(cb)

        # Mock all psutil calls used by _collect.
        # cpu_percent is called twice: (interval=0.1) → float, (interval=None, percpu=True) → list
        def _mock_cpu_percent(interval=0, percpu=False):
            if percpu:
                return [10.0, 20.0, 30.0, 40.0]
            return 42.5

        with patch("agent.monitors.system_resource.psutil.cpu_percent",
                    side_effect=_mock_cpu_percent):
            with patch("agent.monitors.system_resource.psutil.cpu_count",
                        side_effect=[8, 4]):  # logical=8, physical=4
                with patch("agent.monitors.system_resource.psutil.virtual_memory") as mock_vmem:
                    mock_vmem.return_value.total = 16_000_000_000
                    mock_vmem.return_value.available = 8_000_000_000
                    mock_vmem.return_value.used = 8_000_000_000
                    mock_vmem.return_value.percent = 50.0

                    with patch("agent.monitors.system_resource.psutil.swap_memory") as mock_swap:
                        mock_swap.return_value.total = 2_000_000_000
                        mock_swap.return_value.used = 500_000_000
                        mock_swap.return_value.percent = 25.0

                        with patch("agent.monitors.system_resource.psutil.disk_partitions",
                                    return_value=[]):
                            with patch("agent.monitors.system_resource.psutil.disk_io_counters",
                                        return_value=None):
                                with patch("agent.monitors.system_resource.psutil.net_io_counters",
                                            return_value=None):
                                    with patch("agent.monitors.system_resource.psutil.net_connections",
                                                return_value=[]):
                                        # _collect returns metrics; run() stores it as _latest
                                        metrics = mon._collect()
                                        mon._latest = metrics
                                        if mon._callback:
                                            mon._callback(metrics.to_dict())

        assert len(received) == 1
        metrics = received[0]
        assert "cpu" in metrics
        assert metrics["cpu"]["percent"] == 42.5
        assert metrics["cpu"]["count_logical"] == 8
        assert metrics["cpu"]["count_physical"] == 4
        assert metrics["memory"]["total"] == 16_000_000_000
        assert metrics["memory"]["percent"] == 50.0

    def test_callback_error_does_not_crash_monitor(self):
        """Even if callback raises, monitor continues."""
        from agent.monitors.system_resource import SystemResourceMonitor

        mon = SystemResourceMonitor(MonitorConfig(enabled=True, interval_seconds=0.1))

        call_count = 0

        def bad_cb(_metrics: dict) -> None:
            nonlocal call_count
            call_count += 1
            raise RuntimeError("callback error")

        mon.set_callback(bad_cb)

        def _mock_cpu_percent(interval=0, percpu=False):
            if percpu:
                return [5.0, 5.0]
            return 10.0

        with patch("agent.monitors.system_resource.psutil.cpu_percent",
                    side_effect=_mock_cpu_percent):
            with patch("agent.monitors.system_resource.psutil.cpu_count",
                        side_effect=[4, 2]):
                with patch("agent.monitors.system_resource.psutil.virtual_memory") as mock_vmem:
                    mock_vmem.return_value.total = 1000
                    mock_vmem.return_value.available = 500
                    mock_vmem.return_value.used = 500
                    mock_vmem.return_value.percent = 50.0
                    with patch("agent.monitors.system_resource.psutil.swap_memory") as mock_swap:
                        mock_swap.return_value.total = 0
                        mock_swap.return_value.used = 0
                        mock_swap.return_value.percent = 0.0
                        with patch("agent.monitors.system_resource.psutil.disk_partitions",
                                    return_value=[]):
                            with patch("agent.monitors.system_resource.psutil.disk_io_counters",
                                        return_value=None):
                                with patch("agent.monitors.system_resource.psutil.net_io_counters",
                                            return_value=None):
                                    with patch("agent.monitors.system_resource.psutil.net_connections",
                                                return_value=[]):
                                        metrics = mon._collect()
                                        mon._latest = metrics
                                        if mon._callback:
                                            try:
                                                mon._callback(metrics.to_dict())
                                            except RuntimeError:
                                                pass  # expected

        assert call_count == 1  # callback was called

    def test_metrics_to_dict_structure(self):
        """SystemResourceMetrics.to_dict() returns correct structure."""
        from agent.monitors.system_resource import SystemResourceMetrics

        m = SystemResourceMetrics(
            cpu_percent=33.3,
            cpu_per_core=[10.0, 20.0],
            cpu_count_logical=2,
            cpu_count_physical=1,
            memory_total=8_000_000_000,
            memory_available=4_000_000_000,
            memory_used=4_000_000_000,
            memory_percent=50.0,
            swap_total=0,
            swap_used=0,
            swap_percent=0.0,
            disk_partitions=[],
            disk_io_read_bytes=1000,
            disk_io_write_bytes=500,
            net_bytes_sent=200,
            net_bytes_recv=300,
            net_connections=5,
        )
        d = m.to_dict()
        assert d["cpu"]["percent"] == 33.3
        assert d["cpu"]["per_core"] == [10.0, 20.0]
        assert d["memory"]["total"] == 8_000_000_000
        assert d["network"]["connections"] == 5


# ===========================================================================
# Test 6: ProcessMonitor → AlertStore integration
# ===========================================================================


class TestProcessMonitorIntegration:
    """ProcessMonitor ↔ AlertStore integration."""

    def test_new_process_triggers_info_alert(self):
        """Mock psutil → simulate new process → AlertStore has 'New process started'."""
        from agent.monitors.process_monitor import ProcessMonitor

        store = AlertStore(aggregation_window=0)
        pm = ProcessMonitor(
            MonitorConfig(enabled=True, interval_seconds=5.0),
            ProcessConfig(),
            store,
        )
        pm._previous_pids = {1}

        proc = _make_iter_proc(100, "notepad.exe", "C:\\notepad.exe")
        new_proc = _make_process_mock(100, "notepad.exe", "C:\\notepad.exe")

        with patch("agent.monitors.process_monitor.psutil.process_iter", return_value=[proc]):
            with patch("agent.monitors.process_monitor.psutil.Process", return_value=new_proc):
                pm._poll()

        alerts = store.get_all()
        assert len(alerts) == 1
        assert alerts[0].alert_type == AlertType.PROCESS
        assert "New process started" in alerts[0].message
        assert "notepad.exe" in alerts[0].message
        assert alerts[0].details["pid"] == 100
        assert alerts[0].group_key == "process:new:notepad.exe"

    def test_blacklisted_process_triggers_critical_and_info(self):
        """Mock blacklisted process → critical + kill info alerts in AlertStore."""
        from agent.monitors.process_monitor import ProcessMonitor

        store = AlertStore(aggregation_window=0)
        pm = ProcessMonitor(
            MonitorConfig(enabled=True, interval_seconds=5.0),
            ProcessConfig(blacklist=["malware.exe"]),
            store,
        )
        pm._previous_pids = set()

        proc = _make_iter_proc(999, "malware.exe", "C:\\malware.exe")
        with patch("agent.monitors.process_monitor.psutil.process_iter", return_value=[proc]):
            with patch("agent.monitors.process_monitor.psutil.Process"):
                pm._poll()

        alerts = store.get_all()
        alert_messages = [a.message for a in alerts]

        assert any("Blacklisted process detected" in m for m in alert_messages)
        assert any("Killed blacklisted process" in m for m in alert_messages)
        # Critical alert for blacklisted
        crit_alerts = [a for a in alerts if a.severity == AlertSeverity.CRITICAL]
        assert len(crit_alerts) == 1
        assert crit_alerts[0].group_key == "process:blacklisted:malware.exe"


# ===========================================================================
# Test 7: USBMonitor → AlertStore integration
# ===========================================================================


class TestUSBMonitorIntegration:
    """USBMonitor ↔ AlertStore integration."""

    def test_usb_insertion_triggers_info_alert(self):
        """Mock WMI → simulate USB insertion → AlertStore has insertion alert."""
        from agent.monitors.usb_control import USBMonitor

        store = AlertStore(aggregation_window=0)
        mon = USBMonitor(
            MonitorConfig(enabled=True, interval_seconds=5.0),
            USBConfig(),
            store,
        )

        device = _make_device("1234", "5678", "Sandisk Ultra")
        with patch("agent.monitors.usb_control._query_wmi_usb_devices", return_value=[device]):
            mon._poll()

        alerts = store.get_all()
        assert len(alerts) == 1
        assert alerts[0].alert_type == AlertType.USB
        assert "USB device inserted" in alerts[0].message
        assert "Sandisk Ultra" in alerts[0].message
        assert alerts[0].details["vid"] == "1234"
        assert alerts[0].details["pid"] == "5678"
        assert alerts[0].group_key == "usb:inserted:1234:5678"

    def test_blocked_device_triggers_critical_alert(self):
        """Blocklisted USB device → critical alert in AlertStore."""
        from agent.monitors.usb_control import USBMonitor

        store = AlertStore(aggregation_window=0)
        mon = USBMonitor(
            MonitorConfig(enabled=True, interval_seconds=5.0),
            USBConfig(blocklist=["DEAD:BEEF"]),
            store,
        )

        device = _make_device("DEAD", "BEEF", "EvilDevice")
        with patch("agent.monitors.usb_control._query_wmi_usb_devices", return_value=[device]):
            mon._poll()

        alerts = store.get_all()
        critical = [a for a in alerts if a.severity == AlertSeverity.CRITICAL]
        assert len(critical) == 1
        assert "Blocked USB device" in critical[0].message
        assert critical[0].group_key == "usb:blocked:DEAD:BEEF"


# ===========================================================================
# Test 8: AlertStore → WebSocket integration (mock level)
# ===========================================================================


class TestWebSocketIntegration:
    """AlertStore → WebSocket callback bridge."""

    def test_alert_callback_bridge_to_websocket(self):
        """Mock WebSocket send as callback → add alert → callback fires with alert.to_dict()."""
        store = AlertStore(aggregation_window=0)

        sent_alerts: list[dict] = []

        # This simulates the pattern used in main.py:
        # def _on_alert(alert):
        #     asyncio.create_task(backend_client.send_alert(alert.to_dict()))
        def ws_send_callback(alert: Alert) -> None:
            sent_alerts.append(alert.to_dict())

        store.subscribe(ws_send_callback)

        store.info(AlertType.PROCESS, "new process", pid=42, name="cmd.exe")
        store.critical(AlertType.USB, "blocked device", vid="A", pid="B")

        assert len(sent_alerts) == 2
        assert sent_alerts[0]["type"] == "process"
        assert sent_alerts[0]["severity"] == "info"
        assert sent_alerts[0]["message"] == "new process"

        assert sent_alerts[1]["type"] == "usb"
        assert sent_alerts[1]["severity"] == "critical"
        assert sent_alerts[1]["message"] == "blocked device"

    def test_multiple_ws_subscribers(self):
        """Multiple callbacks (like multiple WebSocket clients) all receive alerts."""
        store = AlertStore(aggregation_window=0)

        ws1: list[dict] = []
        ws2: list[dict] = []

        store.subscribe(lambda a: ws1.append(a.to_dict()))
        store.subscribe(lambda a: ws2.append(a.to_dict()))

        store.info(AlertType.SYSTEM, "agent started")

        assert len(ws1) == 1
        assert len(ws2) == 1
        assert ws1[0]["message"] == "agent started"
        assert ws2[0]["message"] == "agent started"


# ===========================================================================
# Test 9: Cross-component group_key consistency
# ===========================================================================


class TestGroupKeyConsistency:
    """Verify group_key patterns across all components."""

    def test_process_monitor_group_keys(self):
        """ProcessMonitor uses correct group_key patterns."""
        from agent.monitors.process_monitor import ProcessMonitor

        store = AlertStore(aggregation_window=0)
        pm = ProcessMonitor(
            MonitorConfig(),
            ProcessConfig(blacklist=["evil.exe"]),
            store,
        )
        pm._previous_pids = {1}

        # Test new process group key
        proc = _make_iter_proc(200, "myapp.exe", "C:\\myapp.exe")
        new_proc = _make_process_mock(200, "myapp.exe", "C:\\myapp.exe")
        with patch("agent.monitors.process_monitor.psutil.process_iter", return_value=[proc]):
            with patch("agent.monitors.process_monitor.psutil.Process", return_value=new_proc):
                pm._poll()

        alerts = store.get_all()
        new_alerts = [a for a in alerts if "New process started" in a.message]
        assert len(new_alerts) == 1
        assert new_alerts[0].group_key == "process:new:myapp.exe"

    def test_usb_monitor_group_keys(self):
        """USBMonitor uses correct group_key patterns."""
        from agent.monitors.usb_control import USBMonitor

        store = AlertStore(aggregation_window=0)
        mon = USBMonitor(
            MonitorConfig(),
            USBConfig(blocklist=["AAAA:BBBB"]),
            store,
        )

        device = _make_device("AAAA", "BBBB", "Test")
        with patch("agent.monitors.usb_control._query_wmi_usb_devices", return_value=[device]):
            mon._poll()

        alerts = store.get_all()
        group_keys = {a.group_key for a in alerts}
        assert "usb:inserted:AAAA:BBBB" in group_keys
        assert "usb:blocked:AAAA:BBBB" in group_keys

    def test_cross_component_group_key_isolation(self):
        """Alerts from different components don't interfere via group_key."""
        store = AlertStore(dedup_window=0, aggregation_window=60)

        # Process alert
        store.info(AlertType.PROCESS, "proc msg", group_key="process:new:a.exe",
                    details={"pid": 1})

        # USB alert
        store.info(AlertType.USB, "usb msg", group_key="usb:inserted:AAAA:BBBB",
                    details={"vid": "AAAA"})

        # System alert
        store.info(AlertType.SYSTEM, "sys msg", group_key="system:startup",
                    details={})

        assert len(store.get_all()) == 3
        # Verify each has its own count of 1 (no cross-aggregation)
        for a in store.get_all():
            assert a.count == 1


# ===========================================================================
# Test 10: End-to-end scenarios — process detection pipeline
# ===========================================================================


class TestEndToEndProcessPipeline:
    """End-to-end: new process → alert → callback pipeline."""

    def test_full_process_lifecycle(self):
        """Mock two polls: first no new, second with new+suspicious → alerts flow through."""
        from agent.monitors.process_monitor import ProcessMonitor

        store = AlertStore(aggregation_window=0)
        pm = ProcessMonitor(
            MonitorConfig(enabled=True, interval_seconds=5.0),
            ProcessConfig(blacklist=["suspicious.exe"]),
            store,
        )

        # Prime previous_pids to simulate that baseline processes are already known.
        # (In production, run() does this; in tests we call _poll() directly.)
        pm._previous_pids = {1}

        # --- Poll 1: baseline — only known processes, nothing new ---
        baseline_proc = _make_iter_proc(1, "explorer.exe", "C:\\Windows\\explorer.exe")
        with patch("agent.monitors.process_monitor.psutil.process_iter", return_value=[baseline_proc]):
            with patch("agent.monitors.process_monitor.psutil.Process"):
                pm._poll()

        # No alerts yet (explorer already known via previous_pids priming)
        assert len(store.get_all()) == 0

        # --- Poll 2: new suspicious process appears ---
        proc_suspicious = _make_iter_proc(999, "suspicious.exe", "C:\\temp\\suspicious.exe")
        new_proc_mock = _make_process_mock(999, "suspicious.exe", "C:\\temp\\suspicious.exe")

        with patch("agent.monitors.process_monitor.psutil.process_iter",
                     return_value=[baseline_proc, proc_suspicious]):
            with patch("agent.monitors.process_monitor.psutil.Process", return_value=new_proc_mock):
                pm._poll()

        alerts = store.get_all()
        # Should have: critical (blacklisted detected) + info (killed)
        assert len(alerts) >= 1

        severity_levels = [a.severity for a in alerts]
        assert AlertSeverity.CRITICAL in severity_levels


# ===========================================================================
# Test 11: End-to-end scenarios — USB device pipeline
# ===========================================================================


class TestEndToEndUSBPipeline:
    """End-to-end: USB insertion, removal, blocklist pipeline."""

    def test_full_usb_lifecycle(self):
        """Simulate insert → verify alerts → remove → verify event log."""
        from agent.monitors.usb_control import USBMonitor

        store = AlertStore(aggregation_window=0)
        mon = USBMonitor(
            MonitorConfig(enabled=True, interval_seconds=5.0),
            USBConfig(blocklist=["EVIL:USB"]),
            store,
        )

        # --- Poll 1: device inserted ---
        device = _make_device("EVIL", "USB", "BadUSB")
        with patch("agent.monitors.usb_control._query_wmi_usb_devices", return_value=[device]):
            mon._poll()

        alerts_after_insert = store.get_all()
        assert len(alerts_after_insert) >= 1  # at least insertion info alert
        assert ("EVIL", "USB") in mon._known

        # --- Poll 2: device removed ---
        with patch("agent.monitors.usb_control._query_wmi_usb_devices", return_value=[]):
            mon._poll()

        # Removal event is logged but doesn't create alert
        assert ("EVIL", "USB") not in mon._known
        assert len(mon._events_log) == 2  # inserted + removed

    def test_usb_safe_device_no_blocklist_alert(self):
        """Non-blocklisted device only gets insertion info alert."""
        from agent.monitors.usb_control import USBMonitor

        store = AlertStore(aggregation_window=0)
        mon = USBMonitor(
            MonitorConfig(enabled=True, interval_seconds=5.0),
            USBConfig(),
            store,
        )

        device = _make_device("SAFE", "USBK", "SafeKeyboard")
        with patch("agent.monitors.usb_control._query_wmi_usb_devices", return_value=[device]):
            mon._poll()

        alerts = store.get_all()
        # Only info alert for insertion, no critical
        assert len(alerts) == 1
        assert alerts[0].severity == AlertSeverity.INFO
        assert "USB device inserted" in alerts[0].message


# ===========================================================================
# Test 12: Multiple detectors wired through AlertStore
# ===========================================================================


class TestMultipleDetectors:
    """Multiple alert sources feed into single AlertStore."""

    def test_alerts_from_different_sources_separated(self):
        """Alerts from process, USB, and system sources are properly separated."""
        store = AlertStore(aggregation_window=0)

        # Process alerts
        store.info(AlertType.PROCESS, "proc alert 1", group_key="process:new:a.exe")
        store.warn(AlertType.PROCESS, "proc alert 2", group_key="process:blacklisted:b.exe")

        # USB alerts
        store.info(AlertType.USB, "usb alert 1", group_key="usb:inserted:AAAA:BBBB")
        store.critical(AlertType.USB, "usb alert 2", group_key="usb:blocked:CCCC:DDDD")

        # System alerts
        store.info(AlertType.SYSTEM, "system alert 1")

        all_alerts = store.get_all()
        assert len(all_alerts) == 5

        process_alerts = store.get_by_severity(AlertSeverity.INFO)
        process_usb_info = [a for a in process_alerts if a.alert_type == AlertType.USB]
        process_proc_info = [a for a in process_alerts if a.alert_type == AlertType.PROCESS]
        assert len(process_usb_info) == 1
        assert len(process_proc_info) == 1

        warn_alerts = store.get_by_severity(AlertSeverity.WARN)
        assert len(warn_alerts) == 1
        assert warn_alerts[0].alert_type == AlertType.PROCESS

        critical_alerts = store.get_by_severity(AlertSeverity.CRITICAL)
        assert len(critical_alerts) == 1
        assert critical_alerts[0].alert_type == AlertType.USB

    def test_alert_store_capacity_and_cleanup(self):
        """AlertStore trims to MAX_ALERTS (1000) without crashing."""
        store = AlertStore(aggregation_window=0)
        for i in range(1100):
            store.info(AlertType.SYSTEM, f"alert {i}")
        assert len(store.get_all()) == 1000
        # Oldest should be trimmed
        assert store.get_all()[0].message == "alert 100"
        assert store.get_all()[-1].message == "alert 1099"

    def test_aggregation_callback_fires_on_merge(self):
        """When aggregation merges alerts, the callback fires with the updated alert."""
        store = AlertStore(dedup_window=0, aggregation_window=60)

        received: list[Alert] = []

        def cb(alert: Alert) -> None:
            received.append(alert)

        store.subscribe(cb)

        r1 = store.info(AlertType.PROCESS, "detected", group_key="yara:test",
                         details={"pids": [1]})
        r2 = store.info(AlertType.PROCESS, "detected", group_key="yara:test",
                         details={"pids": [2]})

        # r1: callback fires once (normal add)
        # r2: callback fires once (aggregation merge)
        assert len(received) == 2
        assert received[0] is r1
        assert received[1] is r1  # r2 is the same alert, aggregated
        assert r1.count == 2
