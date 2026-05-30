"""Unit tests for USBMonitor.

Covers: constructor, blocklist refresh, USB insertion/removal detection,
blocked-device alerts, event logging, lifecycle (run/stop/status).
"""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch

import pytest

from agent.alert import AlertStore, AlertType
from agent.config import MonitorConfig, USBConfig
from agent.monitors.usb_control import USBMonitor


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_device(vid: str, pid: str, name: str = "") -> dict:
    """Build a minimal device dict as returned by _query_wmi_usb_devices."""
    return {
        "vid": vid,
        "pid": pid,
        "vid_pid": f"{vid}:{pid}".upper(),
        "name": name,
        "device_path": "",
    }


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mon_config() -> MonitorConfig:
    return MonitorConfig(enabled=True, interval_seconds=0.1)


@pytest.fixture
def usb_config() -> USBConfig:
    return USBConfig(blocklist=[])


@pytest.fixture
def alert_store() -> AlertStore:
    """AlertStore with aggregation disabled for predictable per-test assertions."""
    return AlertStore(aggregation_window=0)


@pytest.fixture
def mock_query():
    """Patch the module-level _query_wmi_usb_devices."""
    with patch("agent.monitors.usb_control._query_wmi_usb_devices") as m:
        m.return_value = []
        yield m


@pytest.fixture
def monitor(mon_config, usb_config, alert_store, mock_query) -> USBMonitor:
    """Fresh USBMonitor wired to mock WMI query."""
    return USBMonitor(
        mon_config=mon_config,
        usb_config=usb_config,
        alert_store=alert_store,
    )


# ---------------------------------------------------------------------------
# Constructor
# ---------------------------------------------------------------------------


class TestConstructor:
    """Verify USBMonitor initial state."""

    def test_stores_configs(self, monitor, mon_config, usb_config, alert_store):
        assert monitor._mon_config is mon_config
        assert monitor._usb_config is usb_config
        assert monitor._alert_store is alert_store

    def test_initial_running_false(self, monitor):
        assert monitor._running is False
        assert monitor._task is None

    def test_initial_known_empty(self, monitor):
        assert monitor._known == set()
        assert isinstance(monitor._known, set)

    def test_initial_latest_devices_empty(self, monitor):
        assert monitor._latest_devices == []

    def test_initial_events_empty(self, monitor):
        assert monitor._events_log == []

    def test_callback_none_by_default(self, monitor):
        assert monitor._callback is None

    def test_blocklist_refreshed_on_init(self, monitor, usb_config):
        """_refresh_blocklist is called in __init__."""
        # Empty blocklist by default → _blocklist is empty set.
        assert monitor._blocklist == set()

    def test_blocklist_refreshed_from_config(self, mon_config, alert_store, mock_query):
        usb_cfg = USBConfig(blocklist=["1234:5678", "abcd:ef01"])
        mon = USBMonitor(
            mon_config=mon_config,
            usb_config=usb_cfg,
            alert_store=alert_store,
        )
        assert mon._blocklist == {"1234:5678", "ABCD:EF01"}


# ---------------------------------------------------------------------------
# Blocklist refresh
# ---------------------------------------------------------------------------


class TestBlocklistRefresh:
    """Tests for _refresh_blocklist."""

    def test_empty_blocklist(self, monitor):
        monitor._refresh_blocklist()
        assert monitor._blocklist == set()

    def test_single_entry(self, monitor):
        monitor._usb_config = USBConfig(blocklist=["  ABC:DEF  "])
        monitor._refresh_blocklist()
        assert monitor._blocklist == {"ABC:DEF"}

    def test_uppercases_entries(self, monitor):
        monitor._usb_config = USBConfig(blocklist=["abcd:ef01", "1234:5678"])
        monitor._refresh_blocklist()
        assert monitor._blocklist == {"ABCD:EF01", "1234:5678"}

    def test_strips_whitespace(self, monitor):
        monitor._usb_config = USBConfig(blocklist=["  abcd:ef01  ", "\t1234:5678\n"])
        monitor._refresh_blocklist()
        assert monitor._blocklist == {"ABCD:EF01", "1234:5678"}

    def test_duplicates_collapsed(self, monitor):
        monitor._usb_config = USBConfig(blocklist=["abcd:ef01", "ABCD:EF01", "AbCd:Ef01"])
        monitor._refresh_blocklist()
        assert monitor._blocklist == {"ABCD:EF01"}

    def test_update_config_calls_refresh(self, monitor):
        monitor.update_config(USBConfig(blocklist=["feed:beef"]))
        assert monitor._blocklist == {"FEED:BEEF"}


