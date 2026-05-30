"""Unit tests for SystemResourceMonitor and SystemResourceMetrics."""

from __future__ import annotations

import asyncio
import logging
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

from agent.config import MonitorConfig
from agent.monitors.system_resource import (
    SystemResourceMetrics,
    SystemResourceMonitor,
)


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture(autouse=True)
def mock_psutil():
    """Mock all psutil functions used by _collect()."""
    with patch(
        "agent.monitors.system_resource.psutil.cpu_percent",
        side_effect=lambda interval=None, percpu=False: (
            [23.4, 45.6, 67.8, 12.3, 34.5, 56.7, 78.9, 90.1]
            if percpu
            else 45.6
        ),
    ) as cpu_percent_mock:
        with patch(
            "agent.monitors.system_resource.psutil.cpu_count",
            return_value=8,
        ) as cpu_count_mock:
            with patch(
                "agent.monitors.system_resource.psutil.virtual_memory",
                return_value=Mock(
                    total=16_000_000_000,
                    available=8_000_000_000,
                    used=8_000_000_000,
                    percent=50.0,
                ),
            ) as virtual_memory_mock:
                with patch(
                    "agent.monitors.system_resource.psutil.swap_memory",
                    return_value=Mock(
                        total=32_000_000_000,
                        used=1_000_000_000,
                        percent=3.1,
                    ),
                ) as swap_memory_mock:
                    with patch(
                        "agent.monitors.system_resource.psutil.disk_partitions",
                        return_value=[],
                    ) as disk_partitions_mock:
                        with patch(
                            "agent.monitors.system_resource.psutil.disk_io_counters",
                            return_value=Mock(
                                read_bytes=1000,
                                write_bytes=2000,
                            ),
                        ) as disk_io_mock:
                            with patch(
                                "agent.monitors.system_resource.psutil.net_io_counters",
                                return_value=Mock(
                                    bytes_sent=500,
                                    bytes_recv=600,
                                ),
                            ) as net_io_mock:
                                with patch(
                                    "agent.monitors.system_resource.psutil.net_connections",
                                    return_value=[Mock(), Mock()],
                                ) as net_connections_mock:
                                    yield Mock(
                                        cpu_percent=cpu_percent_mock,
                                        cpu_count=cpu_count_mock,
                                        virtual_memory=virtual_memory_mock,
                                        swap_memory=swap_memory_mock,
                                        disk_partitions=disk_partitions_mock,
                                        disk_io_counters=disk_io_mock,
                                        net_io_counters=net_io_mock,
                                        net_connections=net_connections_mock,
                                    )


@pytest.fixture
def basic_config():
    """Return a default MonitorConfig."""
    return MonitorConfig(enabled=True, interval_seconds=5.0)


@pytest.fixture
def disabled_config():
    """Return a disabled MonitorConfig."""
    return MonitorConfig(enabled=False, interval_seconds=1.0)


@pytest.fixture
def custom_config():
    """Return a MonitorConfig with non-default values."""
    return MonitorConfig(enabled=True, interval_seconds=10.0)


# ============================================================================
# SystemResourceMetrics tests
# ============================================================================


class TestSystemResourceMetricsDefaults:
    """Tests for default values of SystemResourceMetrics dataclass."""

    def test_default_cpu_percent(self):
        m = SystemResourceMetrics()
        assert m.cpu_percent == 0.0

    def test_default_cpu_per_core(self):
        m = SystemResourceMetrics()
        assert m.cpu_per_core == []

    def test_default_cpu_count_logical(self):
        m = SystemResourceMetrics()
        assert m.cpu_count_logical == 0

    def test_default_cpu_count_physical(self):
        m = SystemResourceMetrics()
        assert m.cpu_count_physical == 0

    def test_default_memory_fields(self):
        m = SystemResourceMetrics()
        assert m.memory_total == 0
        assert m.memory_available == 0
        assert m.memory_used == 0
        assert m.memory_percent == 0.0

    def test_default_swap_fields(self):
        m = SystemResourceMetrics()
        assert m.swap_total == 0
        assert m.swap_used == 0
        assert m.swap_percent == 0.0

    def test_default_disk_fields(self):
        m = SystemResourceMetrics()
        assert m.disk_partitions == []
        assert m.disk_io_read_bytes == 0
        assert m.disk_io_write_bytes == 0

    def test_default_network_fields(self):
        m = SystemResourceMetrics()
        assert m.net_bytes_sent == 0
        assert m.net_bytes_recv == 0
        assert m.net_connections == 0


