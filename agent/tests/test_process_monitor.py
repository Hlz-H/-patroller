"""Unit tests for ProcessMonitor."""

from __future__ import annotations

import asyncio

from unittest.mock import MagicMock, PropertyMock, patch

import psutil
import pytest

from agent.alert import AlertStore, AlertType
from agent.config import MonitorConfig, ProcessConfig
from agent.monitors.process_monitor import ProcessMonitor

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_mon_config(enabled: bool = True, interval: float = 5.0) -> MonitorConfig:
    return MonitorConfig(enabled=enabled, interval_seconds=interval)


def _make_proc_config(whitelist=None, blacklist=None) -> ProcessConfig:
    return ProcessConfig(
        whitelist=whitelist if whitelist is not None else [],
        blacklist=blacklist if blacklist is not None else [],
    )


def _make_iter_proc(pid, name, exe, cpu=0.0, mem=0.0, status="running"):
    """Create a mock psutil.Process as returned by process_iter."""
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
    """Create a mock for psutil.Process(pid) used in new-process detection."""
    proc = MagicMock()
    proc.name.return_value = name
    proc.exe.return_value = exe
    return proc


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mon_config():
    return _make_mon_config()


@pytest.fixture
def proc_config():
    return _make_proc_config()


@pytest.fixture
def alert_store():
    return MagicMock(spec=AlertStore)


@pytest.fixture
def pm(mon_config, proc_config, alert_store):
    """Return a ProcessMonitor with default config (no blacklist/whitelist)."""
    return ProcessMonitor(mon_config, proc_config, alert_store)


@pytest.fixture
def pm_blacklist(mon_config, alert_store):
    """ProcessMonitor with taskmgr.exe blacklisted."""
    pc = _make_proc_config(blacklist=["taskmgr.exe"])
    return ProcessMonitor(mon_config, pc, alert_store)


@pytest.fixture
def pm_both_lists(mon_config, alert_store):
    """ProcessMonitor with both whitelist and blacklist."""
    pc = _make_proc_config(whitelist=["explorer.exe"], blacklist=["explorer.exe", "taskmgr.exe"])
    return ProcessMonitor(mon_config, pc, alert_store)


# ---------------------------------------------------------------------------
# Constructor
# ---------------------------------------------------------------------------


class TestConstructor:
    def test_stores_configs(self, mon_config, proc_config, alert_store):
        pm = ProcessMonitor(mon_config, proc_config, alert_store)
        assert pm._mon_config is mon_config
        assert pm._proc_config is proc_config
        assert pm._alert_store is alert_store

    def test_initializes_empty_state(self, pm):
        assert pm._previous_pids == set()
        assert pm._latest_snapshot == []

    def test_initializes_empty_callback_and_running(self, pm):
        assert pm._callback is None
        assert pm._running is False
        assert pm._task is None

    def test_refreshes_lists_on_construction(self, alert_store):
        pc = _make_proc_config(whitelist=["A.exe"], blacklist=["B.exe", "C.exe"])
        pm = ProcessMonitor(_make_mon_config(), pc, alert_store)
        assert pm._whitelist == {"a.exe"}
        assert pm._blacklist == {"b.exe", "c.exe"}

    def test_empty_lists_when_no_config_lists(self, pm):
        assert pm._whitelist == set()
        assert pm._blacklist == set()

    def test_lowercase_normalisation(self, alert_store):
        pc = _make_proc_config(
            whitelist=["Explorer.EXE", "Cmd.ExE"],
            blacklist=["TaskMgr.EXE"],
        )
        pm = ProcessMonitor(_make_mon_config(), pc, alert_store)
        assert pm._whitelist == {"explorer.exe", "cmd.exe"}
        assert pm._blacklist == {"taskmgr.exe"}


# ---------------------------------------------------------------------------
# Whitelist / blacklist logic
# ---------------------------------------------------------------------------