# ---------------------------------------------------------------------------
# Polling — USB insertion
# ---------------------------------------------------------------------------


class TestUSBInsertion:
    """Verify that _poll detects newly inserted USB devices."""

    def test_insertion_creates_info_alert(self, monitor, alert_store, mock_query):
        mock_query.return_value = [_make_device("1234", "5678", "SanDisk USB")]

        monitor._poll()

        alerts = alert_store.get_all()
        assert len(alerts) == 1
        assert alerts[0].alert_type == AlertType.USB
        assert "USB device inserted" in alerts[0].message

    def test_insertion_alert_includes_device_name(self, monitor, alert_store, mock_query):
        mock_query.return_value = [_make_device("AAAA", "BBBB", "MyDisk")]

        monitor._poll()

        alert = alert_store.get_all()[0]
        assert "MyDisk" in alert.message

    def test_insertion_alert_fallback_to_vidpid(self, monitor, alert_store, mock_query):
        """When name is empty, the message falls back to VID:PID."""
        mock_query.return_value = [_make_device("1234", "5678", "")]

        monitor._poll()

        alert = alert_store.get_all()[0]
        assert "1234:5678" in alert.message

    def test_insertion_alert_details(self, monitor, alert_store, mock_query):
        mock_query.return_value = [_make_device("ABCD", "0001", "TestDev")]

        monitor._poll()

        alert = alert_store.get_all()[0]
        assert alert.details["vid"] == "ABCD"
        assert alert.details["pid"] == "0001"
        assert alert.details["vid_pid"] == "ABCD:0001"
        assert alert.details["name"] == "TestDev"

    def test_insertion_group_key(self, monitor, alert_store, mock_query):
        mock_query.return_value = [_make_device("AAAA", "BBBB")]

        monitor._poll()

        alert = alert_store.get_all()[0]
        assert alert.group_key == "usb:inserted:AAAA:BBBB"

    def test_multiple_new_devices(self, monitor, alert_store, mock_query):
        mock_query.return_value = [
            _make_device("1111", "2222", "Dev1"),
            _make_device("3333", "4444", "Dev2"),
        ]

        monitor._poll()

        alerts = alert_store.get_all()
        assert len(alerts) == 2

    def test_device_already_known_no_alert(self, monitor, alert_store, mock_query):
        """Second poll with same device should not create duplicate alerts."""
        device = _make_device("1234", "5678", "Known")

        # First poll primes known devices via _poll (not run).
        mock_query.return_value = [device]
        monitor._poll()
        first_alert_count = len(alert_store.get_all())

        # Second poll — same device, no new alerts.
        mock_query.return_value = [device]
        monitor._poll()

        # Should be same number of alerts (no new insertion).
        assert len(alert_store.get_all()) == first_alert_count

    def test_insertion_updates_known_set(self, monitor, mock_query):
        mock_query.return_value = [_make_device("1234", "5678")]
        monitor._poll()
        assert ("1234", "5678") in monitor._known


# ---------------------------------------------------------------------------
# Polling — USB removal
# ---------------------------------------------------------------------------