class TestSystemResourceMetricsToDict:
    """Tests for to_dict() serialization."""

    def test_to_dict_key_structure(self):
        """Verify to_dict has exactly the expected top-level keys."""
        m = SystemResourceMetrics()
        d = m.to_dict()
        expected_keys = {"cpu", "memory", "swap", "disk", "network"}
        assert set(d.keys()) == expected_keys

    def test_to_dict_cpu_subkeys(self):
        m = SystemResourceMetrics()
        d = m.to_dict()
        expected_subkeys = {"percent", "per_core", "count_logical", "count_physical"}
        assert set(d["cpu"].keys()) == expected_subkeys

    def test_to_dict_memory_subkeys(self):
        m = SystemResourceMetrics()
        d = m.to_dict()
        expected_subkeys = {"total", "available", "used", "percent"}
        assert set(d["memory"].keys()) == expected_subkeys

    def test_to_dict_swap_subkeys(self):
        m = SystemResourceMetrics()
        d = m.to_dict()
        expected_subkeys = {"total", "used", "percent"}
        assert set(d["swap"].keys()) == expected_subkeys

    def test_to_dict_disk_subkeys(self):
        m = SystemResourceMetrics()
        d = m.to_dict()
        expected_subkeys = {"partitions", "io_read_bytes", "io_write_bytes"}
        assert set(d["disk"].keys()) == expected_subkeys

    def test_to_dict_network_subkeys(self):
        m = SystemResourceMetrics()
        d = m.to_dict()
        expected_subkeys = {"bytes_sent", "bytes_recv", "connections"}
        assert set(d["network"].keys()) == expected_subkeys

    def test_to_dict_rounding_cpu_percent_one_decimal(self):
        """cpu_percent rounded to 1 decimal place."""
        m = SystemResourceMetrics(cpu_percent=45.6789)
        d = m.to_dict()
        assert d["cpu"]["percent"] == 45.7

    def test_to_dict_rounding_cpu_percent_exact_one_decimal(self):
        """cpu_percent with exactly 1 decimal stays unchanged."""
        m = SystemResourceMetrics(cpu_percent=45.6)
        d = m.to_dict()
        assert d["cpu"]["percent"] == 45.6

    def test_to_dict_rounding_per_core_values(self):
        """per_core values are each rounded to 1 decimal place."""
        m = SystemResourceMetrics(cpu_per_core=[12.34, 56.78, 90.12])
        d = m.to_dict()
        assert d["cpu"]["per_core"] == [12.3, 56.8, 90.1]

    def test_to_dict_rounding_memory_percent(self):
        """memory_percent rounded to 1 decimal place."""
        m = SystemResourceMetrics(memory_percent=50.555)
        d = m.to_dict()
        assert d["memory"]["percent"] == 50.6

    def test_to_dict_rounding_swap_percent(self):
        """swap_percent rounded to 1 decimal place."""
        m = SystemResourceMetrics(swap_percent=3.1499)
        d = m.to_dict()
        assert d["swap"]["percent"] == 3.1

    def test_to_dict_integer_fields_preserved(self):
        """Integer fields (bytes, counts) are not rounded."""
        m = SystemResourceMetrics(
            cpu_count_logical=16,
            cpu_count_physical=8,
            memory_total=32_000_000_000,
            memory_available=16_000_000_000,
            memory_used=16_000_000_000,
            swap_total=64_000_000_000,
            swap_used=2_000_000_000,
            disk_io_read_bytes=100_000,
            disk_io_write_bytes=200_000,
            net_bytes_sent=1000,
            net_bytes_recv=2000,
            net_connections=42,
        )
        d = m.to_dict()
        assert d["cpu"]["count_logical"] == 16
        assert d["cpu"]["count_physical"] == 8
        assert d["memory"]["total"] == 32_000_000_000
        assert d["memory"]["available"] == 16_000_000_000
        assert d["memory"]["used"] == 16_000_000_000
        assert d["swap"]["total"] == 64_000_000_000
        assert d["swap"]["used"] == 2_000_000_000
        assert d["disk"]["io_read_bytes"] == 100_000
        assert d["disk"]["io_write_bytes"] == 200_000
        assert d["network"]["bytes_sent"] == 1000
        assert d["network"]["bytes_recv"] == 2000
        assert d["network"]["connections"] == 42

    def test_to_dict_full_serialization(self):
        """Complete round-trip: set all fields, verify to_dict matches."""
        m = SystemResourceMetrics(
            cpu_percent=25.5,
            cpu_per_core=[30.1, 40.2],
            cpu_count_logical=4,
            cpu_count_physical=2,
            memory_total=8_000_000_000,
            memory_available=4_000_000_000,
            memory_used=4_000_000_000,
            memory_percent=50.0,
            swap_total=16_000_000_000,
            swap_used=500_000_000,
            swap_percent=3.1,
            disk_partitions=[
                {
                    "device": "/dev/sda1",
                    "mountpoint": "/",
                    "fstype": "ext4",
                    "total": 100_000_000_000,
                    "used": 50_000_000_000,
                    "free": 50_000_000_000,
                    "percent": 50.0,
                }
            ],
            disk_io_read_bytes=500,
            disk_io_write_bytes=1000,
            net_bytes_sent=200,
            net_bytes_recv=300,
            net_connections=5,
        )
        d = m.to_dict()
        assert d["cpu"]["percent"] == 25.5
        assert d["cpu"]["per_core"] == [30.1, 40.2]
        assert d["cpu"]["count_logical"] == 4
        assert d["cpu"]["count_physical"] == 2
        assert d["memory"]["total"] == 8_000_000_000
        assert d["memory"]["available"] == 4_000_000_000
        assert d["memory"]["used"] == 4_000_000_000
        assert d["memory"]["percent"] == 50.0
        assert d["swap"]["total"] == 16_000_000_000
        assert d["swap"]["used"] == 500_000_000
        assert d["swap"]["percent"] == 3.1
        assert len(d["disk"]["partitions"]) == 1
        assert d["disk"]["partitions"][0]["device"] == "/dev/sda1"
        assert d["disk"]["io_read_bytes"] == 500
        assert d["disk"]["io_write_bytes"] == 1000
        assert d["network"]["bytes_sent"] == 200
        assert d["network"]["bytes_recv"] == 300
        assert d["network"]["connections"] == 5