class TestIsBlacklisted:
    def test_true_for_exact_match(self, pm_blacklist):
        assert pm_blacklist._is_blacklisted("taskmgr.exe", "") is True

    def test_true_for_case_insensitive_match(self, pm_blacklist):
        assert pm_blacklist._is_blacklisted("TASKMGR.EXE", "") is True
        assert pm_blacklist._is_blacklisted("Taskmgr.Exe", "") is True

    def test_false_for_non_blacklisted(self, pm_blacklist):
        assert pm_blacklist._is_blacklisted("notepad.exe", "") is False

    def test_ignores_exe_parameter(self, pm_blacklist):
        """_is_blacklisted only uses name, not exe."""
        assert pm_blacklist._is_blacklisted("taskmgr.exe", "C:\\some\\path.exe") is True
        assert pm_blacklist._is_blacklisted("notepad.exe", "taskmgr.exe") is False

    def test_does_not_check_whitelist(self, pm_both_lists):
        """_is_blacklisted returns True even if name is also whitelisted.
        The override is at the _poll call site, not inside _is_blacklisted."""
        assert pm_both_lists._is_blacklisted("explorer.exe", "") is True


class TestIsWhitelisted:
    def test_true_for_exact_match(self, pm_both_lists):
        assert pm_both_lists._is_whitelisted("explorer.exe", "") is True

    def test_true_for_case_insensitive_match(self, pm_both_lists):
        assert pm_both_lists._is_whitelisted("EXPLORER.EXE", "") is True
        assert pm_both_lists._is_whitelisted("Explorer.Exe", "") is True

    def test_false_for_non_whitelisted(self, pm_both_lists):
        assert pm_both_lists._is_whitelisted("notepad.exe", "") is False

    def test_ignores_exe_parameter(self, pm_both_lists):
        assert pm_both_lists._is_whitelisted("explorer.exe", "C:\\other.exe") is True


class TestWhitelistOverridesBlacklist:
    """In _poll, whitelist takes priority over blacklist."""

    def test_poll_skips_blacklist_handling_when_whitelisted(self, pm_both_lists):
        """A process in both lists should NOT trigger _handle_blacklisted."""
        proc = _make_iter_proc(100, "explorer.exe", "C:\\Windows\\explorer.exe")

        with patch.object(pm_both_lists, "_handle_blacklisted") as mock_handle:
            with patch("agent.monitors.process_monitor.psutil.process_iter", return_value=[proc]):
                # Also mock psutil.Process for new-process detection (no new pids expected)
                with patch("agent.monitors.process_monitor.psutil.Process"):
                    pm_both_lists._poll()

        mock_handle.assert_not_called()

    def test_poll_calls_handle_blacklisted_when_only_blacklisted(self, pm_blacklist):
        """A blacklisted-only process SHOULD trigger _handle_blacklisted."""
        proc = _make_iter_proc(200, "taskmgr.exe", "C:\\taskmgr.exe")

        with patch.object(pm_blacklist, "_handle_blacklisted") as mock_handle:
            with patch("agent.monitors.process_monitor.psutil.process_iter", return_value=[proc]):
                with patch("agent.monitors.process_monitor.psutil.Process"):
                    pm_blacklist._poll()

        mock_handle.assert_called_once()


class TestRefreshLists:
    def test_updates_after_config_change(self, pm):
        assert pm._whitelist == set()
        assert pm._blacklist == set()

        new_pc = _make_proc_config(whitelist=["svchost.exe"], blacklist=["evil.exe"])
        pm.update_config(new_pc)
        assert pm._whitelist == {"svchost.exe"}
        assert pm._blacklist == {"evil.exe"}
        assert pm._proc_config is new_pc

    def test_clears_when_config_has_empty_lists(self, pm_both_lists):
        assert pm_both_lists._whitelist == {"explorer.exe"}
        assert pm_both_lists._blacklist == {"explorer.exe", "taskmgr.exe"}

        empty_pc = _make_proc_config()
        pm_both_lists.update_config(empty_pc)
        assert pm_both_lists._whitelist == set()
        assert pm_both_lists._blacklist == set()


# ---------------------------------------------------------------------------
# New process detection (_poll)
# ---------------------------------------------------------------------------