class TestUSBRemoval:
    """Verify removal detection and event logging."""

    def test_removal_logs_event_no_alert(self, monitor, alert_store, mock_query):
        device = _make_device("ABCD", "0001", "Stick")

        # First poll — device appears.
        mock_query.return_value = [device]
        monitor._poll()
        alert_count = len(alert_store.get_all())

        # Second poll — device gone.
        mock_query.return_value = []
        monitor._poll()

        # No new alert should be created for removal.
        assert len(alert_store.get_all()) == alert_count

    def test_removal_event_logged(self, monitor, mock_query):
        device = _make_device("ABCD", "0001", "Stick")

        mock_query.return_value = [device]
        monitor._poll()

        # Now remove.
        mock_query.return_value = []
        monitor._poll()

        # Check events log
        events = monitor._events_log
        assert len(events) >= 2  # inserted + removed
        removal_events = [e for e in events if e["event"] == "removed"]
        assert len(removal_events) == 1
        assert removal_events[0]["vid"] == "ABCD"
        assert removal_events[0]["pid"] == "0001"
        assert removal_events[0]["vid_pid"] == "ABCD:0001"

    def test_removal_updates_known_set(self, monitor, mock_query):
        device = _make_device("AAAA", "BBBB")

        mock_query.return_value = [device]
        monitor._poll()
        assert ("AAAA", "BBBB") in monitor._known

        mock_query.return_value = []
        monitor._poll()
        assert ("AAAA", "BBBB") not in monitor._known


# ---------------------------------------------------------------------------
# Polling — Blocked device
# ---------------------------------------------------------------------------


class TestBlockedDevice:
    """Verify that blocklisted devices trigger critical alerts."""

    def test_blocked_device_critical_alert(self, mon_config, alert_store, mock_query):
        usb_cfg = USBConfig(blocklist=["1234:5678"])
        mon = USBMonitor(
            mon_config=mon_config,
            usb_config=usb_cfg,
            alert_store=alert_store,
        )

        mock_query.return_value = [_make_device("1234", "5678", "EvilUSB")]

        mon._poll()

        alerts = alert_store.get_all()
        # Should have both an info alert (insertion) and a critical alert (blocked).
        critical_alerts = [a for a in alerts if a.severity.value == "critical"]
        assert len(critical_alerts) == 1
        assert "Blocked USB device" in critical_alerts[0].message
        assert "EvilUSB" in critical_alerts[0].message

    def test_blocked_device_group_key(self, mon_config, alert_store, mock_query):
        usb_cfg = USBConfig(blocklist=["DEAD:BEEF"])
        mon = USBMonitor(
            mon_config=mon_config,
            usb_config=usb_cfg,
            alert_store=alert_store,
        )

        mock_query.return_value = [_make_device("DEAD", "BEEF", "Bad")]

        mon._poll()

        critical = [a for a in alert_store.get_all() if a.severity.value == "critical"][0]
        assert critical.group_key == "usb:blocked:DEAD:BEEF"

    def test_blocked_device_without_name(self, mon_config, alert_store, mock_query):
        usb_cfg = USBConfig(blocklist=["AAAA:BBBB"])
        mon = USBMonitor(
            mon_config=mon_config,
            usb_config=usb_cfg,
            alert_store=alert_store,
        )

        mock_query.return_value = [_make_device("AAAA", "BBBB", "")]

        mon._poll()

        critical = [a for a in alert_store.get_all() if a.severity.value == "critical"][0]
        assert "AAAA:BBBB" in critical.message

    def test_non_blocked_device_no_critical(self, monitor, alert_store, mock_query):
        mock_query.return_value = [_make_device("9999", "8888", "SafeUSB")]

        monitor._poll()

        critical = [a for a in alert_store.get_all() if a.severity.value == "critical"]
        assert len(critical) == 0

    def test_blocklist_case_insensitive(self, mon_config, alert_store, mock_query):
        usb_cfg = USBConfig(blocklist=["abcd:ef01"])
        mon = USBMonitor(
            mon_config=mon_config,
            usb_config=usb_cfg,
            alert_store=alert_store,
        )

        mock_query.return_value = [_make_device("ABCD", "EF01", "Test")]

        mon._poll()

        critical = [a for a in alert_store.get_all() if a.severity.value == "critical"]
        assert len(critical) == 1


# ---------------------------------------------------------------------------
# Event log
# ---------------------------------------------------------------------------