# ============================================================================
# SystemResourceMonitor constructor tests
# ============================================================================


class TestSystemResourceMonitorConstructor:
    """Tests for SystemResourceMonitor initialization."""

    def test_constructor_stores_config(self, basic_config):
        monitor = SystemResourceMonitor(basic_config)
        assert monitor._config is basic_config

    def test_constructor_initial_not_running(self, basic_config):
        monitor = SystemResourceMonitor(basic_config)
        assert monitor._running is False

    def test_constructor_no_callback(self, basic_config):
        monitor = SystemResourceMonitor(basic_config)
        assert monitor._callback is None

    def test_constructor_no_task(self, basic_config):
        monitor = SystemResourceMonitor(basic_config)
        assert monitor._task is None

    def test_constructor_no_latest(self, basic_config):
        monitor = SystemResourceMonitor(basic_config)
        assert monitor._latest is None


# ============================================================================
# set_callback tests
# ============================================================================


class TestSetCallback:
    """Tests for set_callback method."""

    def test_set_callback_stores_reference(self, basic_config):
        monitor = SystemResourceMonitor(basic_config)
        dummy = lambda d: None
        monitor.set_callback(dummy)
        assert monitor._callback is dummy

    def test_set_callback_overwrites_previous(self, basic_config):
        monitor = SystemResourceMonitor(basic_config)
        cb1 = lambda d: None
        cb2 = lambda d: None
        monitor.set_callback(cb1)
        monitor.set_callback(cb2)
        assert monitor._callback is cb2
        assert monitor._callback is not cb1

    def test_set_callback_with_none(self, basic_config):
        monitor = SystemResourceMonitor(basic_config)
        monitor.set_callback(lambda d: None)
        monitor.set_callback(None)
        assert monitor._callback is None


# ============================================================================
# status tests
# ============================================================================