class TestNewProcessDetection:
    def test_alert_when_new_pid_appears(self, pm, alert_store):
        """A PID not in _previous_pids generates an info alert."""
        pm._previous_pids = {1}  # only PID 1 known

        proc = _make_iter_proc(100, "notepad.exe", "C:\\notepad.exe")
        new_proc_mock = _make_process_mock(100, "notepad.exe", "C:\\notepad.exe")

        with patch("agent.monitors.process_monitor.psutil.process_iter", return_value=[proc]):
            with patch("agent.monitors.process_monitor.psutil.Process", return_value=new_proc_mock):
                snapshot = pm._poll()

        alert_store.info.assert_called_once()
        call_args = alert_store.info.call_args
        assert call_args[0][0] == AlertType.PROCESS
        assert "notepad.exe" in call_args[0][1]
        assert call_args[1]["pid"] == 100
        assert call_args[1]["name"] == "notepad.exe"
        assert call_args[1]["exe"] == "C:\\notepad.exe"

        assert 100 in pm._previous_pids
        assert len(snapshot) == 1
        assert snapshot[0]["pid"] == 100

    def test_no_alert_when_pid_already_known(self, pm, alert_store):
        """No alert for a PID already in _previous_pids."""
        pm._previous_pids = {100}

        proc = _make_iter_proc(100, "notepad.exe", "C:\\notepad.exe")

        with patch("agent.monitors.process_monitor.psutil.process_iter", return_value=[proc]):
            with patch("agent.monitors.process_monitor.psutil.Process"):
                pm._poll()

        alert_store.info.assert_not_called()

    def test_new_process_alert_skipped_for_blacklisted(self, pm_blacklist, alert_store):
        """Blacklisted new processes don't get 'new process' alerts (they're handled by _handle_blacklisted)."""
        pm_blacklist._previous_pids = set()

        proc = _make_iter_proc(200, "taskmgr.exe", "C:\\taskmgr.exe")
        # Blacklisted → _handle_blacklisted is called; the new-process section should skip it.
        # _handle_blacklisted calls alert_store.critical then alert_store.info on kill success.
        new_proc = _make_process_mock(200, "taskmgr.exe", "C:\\taskmgr.exe")

        with patch("agent.monitors.process_monitor.psutil.process_iter", return_value=[proc]):
            with patch("agent.monitors.process_monitor.psutil.Process", return_value=new_proc):
                pm_blacklist._poll()

        # The info alert with "New process started" should NOT be issued for blacklisted processes.
        # (critical alert from _handle_blacklisted and kill success info are separate.)
        new_process_alerts = [
            c for c in alert_store.info.call_args_list
            if "New process started" in str(c)
        ]
        assert len(new_process_alerts) == 0

    def test_new_process_info_alert_details(self, pm, alert_store):
        """Verify new process alert has correct type, message, pid, name, exe, group_key."""
        pm._previous_pids = set()

        proc = _make_iter_proc(42, "myapp.exe", "C:\\app\\myapp.exe")
        new_proc = _make_process_mock(42, "myapp.exe", "C:\\app\\myapp.exe")

        with patch("agent.monitors.process_monitor.psutil.process_iter", return_value=[proc]):
            with patch("agent.monitors.process_monitor.psutil.Process", return_value=new_proc):
                pm._poll()

        alert_store.info.assert_called_with(
            AlertType.PROCESS,
            "New process started: myapp.exe",
            pid=42,
            name="myapp.exe",
            exe="C:\\app\\myapp.exe",
            group_key="process:new:myapp.exe",
        )

    def test_new_process_access_denied_suppressed(self, pm, alert_store):
        """psutil.Process(pid) raising AccessDenied is silently caught."""
        pm._previous_pids = set()

        proc = _make_iter_proc(99, "secret.exe", "")
        mock_psutil = MagicMock()
        mock_psutil.Process.side_effect = psutil.AccessDenied()

        with patch("agent.monitors.process_monitor.psutil.process_iter", return_value=[proc]):
            with patch("agent.monitors.process_monitor.psutil.Process", side_effect=psutil.AccessDenied):
                pm._poll()

        # No alert should be raised for the new process
        alert_store.info.assert_not_called()
        # Still tracks the PID in previous_pids
        assert 99 in pm._previous_pids

    def test_no_such_process_during_new_detection_suppressed(self, pm, alert_store):
        """Process that disappears between iteration and detection is silently handled."""
        pm._previous_pids = set()

        proc = _make_iter_proc(77, "ephemeral.exe", "")
        with patch("agent.monitors.process_monitor.psutil.process_iter", return_value=[proc]):
            with patch("agent.monitors.process_monitor.psutil.Process", side_effect=psutil.NoSuchProcess(77)):
                pm._poll()

        alert_store.info.assert_not_called()

    def test_pid_none_skipped(self, pm, alert_store):
        """Processes with pid=None are skipped and not added to current_pids."""
        pm._previous_pids = set()

        proc = _make_iter_proc(None, "bad.exe", "")
        with patch("agent.monitors.process_monitor.psutil.process_iter", return_value=[proc]):
            with patch("agent.monitors.process_monitor.psutil.Process"):
                pm._poll()

        assert pm._previous_pids == set()
        alert_store.info.assert_not_called()

    def test_empty_name_and_exe_normalised(self, pm, alert_store):
        """Empty/None name and exe are normalised to ''."""
        pm._previous_pids = set()

        proc = MagicMock()
        proc.info = {"pid": 10, "name": None, "exe": None, "cpu_percent": 0, "memory_percent": 0, "status": "running"}

        new_proc = _make_process_mock(10, "", "")

        with patch("agent.monitors.process_monitor.psutil.process_iter", return_value=[proc]):
            with patch("agent.monitors.process_monitor.psutil.Process", return_value=new_proc):
                snapshot = pm._poll()

        assert snapshot[0]["name"] == ""
        assert snapshot[0]["exe"] == ""

    def test_exception_in_process_iter_skipped(self, pm, alert_store):
        """If a single process raises NoSuchProcess in the iter loop, it is skipped."""
        pm._previous_pids = set()

        good_proc = _make_iter_proc(1, "good.exe", "C:\\good.exe")
        bad_proc = MagicMock()
        bad_proc.info = {"pid": 2, "name": "bad.exe", "exe": ""}
        # Simulate that accessing .info on bad_proc works but _handle_blacklisted
        # or something else could raise. Instead, let's use the exception in the loop:
        # The loop catches NoSuchProcess/AccessDenied/ZombieProcess.
        # We can't easily make .info raise, but we can set info such that
        # accessing it works but a later exception would be caught.
        # Actually, the try block wraps everything after for loop.
        # To test the except clause, I'll patch process_iter to return a mock
        # whose .info attribute raises on access.
        bad_proc = MagicMock()
        type(bad_proc).info = PropertyMock(side_effect=psutil.NoSuchProcess(2))

        new_proc = _make_process_mock(1, "good.exe", "C:\\good.exe")

        with patch("agent.monitors.process_monitor.psutil.process_iter", return_value=[bad_proc, good_proc]):
            with patch("agent.monitors.process_monitor.psutil.Process", return_value=new_proc):
                snapshot = pm._poll()

        # good.exe should be in snapshot
        assert len(snapshot) == 1
        assert snapshot[0]["pid"] == 1