class TestEventLog:
    """Tests for _log_event and the events property."""

    def test_insertion_event_logged(self, monitor, mock_query):
        mock_query.return_value = [_make_device("1234", "5678", "Stick")]
        monitor._poll()

        events = monitor._events_log
        assert len(events) == 1
        e = events[0]
        assert e["event"] == "inserted"
        assert e["vid"] == "1234"
        assert e["pid"] == "5678"
        assert e["vid_pid"] == "1234:5678"
        assert e["name"] == "Stick"
        assert "timestamp" in e

    def test_insertion_and_removal_events(self, monitor, mock_query):
        mock_query.return_value = [_make_device("AAAA", "BBBB", "Dev")]
        monitor._poll()

        mock_query.return_value = []
        monitor._poll()

        events = monitor._events_log
        assert len(events) == 2
        assert events[0]["event"] == "inserted"
        assert events[1]["event"] == "removed"

    def test_event_log_capped_at_500(self, monitor, mock_query):
        # Simulate 600 insertions - each with a different VID so they count as new.
        for i in range(600):
            vid = f"{i // 1000:04X}"
            pid = f"{i % 1000:04X}"
            mock_query.return_value = [_make_device(vid, pid, f"Dev{i}")]
            monitor._poll()

        assert len(monitor._events_log) == 500
        # Each poll after the first produces one insertion + one removal event.
        # The last poll (i=599) inserts Dev599 and removes Dev598.
        # The insertion event for Dev599 is the second-to-last event.
        assert monitor._events_log[-2]["name"] == "Dev599"
        assert monitor._events_log[-2]["event"] == "inserted"

    def test_events_property(self, monitor, mock_query):
        mock_query.return_value = [_make_device("1111", "2222", "A")]
        monitor._poll()

        assert monitor.events == monitor._events_log


# ---------------------------------------------------------------------------
# Properties
# ---------------------------------------------------------------------------


class TestProperties:
    """Tests for latest_devices and events properties."""

    def test_latest_devices_after_poll(self, monitor, mock_query):
        devices = [_make_device("1111", "2222", "DevA")]
        mock_query.return_value = devices
        monitor._poll()

        assert monitor.latest_devices == devices

    def test_latest_devices_initial(self, monitor):
        assert monitor.latest_devices == []

    def test_set_callback(self, monitor):
        cb = MagicMock()
        monitor.set_callback(cb)
        assert monitor._callback is cb


# ---------------------------------------------------------------------------
# Lifecycle — run / stop / status
# ---------------------------------------------------------------------------