class TestStatus:
    """Tests for status() method."""

    def test_status_default_returns_all_keys(self, basic_config):
        monitor = SystemResourceMonitor(basic_config)
        s = monitor.status()
        assert set(s.keys()) == {"running", "enabled", "interval_seconds"}

    def test_status_initial_not_running(self, basic_config):
        monitor = SystemResourceMonitor(basic_config)
        assert monitor.status()["running"] is False

    def test_status_reflects_config_enabled(self, basic_config):
        monitor = SystemResourceMonitor(basic_config)
        assert monitor.status()["enabled"] is True

    def test_status_reflects_disabled_config(self, disabled_config):
        monitor = SystemResourceMonitor(disabled_config)
        assert monitor.status()["enabled"] is False

    def test_status_reflects_interval(self, basic_config):
        monitor = SystemResourceMonitor(basic_config)
        assert monitor.status()["interval_seconds"] == 5.0

    def test_status_reflects_custom_interval(self, custom_config):
        monitor = SystemResourceMonitor(custom_config)
        assert monitor.status()["interval_seconds"] == 10.0


# ============================================================================
# latest_metrics tests
# ============================================================================


class TestLatestMetrics:
    """Tests for latest_metrics property."""

    def test_latest_metrics_returns_none_initially(self, basic_config):
        monitor = SystemResourceMonitor(basic_config)
        assert monitor.latest_metrics is None

    def test_latest_metrics_returns_dict_after_collect(self, basic_config):
        monitor = SystemResourceMonitor(basic_config)
        monitor._latest = monitor._collect()
        result = monitor.latest_metrics
        assert isinstance(result, dict)
        assert "cpu" in result
        assert "memory" in result

    def test_latest_metrics_returns_to_dict_output(self, basic_config):
        monitor = SystemResourceMonitor(basic_config)
        monitor._latest = monitor._collect()
        result = monitor.latest_metrics
        assert result["cpu"]["percent"] == 45.6

    def test_latest_metrics_still_none_if_latest_was_none(self, basic_config):
        """Ensure latest_metrics does not return stale data if _latest is None."""
        monitor = SystemResourceMonitor(basic_config)
        monitor._latest = None
        assert monitor.latest_metrics is None

    def test_latest_metrics_updates_after_second_collection(self, basic_config):
        """Each _collect() call updates latest_metrics."""
        monitor = SystemResourceMonitor(basic_config)

        # First collect with default mock (cpu_percent=45.6)
        monitor._latest = monitor._collect()
        first = monitor.latest_metrics
        assert first["cpu"]["percent"] == 45.6

        # Override the mock for a second collect (must handle percpu=True too)
        with patch(
            "agent.monitors.system_resource.psutil.cpu_percent",
            side_effect=lambda interval=None, percpu=False: (
                [99.9] * 8 if percpu else 99.9
            ),
        ):
            monitor._latest = monitor._collect()
        second = monitor.latest_metrics
        assert second["cpu"]["percent"] == 99.9


# ============================================================================
# _collect tests
# ============================================================================