# ---------------------------------------------------------------------------
# Blacklist enforcement (_poll / _handle_blacklisted)
# ---------------------------------------------------------------------------


class TestHandleBlacklisted:
    def test_raises_critical_alert(self, pm_blacklist, alert_store):
        proc = _make_iter_proc(200, "taskmgr.exe", "C:\\taskmgr.exe")
        pm_blacklist._handle_blacklisted(proc, "taskmgr.exe", "C:\\taskmgr.exe", 200)

        alert_store.critical.assert_called_once_with(
            AlertType.PROCESS,
            "Blacklisted process detected: taskmgr.exe",
            pid=200,
            name="taskmgr.exe",
            exe="C:\\taskmgr.exe",
            group_key="process:blacklisted:taskmgr.exe",
        )

    def test_kills_process_and_logs_info(self, pm_blacklist, alert_store):
        proc = _make_iter_proc(200, "taskmgr.exe", "C:\\taskmgr.exe")
        # By default MagicMock.kill() does nothing / returns a MagicMock (no exception)
        pm_blacklist._handle_blacklisted(proc, "taskmgr.exe", "C:\\taskmgr.exe", 200)

        proc.kill.assert_called_once()
        alert_store.info.assert_called_once_with(
            AlertType.PROCESS,
            "Killed blacklisted process: taskmgr.exe (PID 200)",
            pid=200,
            name="taskmgr.exe",
            group_key="process:killed:taskmgr.exe",
        )

    def test_kill_fails_access_denied_no_second_alert(self, pm_blacklist, alert_store):
        proc = _make_iter_proc(200, "taskmgr.exe", "C:\\taskmgr.exe")
        proc.kill.side_effect = psutil.AccessDenied()

        pm_blacklist._handle_blacklisted(proc, "taskmgr.exe", "C:\\taskmgr.exe", 200)

        # Critical alert still raised
        alert_store.critical.assert_called_once()
        # Info alert for kill success NOT raised
        # (info may have been called for other reasons, so check it wasn't called with kill message)
        kill_calls = [
            c for c in alert_store.info.call_args_list
            if "Killed blacklisted process" in str(c)
        ]
        assert len(kill_calls) == 0

    def test_kill_fails_no_such_process_no_second_alert(self, pm_blacklist, alert_store):
        proc = _make_iter_proc(200, "taskmgr.exe", "C:\\taskmgr.exe")
        proc.kill.side_effect = psutil.NoSuchProcess(200)

        pm_blacklist._handle_blacklisted(proc, "taskmgr.exe", "C:\\taskmgr.exe", 200)

        alert_store.critical.assert_called_once()
        kill_calls = [
            c for c in alert_store.info.call_args_list
            if "Killed blacklisted process" in str(c)
        ]
        assert len(kill_calls) == 0