class TestLifecycle:
    """Tests for run(), stop(), and status()."""

    def test_run_primes_known_devices(self, monitor, mock_query):
        mock_query.return_value = [_make_device("AAAA", "BBBB", "Dev")]

        async def _run_and_stop():
            task = asyncio.create_task(monitor.run())
            # Let it prime and do at least one poll.
            await asyncio.sleep(0.05)
            await monitor.stop()
            await task

        asyncio.run(_run_and_stop())

        assert ("AAAA", "BBBB") in monitor._known

    def test_run_sets_running_true(self, monitor, mock_query):
        mock_query.return_value = []

        async def _run_and_stop():
            task = asyncio.create_task(monitor.run())
            await asyncio.sleep(0.02)
            assert monitor._running is True
            await monitor.stop()
            await task

        asyncio.run(_run_and_stop())

    def test_stop_sets_running_false(self, monitor, mock_query):
        mock_query.return_value = []

        async def _run_and_stop():
            task = asyncio.create_task(monitor.run())
            await asyncio.sleep(0.02)
            await monitor.stop()
            await task

        asyncio.run(_run_and_stop())
        assert monitor._running is False

    def test_run_does_nothing_if_already_running(self, monitor, mock_query):
        mock_query.return_value = [_make_device("1111", "2222")]

        async def _double_run():
            # Start first run.
            task = asyncio.create_task(monitor.run())
            await asyncio.sleep(0.02)

            # Try to start again — should be a no-op.
            task2 = asyncio.create_task(monitor.run())
            await task2
            await monitor.stop()
            await task

        asyncio.run(_double_run())
        # Known still primed from first run.
        assert ("1111", "2222") in monitor._known

    def test_status_when_running(self, monitor, mock_query):
        mock_query.return_value = []

        async def _run():
            task = asyncio.create_task(monitor.run())
            await asyncio.sleep(0.02)
            s = monitor.status()
            await monitor.stop()
            await task
            return s

        s = asyncio.run(_run())
        assert s["running"] is True
        assert s["enabled"] is True
        assert s["blocklist_entries"] == 0
        assert s["active_devices"] == 0

    def test_status_when_stopped(self, monitor):
        s = monitor.status()
        assert s["running"] is False
        assert s["enabled"] is True

    def test_status_includes_blocklist_count(self, mon_config, alert_store, mock_query):
        usb_cfg = USBConfig(blocklist=["A:B", "C:D", "E:F"])
        mon = USBMonitor(
            mon_config=mon_config,
            usb_config=usb_cfg,
            alert_store=alert_store,
        )
        assert mon.status()["blocklist_entries"] == 3

    def test_status_includes_active_devices(self, monitor, mock_query):
        mock_query.return_value = [
            _make_device("A", "B"),
            _make_device("C", "D"),
            _make_device("E", "F"),
        ]
        monitor._poll()
        assert monitor.status()["active_devices"] == 3


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """Corner cases and error handling."""

    def test_device_without_vid_pid_ignored_for_known(self, monitor, alert_store, mock_query):
        """Devices with empty VID/PID should not be tracked."""
        mock_query.return_value = [
            {"vid": "", "pid": "", "vid_pid": "", "name": "No VID", "device_path": ""}
        ]

        monitor._poll()

        assert len(monitor._known) == 0
        assert len(alert_store.get_all()) == 0

    def test_device_with_vid_only_no_alert(self, monitor, alert_store, mock_query):
        """Device with only VID (no PID) should not trigger insertion."""
        mock_query.return_value = [
            {"vid": "1234", "pid": "", "vid_pid": "1234:", "name": "Half", "device_path": ""}
        ]

        monitor._poll()

        assert len(alert_store.get_all()) == 0

    def test_poll_graceful_on_wmi_failure(self, monitor, alert_store, mock_query):
        """When WMI returns empty list, no errors and no alerts."""
        mock_query.return_value = []
        monitor._poll()
        # Should not raise, no alerts.
        assert len(alert_store.get_all()) == 0

    def test_callback_invoked_on_poll(self, monitor, mock_query):
        callback = MagicMock()
        monitor.set_callback(callback)

        devices = [_make_device("1111", "2222", "Dev")]
        mock_query.return_value = devices
        monitor._poll()

        callback.assert_called_once()
        args = callback.call_args[0]
        assert args[0] == devices
        # events log slice (last 20).
        assert isinstance(args[1], list)

    def test_poll_does_not_raise_on_exception(self, monitor, mock_query):
        """Even if something unexpected happens during _poll, the run loop should continue.
        Here we test _poll directly; the exception handler is in run()."""
        mock_query.side_effect = RuntimeError("WMI crash")
        # _poll does NOT catch exceptions itself; the try/except is in run().
        # So calling _poll directly will raise.
        with pytest.raises(RuntimeError):
            monitor._poll()

    def test_stop_when_not_running(self, monitor):
        """stop() should be safe to call when not running."""

        async def _stop():
            await monitor.stop()

        asyncio.run(_stop())
        assert monitor._running is False

    def test_stop_with_active_task(self, monitor, mock_query):
        """stop() cancels the task if present."""
        mock_query.return_value = []

        async def _run_then_stop():
            # Manually set _task to simulate a tracked task.
            async def dummy_loop():
                while monitor._running:
                    await asyncio.sleep(0.01)

            monitor._task = asyncio.create_task(dummy_loop())
            monitor._running = True

            await monitor.stop()
            assert monitor._task.done()
            assert monitor._running is False

        asyncio.run(_run_then_stop())