class TestCollect:
    """Tests for the _collect() method."""

    def test_collect_returns_system_resource_metrics(self, basic_config):
        monitor = SystemResourceMonitor(basic_config)
        result = monitor._collect()
        assert isinstance(result, SystemResourceMetrics)

    def test_collect_sets_cpu_percent(self, basic_config, mock_psutil):
        monitor = SystemResourceMonitor(basic_config)
        result = monitor._collect()
        assert result.cpu_percent == 45.6
        mock_psutil.cpu_percent.assert_any_call(interval=0.1)

    def test_collect_sets_cpu_per_core(self, basic_config, mock_psutil):
        monitor = SystemResourceMonitor(basic_config)
        result = monitor._collect()
        assert isinstance(result.cpu_per_core, list)
        assert len(result.cpu_per_core) == 8
        assert result.cpu_per_core[0] == 23.4
        mock_psutil.cpu_percent.assert_any_call(interval=None, percpu=True)

    def test_collect_sets_cpu_count_logical(self, basic_config, mock_psutil):
        monitor = SystemResourceMonitor(basic_config)
        result = monitor._collect()
        assert result.cpu_count_logical == 8
        mock_psutil.cpu_count.assert_any_call(logical=True)

    def test_collect_sets_cpu_count_physical(self, basic_config, mock_psutil):
        monitor = SystemResourceMonitor(basic_config)
        result = monitor._collect()
        assert result.cpu_count_physical == 8
        mock_psutil.cpu_count.assert_any_call(logical=False)

    def test_collect_sets_memory_fields(self, basic_config, mock_psutil):
        monitor = SystemResourceMonitor(basic_config)
        result = monitor._collect()
        assert result.memory_total == 16_000_000_000
        assert result.memory_available == 8_000_000_000
        assert result.memory_used == 8_000_000_000
        assert result.memory_percent == 50.0
        mock_psutil.virtual_memory.assert_called_once()

    def test_collect_sets_swap_fields(self, basic_config, mock_psutil):
        monitor = SystemResourceMonitor(basic_config)
        result = monitor._collect()
        assert result.swap_total == 32_000_000_000
        assert result.swap_used == 1_000_000_000
        assert result.swap_percent == 3.1
        mock_psutil.swap_memory.assert_called_once()

    def test_collect_sets_disk_io(self, basic_config, mock_psutil):
        monitor = SystemResourceMonitor(basic_config)
        result = monitor._collect()
        assert result.disk_io_read_bytes == 1000
        assert result.disk_io_write_bytes == 2000
        mock_psutil.disk_io_counters.assert_called_once()

    def test_collect_sets_network_io(self, basic_config, mock_psutil):
        monitor = SystemResourceMonitor(basic_config)
        result = monitor._collect()
        assert result.net_bytes_sent == 500
        assert result.net_bytes_recv == 600
        mock_psutil.net_io_counters.assert_called_once()

    def test_collect_sets_network_connections(self, basic_config, mock_psutil):
        monitor = SystemResourceMonitor(basic_config)
        result = monitor._collect()
        assert result.net_connections == 2  # 2 mocked connections
        mock_psutil.net_connections.assert_called_once()

    def test_collect_calls_disk_partitions(self, basic_config, mock_psutil):
        monitor = SystemResourceMonitor(basic_config)
        monitor._collect()
        mock_psutil.disk_partitions.assert_called_once_with(all=False)

    def test_collect_disk_partitions_with_data(self, basic_config, mock_psutil):
        """Test disk partition collection with actual partition data."""
        # Create mock partition
        mock_partition = Mock()
        mock_partition.device = "/dev/sda1"
        mock_partition.mountpoint = "/"
        mock_partition.fstype = "ext4"

        mock_usage = Mock()
        mock_usage.total = 100_000_000_000
        mock_usage.used = 50_000_000_000
        mock_usage.free = 50_000_000_000
        mock_usage.percent = 50.0

        with patch(
            "agent.monitors.system_resource.psutil.disk_partitions",
            return_value=[mock_partition],
        ):
            with patch(
                "agent.monitors.system_resource.psutil.disk_usage",
                return_value=mock_usage,
            ):
                monitor = SystemResourceMonitor(basic_config)
                result = monitor._collect()

        assert len(result.disk_partitions) == 1
        p = result.disk_partitions[0]
        assert p["device"] == "/dev/sda1"
        assert p["mountpoint"] == "/"
        assert p["fstype"] == "ext4"
        assert p["total"] == 100_000_000_000
        assert p["used"] == 50_000_000_000
        assert p["free"] == 50_000_000_000
        assert p["percent"] == 50.0

    def test_collect_disk_partitions_permission_error(self):
        """When disk_usage raises PermissionError, partition gets zeroed fields."""
        mock_partition = Mock()
        mock_partition.device = "/dev/cdrom"
        mock_partition.mountpoint = "/media/cdrom"
        mock_partition.fstype = "iso9660"

        with patch(
            "agent.monitors.system_resource.psutil.disk_partitions",
            return_value=[mock_partition],
        ):
            with patch(
                "agent.monitors.system_resource.psutil.disk_usage",
                side_effect=PermissionError("Access denied"),
            ):
                config = MonitorConfig(enabled=True)
                monitor = SystemResourceMonitor(config)
                result = monitor._collect()

        assert len(result.disk_partitions) == 1
        p = result.disk_partitions[0]
        assert p["device"] == "/dev/cdrom"
        assert p["mountpoint"] == "/media/cdrom"
        assert p["fstype"] == "iso9660"
        assert p["total"] == 0
        assert p["used"] == 0
        assert p["free"] == 0
        assert p["percent"] == 0.0

    def test_collect_handles_disk_io_exception(self):
        """When disk_io_counters raises exception, fields stay 0."""
        with patch(
            "agent.monitors.system_resource.psutil.disk_io_counters",
            side_effect=OSError("No disk IO available"),
        ):
            config = MonitorConfig(enabled=True)
            monitor = SystemResourceMonitor(config)
            result = monitor._collect()
        assert result.disk_io_read_bytes == 0
        assert result.disk_io_write_bytes == 0

    def test_collect_handles_net_io_exception(self):
        """When net_io_counters raises exception, fields stay 0."""
        with patch(
            "agent.monitors.system_resource.psutil.net_io_counters",
            side_effect=OSError("No network available"),
        ):
            config = MonitorConfig(enabled=True)
            monitor = SystemResourceMonitor(config)
            result = monitor._collect()
        assert result.net_bytes_sent == 0
        assert result.net_bytes_recv == 0

    def test_collect_handles_net_connections_exception(self):
        """When net_connections raises exception, connections stays 0."""
        with patch(
            "agent.monitors.system_resource.psutil.net_connections",
            side_effect=OSError("Permission denied"),
        ):
            config = MonitorConfig(enabled=True)
            monitor = SystemResourceMonitor(config)
            result = monitor._collect()
        assert result.net_connections == 0

    def test_collect_handles_cpu_count_returns_none(self, basic_config):
        """When cpu_count returns None, fallback to 0."""
        with patch(
            "agent.monitors.system_resource.psutil.cpu_count",
            return_value=None,
        ):
            monitor = SystemResourceMonitor(basic_config)
            result = monitor._collect()
        assert result.cpu_count_logical == 0
        assert result.cpu_count_physical == 0

    def test_collect_handles_disk_io_counters_returns_none(self, basic_config):
        """When disk_io_counters returns None/falsy, fields stay default."""
        with patch(
            "agent.monitors.system_resource.psutil.disk_io_counters",
            return_value=None,
        ):
            monitor = SystemResourceMonitor(basic_config)
            result = monitor._collect()
        assert result.disk_io_read_bytes == 0
        assert result.disk_io_write_bytes == 0

    def test_collect_handles_net_io_counters_returns_none(self, basic_config):
        """When net_io_counters returns None/falsy, fields stay default."""
        with patch(
            "agent.monitors.system_resource.psutil.net_io_counters",
            return_value=None,
        ):
            monitor = SystemResourceMonitor(basic_config)
            result = monitor._collect()
        assert result.net_bytes_sent == 0
        assert result.net_bytes_recv == 0

    def test_collect_always_returns_fresh_instance(self, basic_config):
        """Each _collect() call returns a new instance."""
        monitor = SystemResourceMonitor(basic_config)
        r1 = monitor._collect()
        r2 = monitor._collect()
        assert r1 is not r2