# ---------------------------------------------------------------------------
# kill_process
# ---------------------------------------------------------------------------


class TestKillProcess:
    def test_success_kills_and_alerts(self, pm, alert_store):
        mock_proc = MagicMock()
        mock_proc.name.return_value = "notepad.exe"

        with patch("agent.monitors.process_monitor.psutil.Process", return_value=mock_proc):
            success, msg = pm.kill_process(123)

        assert success is True
        assert "notepad.exe (PID 123) killed" in msg
        mock_proc.kill.assert_called_once()
        alert_store.info.assert_called_once_with(
            AlertType.PROCESS,
            msg,
            pid=123,
            name="notepad.exe",
            group_key="process:killed:notepad.exe",
        )
        assert 123 not in pm._previous_pids

    def test_removes_pid_from_previous_pids(self, pm):
        pm._previous_pids = {123, 456}
        mock_proc = MagicMock()
        mock_proc.name.return_value = "x.exe"

        with patch("agent.monitors.process_monitor.psutil.Process", return_value=mock_proc):
            pm.kill_process(123)

        assert 123 not in pm._previous_pids
        assert 456 in pm._previous_pids

    def test_no_such_process(self, pm, alert_store):
        with patch("agent.monitors.process_monitor.psutil.Process", side_effect=psutil.NoSuchProcess(999)):
            success, msg = pm.kill_process(999)

        assert success is False
        assert msg == "No such process: PID 999"
        alert_store.info.assert_not_called()

    def test_access_denied(self, pm, alert_store):
        with patch("agent.monitors.process_monitor.psutil.Process", side_effect=psutil.AccessDenied()):
            success, msg = pm.kill_process(1)

        assert success is False
        assert msg == "Access denied when killing PID 1"
        alert_store.info.assert_not_called()


# ---------------------------------------------------------------------------
# Lifecycle (run / stop / status)
# ---------------------------------------------------------------------------


class TestLifecycle:
    @pytest.mark.asyncio
    async def test_run_primes_previous_pids(self, pm):
        """run() primes _previous_pids with current PIDs."""
        mock_proc1 = MagicMock()
        mock_proc1.pid = 100
        mock_proc2 = MagicMock()
        mock_proc2.pid = 200

        with patch("agent.monitors.process_monitor.psutil.process_iter", return_value=[mock_proc1, mock_proc2]):
            # Patch _poll to avoid side effects, and sleep to break loop quickly
            with patch.object(pm, "_poll"):
                # Raise to exit the while loop after one iteration
                loop_count = 0

                async def mock_sleep(_):
                    nonlocal loop_count
                    loop_count += 1
                    if loop_count >= 2:
                        pm._running = False  # stop after first sleep

                with patch("agent.monitors.process_monitor.asyncio.sleep", side_effect=mock_sleep):
                    await pm.run()

        assert pm._previous_pids == {100, 200}

    @pytest.mark.asyncio
    async def test_run_already_running_noop(self, pm):
        """If already running, run() returns immediately."""
        pm._running = True
        pm._previous_pids = {999}

        async def fail_if_called(*args):
            pytest.fail("_poll should not be called")

        with patch.object(pm, "_poll", side_effect=fail_if_called):
            await pm.run()

        # State unchanged
        assert pm._previous_pids == {999}

    @pytest.mark.asyncio
    async def test_stop_sets_running_false(self, pm):
        pm._running = True
        await pm.stop()
        assert pm._running is False

    @pytest.mark.asyncio
    async def test_stop_cancels_task(self, pm):
        pm._running = True
        task = asyncio.create_task(asyncio.sleep(10))
        pm._task = task
        await pm.stop()
        assert task.cancelled() or task.done()

    def test_status_returns_correct_values(self, pm, mon_config):
        pm._running = True
        pm._latest_snapshot = [{"pid": 1}, {"pid": 2}, {"pid": 3}]
        # _blacklist is set via constructor; default is empty

        s = pm.status()
        assert s["running"] is True
        assert s["enabled"] is mon_config.enabled
        assert s["tracked_processes"] == 3
        assert s["blacklist_entries"] == 0

    def test_status_with_blacklist(self, pm_blacklist):
        s = pm_blacklist.status()
        assert s["blacklist_entries"] == 1

    def test_status_when_disabled(self):
        mc = _make_mon_config(enabled=False)
        pc = _make_proc_config()
        pm = ProcessMonitor(mc, pc, MagicMock(spec=AlertStore))
        s = pm.status()
        assert s["enabled"] is False


# ---------------------------------------------------------------------------
# Callback
# ---------------------------------------------------------------------------


class TestCallback:
    def test_set_callback_stores(self, pm):
        cb = MagicMock()
        pm.set_callback(cb)
        assert pm._callback is cb

    def test_set_callback_none(self, pm):
        pm._callback = MagicMock()
        pm.set_callback(None)
        assert pm._callback is None

    def test_callback_receives_snapshot_after_poll(self, pm):
        cb = MagicMock()
        pm.set_callback(cb)

        proc = _make_iter_proc(1, "a.exe", "C:\\a.exe")
        with patch("agent.monitors.process_monitor.psutil.process_iter", return_value=[proc]):
            with patch("agent.monitors.process_monitor.psutil.Process"):
                pm._poll()

        cb.assert_called_once()
        snapshot_arg = cb.call_args[0][0]
        assert isinstance(snapshot_arg, list)
        assert snapshot_arg[0]["pid"] == 1

    def test_callback_not_called_when_none(self, pm):
        pm._callback = None
        proc = _make_iter_proc(1, "a.exe", "C:\\a.exe")
        with patch("agent.monitors.process_monitor.psutil.process_iter", return_value=[proc]):
            with patch("agent.monitors.process_monitor.psutil.Process"):
                pm._poll()
        # Should not raise


# ---------------------------------------------------------------------------
# latest_snapshot property
# ---------------------------------------------------------------------------


class TestLatestSnapshot:
    def test_returns_latest_snapshot(self, pm):
        snapshot = [{"pid": 1}, {"pid": 2}]
        pm._latest_snapshot = snapshot
        assert pm.latest_snapshot is snapshot


# ---------------------------------------------------------------------------
# _poll returns snapshot
# ---------------------------------------------------------------------------