# ============================================================================
# run() / stop() lifecycle tests
# ============================================================================


class TestRunStopLifecycle:
    """Tests for run() and stop() async lifecycle."""

    @pytest.mark.asyncio
    async def test_run_sets_running_true(self, basic_config):
        """After starting run(), _running should be True."""
        monitor = SystemResourceMonitor(basic_config)

        async def controlled_sleep(seconds):
            monitor._running = False

        with patch(
            "agent.monitors.system_resource.asyncio.sleep",
            side_effect=controlled_sleep,
        ):
            await monitor.run()

    @pytest.mark.asyncio
    async def test_run_already_running_returns_immediately(self, basic_config):
        """If _running is already True, run() returns immediately."""
        monitor = SystemResourceMonitor(basic_config)
        monitor._running = True

        # Patch asyncio.sleep to ensure it's NOT called
        with patch(
            "agent.monitors.system_resource.asyncio.sleep",
            new_callable=AsyncMock,
        ) as mock_sleep:
            await monitor.run()

        # Since _running is already True, the while loop body is skipped
        mock_sleep.assert_not_called()

    @pytest.mark.asyncio
    async def test_run_collects_and_calls_callback(self, basic_config):
        """Callback receives metrics dict on each poll cycle."""
        config = MonitorConfig(enabled=True, interval_seconds=0.1)
        monitor = SystemResourceMonitor(config)
        metrics_received = []

        def callback(metrics_dict):
            metrics_received.append(metrics_dict)

        monitor.set_callback(callback)

        iteration_count = 0

        async def controlled_sleep(seconds):
            nonlocal iteration_count
            iteration_count += 1
            if iteration_count >= 2:
                monitor._running = False

        with patch(
            "agent.monitors.system_resource.asyncio.sleep",
            side_effect=controlled_sleep,
        ):
            await monitor.run()

        assert len(metrics_received) >= 1
        assert "cpu" in metrics_received[0]
        assert "memory" in metrics_received[0]
        assert "swap" in metrics_received[0]
        assert "disk" in metrics_received[0]
        assert "network" in metrics_received[0]

    @pytest.mark.asyncio
    async def test_run_updates_latest_metrics(self, basic_config):
        """After a poll cycle, latest_metrics should return collected data."""
        config = MonitorConfig(enabled=True, interval_seconds=0.1)
        monitor = SystemResourceMonitor(config)

        iteration_count = 0

        async def controlled_sleep(seconds):
            nonlocal iteration_count
            iteration_count += 1
            if iteration_count >= 1:
                monitor._running = False

        with patch(
            "agent.monitors.system_resource.asyncio.sleep",
            side_effect=controlled_sleep,
        ):
            await monitor.run()

        assert monitor.latest_metrics is not None
        assert "cpu" in monitor.latest_metrics

    @pytest.mark.asyncio
    async def test_run_without_callback_does_not_crash(self, basic_config):
        """Run should work fine even without a callback registered."""
        config = MonitorConfig(enabled=True, interval_seconds=0.1)
        monitor = SystemResourceMonitor(config)

        iteration_count = 0

        async def controlled_sleep(seconds):
            nonlocal iteration_count
            iteration_count += 1
            if iteration_count >= 2:
                monitor._running = False

        with patch(
            "agent.monitors.system_resource.asyncio.sleep",
            side_effect=controlled_sleep,
        ):
            await monitor.run()

        # Should complete without error
        assert monitor.latest_metrics is not None

    @pytest.mark.asyncio
    async def test_stop_sets_running_false(self, basic_config):
        """stop() should set _running to False."""
        monitor = SystemResourceMonitor(basic_config)
        monitor._running = True
        await monitor.stop()
        assert monitor._running is False

    @pytest.mark.asyncio
    async def test_stop_cancels_task(self, basic_config):
        """stop() should cancel the stored task."""
        monitor = SystemResourceMonitor(basic_config)

        async def dummy_run():
            try:
                while True:
                    await asyncio.sleep(0.1)
            except asyncio.CancelledError:
                pass

        task = asyncio.create_task(dummy_run())
        monitor._task = task
        monitor._running = True

        await monitor.stop()

        assert task.done()
        assert task.cancelled()

    @pytest.mark.asyncio
    async def test_stop_handles_already_done_task(self, basic_config):
        """stop() should not crash if task is already done."""
        monitor = SystemResourceMonitor(basic_config)

        async def short_task():
            pass

        task = asyncio.create_task(short_task())
        await task  # Wait for completion
        monitor._task = task

        await monitor.stop()
        # Should complete without error

    @pytest.mark.asyncio
    async def test_stop_no_task(self, basic_config):
        """stop() should work even if no task was ever created."""
        monitor = SystemResourceMonitor(basic_config)
        monitor._running = True
        await monitor.stop()
        assert monitor._running is False

    @pytest.mark.asyncio
    async def test_run_logs_start_message(self, basic_config):
        """Verify run() logs a start message."""
        config = MonitorConfig(enabled=True, interval_seconds=5.0)
        monitor = SystemResourceMonitor(config)

        iteration_count = 0

        async def controlled_sleep(seconds):
            nonlocal iteration_count
            iteration_count += 1
            if iteration_count >= 1:
                monitor._running = False

        with patch(
            "agent.monitors.system_resource.asyncio.sleep",
            side_effect=controlled_sleep,
        ):
            with patch.object(
                logging.getLogger("agent.monitors.system_resource"), "info"
            ) as mock_info:
                await monitor.run()

        # Verify the start message was logged
        start_calls = [
            c for c in mock_info.call_args_list
            if "started" in str(c)
        ]
        assert len(start_calls) >= 1


# ============================================================================
# Callback invocation tests
# ============================================================================


class TestCallbackInvocation:
    """Tests for callback invocation during the polling loop."""

    @pytest.mark.asyncio
    async def test_callback_receives_to_dict_format(self, basic_config):
        """Callback receives metrics in to_dict() format."""
        config = MonitorConfig(enabled=True, interval_seconds=0.1)
        monitor = SystemResourceMonitor(config)
        received = []

        def cb(data):
            received.append(data)

        monitor.set_callback(cb)

        iteration_count = 0

        async def controlled_sleep(seconds):
            nonlocal iteration_count
            iteration_count += 1
            if iteration_count >= 1:
                monitor._running = False

        with patch(
            "agent.monitors.system_resource.asyncio.sleep",
            side_effect=controlled_sleep,
        ):
            await monitor.run()

        assert len(received) >= 1
        # Verify it's a dict with the expected structure
        assert isinstance(received[0], dict)
        assert set(received[0].keys()) == {"cpu", "memory", "swap", "disk", "network"}

    @pytest.mark.asyncio
    async def test_callback_called_multiple_times(self, basic_config):
        """Callback is called once per poll cycle."""
        config = MonitorConfig(enabled=True, interval_seconds=0.1)
        monitor = SystemResourceMonitor(config)
        call_count = 0

        def cb(data):
            nonlocal call_count
            call_count += 1

        monitor.set_callback(cb)

        # Stop after 3 iterations
        iteration_count = 0

        async def controlled_sleep(seconds):
            nonlocal iteration_count
            iteration_count += 1
            if iteration_count >= 3:
                monitor._running = False

        with patch(
            "agent.monitors.system_resource.asyncio.sleep",
            side_effect=controlled_sleep,
        ):
            await monitor.run()

        assert call_count == 3

    @pytest.mark.asyncio
    async def test_run_handles_callback_exception(self, basic_config):
        """If callback raises, the loop should continue (exception caught)."""
        config = MonitorConfig(enabled=True, interval_seconds=0.1)
        monitor = SystemResourceMonitor(config)
        call_count = 0

        def faulty_cb(data):
            nonlocal call_count
            call_count += 1
            raise RuntimeError("Callback error")

        monitor.set_callback(faulty_cb)

        iteration_count = 0

        async def controlled_sleep(seconds):
            nonlocal iteration_count
            iteration_count += 1
            if iteration_count >= 3:
                monitor._running = False

        with patch(
            "agent.monitors.system_resource.asyncio.sleep",
            side_effect=controlled_sleep,
        ):
            await monitor.run()

        # The callback was called 3 times even though it raised each time
        assert call_count == 3
        # latest_metrics should still be set
        assert monitor.latest_metrics is not None

    @pytest.mark.asyncio
    async def test_run_handles_collect_exception(self, basic_config):
        """If _collect raises, the loop should continue."""
        config = MonitorConfig(enabled=True, interval_seconds=0.1)
        monitor = SystemResourceMonitor(config)
        call_count = 0

        def cb(data):
            nonlocal call_count
            call_count += 1

        monitor.set_callback(cb)

        # First collect raises, subsequent succeed
        collect_calls = 0

        def faulty_collect():
            nonlocal collect_calls
            collect_calls += 1
            if collect_calls == 1:
                raise RuntimeError("Collection error")
            return SystemResourceMetrics(cpu_percent=99.0)

        iteration_count = 0

        async def controlled_sleep(seconds):
            nonlocal iteration_count
            iteration_count += 1
            if iteration_count >= 3:
                monitor._running = False

        with patch.object(
            monitor, "_collect", side_effect=faulty_collect
        ):
            with patch(
                "agent.monitors.system_resource.asyncio.sleep",
                side_effect=controlled_sleep,
            ):
                await monitor.run()

        # Iteration 1: collect fails, callback NOT called
        # Iteration 2: collect succeeds, callback called
        # Iteration 3: collect succeeds, callback called
        assert call_count == 2

        # latest should be from the last successful collect
        assert monitor.latest_metrics["cpu"]["percent"] == 99.0

    @pytest.mark.asyncio
    async def test_stop_logs_stop_message(self, basic_config):
        """Verify stop() logs a stop message."""
        monitor = SystemResourceMonitor(basic_config)
        monitor._running = True

        with patch.object(
            logging.getLogger("agent.monitors.system_resource"), "info"
        ) as mock_info:
            await monitor.stop()

        stop_calls = [
            c for c in mock_info.call_args_list
            if "stopped" in str(c).lower()
        ]
        assert len(stop_calls) >= 1