class TestPollReturnsSnapshot:
    def test_returns_snapshot_list(self, pm):
        proc1 = _make_iter_proc(1, "a.exe", "C:\\a.exe")
        proc2 = _make_iter_proc(2, "b.exe", "C:\\b.exe")

        with patch("agent.monitors.process_monitor.psutil.process_iter", return_value=[proc1, proc2]):
            with patch("agent.monitors.process_monitor.psutil.Process"):
                snapshot = pm._poll()

        assert len(snapshot) == 2
        assert snapshot[0]["pid"] == 1
        assert snapshot[0]["name"] == "a.exe"
        assert snapshot[1]["pid"] == 2
        assert snapshot[1]["name"] == "b.exe"

    def test_snapshot_stored_as_latest(self, pm):
        proc = _make_iter_proc(5, "x.exe", "C:\\x.exe")
        with patch("agent.monitors.process_monitor.psutil.process_iter", return_value=[proc]):
            with patch("agent.monitors.process_monitor.psutil.Process"):
                pm._poll()

        assert pm._latest_snapshot[0]["pid"] == 5

    def test_snapshot_includes_all_fields(self, pm):
        proc = _make_iter_proc(10, "test.exe", "C:\\test.exe", cpu=5.0, mem=10.0, status="sleeping")
        with patch("agent.monitors.process_monitor.psutil.process_iter", return_value=[proc]):
            with patch("agent.monitors.process_monitor.psutil.Process"):
                snapshot = pm._poll()

        s = snapshot[0]
        assert s["pid"] == 10
        assert s["name"] == "test.exe"
        assert s["exe"] == "C:\\test.exe"
        assert s["cpu_percent"] == 5.0
        assert s["memory_percent"] == 10.0
        assert s["status"] == "sleeping"

    def test_missing_fields_get_defaults(self, pm):
        proc = MagicMock()
        proc.info = {"pid": 77, "name": "minimal.exe", "exe": ""}
        # cpu_percent, memory_percent, status missing

        with patch("agent.monitors.process_monitor.psutil.process_iter", return_value=[proc]):
            with patch("agent.monitors.process_monitor.psutil.Process"):
                snapshot = pm._poll()

        assert snapshot[0]["cpu_percent"] == 0.0
        assert snapshot[0]["memory_percent"] == 0.0
        assert snapshot[0]["status"] == ""


# ---------------------------------------------------------------------------
# update_config
# ---------------------------------------------------------------------------


class TestUpdateConfig:
    def test_updates_proc_config_and_lists(self, pm, alert_store):
        new_pc = _make_proc_config(whitelist=["cmd.exe"], blacklist=["virus.exe"])
        pm.update_config(new_pc)

        assert pm._proc_config is new_pc
        assert pm._whitelist == {"cmd.exe"}
        assert pm._blacklist == {"virus.exe"}


# ---------------------------------------------------------------------------
# _poll exception handling (per-process loop)
# ---------------------------------------------------------------------------


class TestPollPerProcessException:
    def test_no_such_process_in_iter_skipped(self, pm):
        """process_iter items that raise NoSuchProcess on .info access are skipped."""
        good = _make_iter_proc(1, "good.exe", "C:\\good.exe")
        bad = MagicMock()
        type(bad).info = PropertyMock(side_effect=psutil.NoSuchProcess(99))

        with patch("agent.monitors.process_monitor.psutil.process_iter", return_value=[bad, good]):
            with patch("agent.monitors.process_monitor.psutil.Process"):
                snapshot = pm._poll()

        assert len(snapshot) == 1
        assert snapshot[0]["pid"] == 1

    def test_access_denied_in_iter_skipped(self, pm):
        good = _make_iter_proc(1, "good.exe", "C:\\good.exe")
        bad = MagicMock()
        type(bad).info = PropertyMock(side_effect=psutil.AccessDenied())

        with patch("agent.monitors.process_monitor.psutil.process_iter", return_value=[bad, good]):
            with patch("agent.monitors.process_monitor.psutil.Process"):
                snapshot = pm._poll()

        assert len(snapshot) == 1

    def test_zombie_process_in_iter_skipped(self, pm):
        good = _make_iter_proc(1, "good.exe", "C:\\good.exe")
        bad = MagicMock()
        type(bad).info = PropertyMock(side_effect=psutil.ZombieProcess(999))

        with patch("agent.monitors.process_monitor.psutil.process_iter", return_value=[bad, good]):
            with patch("agent.monitors.process_monitor.psutil.Process"):
                snapshot = pm._poll()

        assert len(snapshot) == 1
