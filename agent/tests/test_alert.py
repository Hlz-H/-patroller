"""Tests for agent.alert — Alert dataclass and AlertStore."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from agent.alert import Alert, AlertStore, AlertSeverity, AlertType


# ---------------------------------------------------------------------------
# Alert dataclass tests
# ---------------------------------------------------------------------------


def test_alert_creation():
    """Create Alert with all fields, verify to_dict() output."""
    alert = Alert(
        alert_id="test-id-123",
        timestamp=1700000000.0,
        alert_type=AlertType.PROCESS,
        severity=AlertSeverity.WARN,
        message="Test alert message",
        details={"key1": "value1", "key2": 42},
    )
    d = alert.to_dict()
    assert d["alert_id"] == "test-id-123"
    assert d["timestamp"] == 1700000000.0
    assert d["type"] == "process"
    assert d["severity"] == "warn"
    assert d["message"] == "Test alert message"
    assert d["details"] == {"key1": "value1", "key2": 42}


def test_alert_default_fields():
    """Create Alert with minimal args, verify defaults are set."""
    alert = Alert(message="minimal")
    assert alert.alert_id  # should be a non-empty uuid string
    assert len(alert.alert_id) > 0
    assert isinstance(alert.timestamp, float)
    assert alert.timestamp > 0
    assert alert.alert_type == AlertType.SYSTEM
    assert alert.severity == AlertSeverity.INFO
    assert alert.message == "minimal"
    assert alert.details == {}


def test_alert_severity_enum_values():
    """Verify AlertSeverity enum string values."""
    assert AlertSeverity.INFO.value == "info"
    assert AlertSeverity.WARN.value == "warn"
    assert AlertSeverity.CRITICAL.value == "critical"


def test_alert_type_enum_values():
    """Verify AlertType enum string values."""
    assert AlertType.PROCESS.value == "process"
    assert AlertType.USB.value == "usb"
    assert AlertType.SYSTEM.value == "system"


def test_alert_to_dict_uses_enum_values():
    """Verify to_dict() serializes enum fields as their string values."""
    alert = Alert(
        alert_type=AlertType.USB,
        severity=AlertSeverity.CRITICAL,
        message="usb critical",
    )
    d = alert.to_dict()
    assert d["type"] == "usb"
    assert d["severity"] == "critical"


# ---------------------------------------------------------------------------
# AlertStore tests
# ---------------------------------------------------------------------------


def test_alert_store_add_get():
    """Store alerts and retrieve them."""
    store = AlertStore()
    a1 = Alert(message="first")
    a2 = Alert(message="second")

    store.add(a1)
    store.add(a2)

    all_alerts = store.get_all()
    assert len(all_alerts) == 2
    assert all_alerts[0].message == "first"
    assert all_alerts[1].message == "second"


def test_alert_store_max_size():
    """Add 1001 alerts, verify only 1000 stored (oldest trimmed)."""
    store = AlertStore()
    for i in range(1001):
        store.add(Alert(message=f"alert-{i}"))

    all_alerts = store.get_all()
    assert len(all_alerts) == 1000
    # Oldest (index 0) should have been trimmed
    assert all_alerts[0].message == "alert-1"
    assert all_alerts[-1].message == "alert-1000"


def test_alert_store_get_recent():
    """Add 100 alerts, get_recent(10) returns last 10."""
    store = AlertStore()
    for i in range(100):
        store.add(Alert(message=f"alert-{i}"))

    recent = store.get_recent(10)
    assert len(recent) == 10
    assert recent[0].message == "alert-90"
    assert recent[-1].message == "alert-99"


def test_alert_store_get_recent_default():
    """get_recent() with no arg returns at most 50."""
    store = AlertStore()
    for i in range(10):
        store.add(Alert(message=f"alert-{i}"))

    recent = store.get_recent()
    assert len(recent) == 10  # fewer than default 50
    assert recent[0].message == "alert-0"


def test_alert_store_get_by_severity():
    """Filter alerts by severity."""
    store = AlertStore()
    store.add(Alert(message="info1", severity=AlertSeverity.INFO))
    store.add(Alert(message="warn1", severity=AlertSeverity.WARN))
    store.add(Alert(message="warn2", severity=AlertSeverity.WARN))
    store.add(Alert(message="crit1", severity=AlertSeverity.CRITICAL))

    warn_alerts = store.get_by_severity(AlertSeverity.WARN)
    assert len(warn_alerts) == 2
    assert all(a.severity == AlertSeverity.WARN for a in warn_alerts)

    info_alerts = store.get_by_severity(AlertSeverity.INFO)
    assert len(info_alerts) == 1
    assert info_alerts[0].message == "info1"

    crit_alerts = store.get_by_severity(AlertSeverity.CRITICAL)
    assert len(crit_alerts) == 1


def test_alert_store_subscribe_callback():
    """Subscribe callback fires on add."""
    store = AlertStore()
    received = []

    def my_callback(alert):
        received.append(alert.message)

    store.subscribe(my_callback)
    store.add(Alert(message="hello"))
    assert received == ["hello"]


def test_alert_store_unsubscribe():
    """Unsubscribe stops callback from firing."""
    store = AlertStore()
    received = []

    def my_callback(alert):
        received.append(alert.message)

    store.subscribe(my_callback)
    store.add(Alert(message="first"))
    assert received == ["first"]

    store.unsubscribe(my_callback)
    store.add(Alert(message="second"))
    assert received == ["first"]  # unchanged


def test_alert_store_convenience_methods():
    """info/warn/critical create alerts with correct severity."""
    store = AlertStore()

    a1 = store.info(AlertType.SYSTEM, "info msg")
    assert a1.severity == AlertSeverity.INFO
    assert a1.message == "info msg"

    a2 = store.warn(AlertType.PROCESS, "warn msg", pid=1234)
    assert a2.severity == AlertSeverity.WARN
    assert a2.details == {"pid": 1234}

    a3 = store.critical(AlertType.USB, "crit msg", device="sandisk")
    assert a3.severity == AlertSeverity.CRITICAL

    all_alerts = store.get_all()
    assert len(all_alerts) == 3


def test_convenience_methods_with_group_key():
    """info/warn/critical accept and propagate group_key."""
    store = AlertStore()
    a1 = store.info(AlertType.SYSTEM, "info", group_key="sys:info")
    a2 = store.warn(AlertType.PROCESS, "warn", group_key="proc:warn")
    a3 = store.critical(AlertType.USB, "crit", group_key="usb:crit")
    assert a1.group_key == "sys:info"
    assert a2.group_key == "proc:warn"
    assert a3.group_key == "usb:crit"
    assert len(store.get_all()) == 3


def test_alert_store_get_all_returns_copy():
    """get_all() returns a copy, not the internal list."""
    store = AlertStore()
    store.add(Alert(message="a"))
    alerts = store.get_all()
    alerts.append(Alert(message="b"))
    # Internal list should be unchanged
    assert len(store.get_all()) == 1


# ===================================================================
# Alert aggregation / dedup / suppression tests
# ===================================================================


class TestAlertCount:
    def test_count_default(self):
        a = Alert(message="x")
        assert a.count == 1
        assert a.to_dict()["count"] == 1

    def test_count_custom(self):
        a = Alert(message="x", count=5)
        assert a.count == 5
        assert a.to_dict()["count"] == 5

    def test_group_key_default(self):
        a = Alert(message="x")
        assert a.group_key == ""


class TestSuppression:
    def test_basic_suppression(self):
        store = AlertStore()
        store.suppress("usb", 300)
        alert = Alert(alert_type=AlertType.USB, message="USB inserted")
        assert store.add_with_policy(alert) is None
        assert len(store.get_all()) == 0

    def test_suppression_expires(self):
        store = AlertStore()
        store.suppress("usb", 0.01)
        import time
        time.sleep(0.02)
        alert = Alert(alert_type=AlertType.USB, message="USB inserted")
        assert store.add_with_policy(alert) is not None
        assert len(store.get_all()) == 1

    def test_unsuppress(self):
        store = AlertStore()
        store.suppress("usb", 300)
        store.unsuppress("usb")
        alert = Alert(alert_type=AlertType.USB, message="USB")
        assert store.add_with_policy(alert) is not None

    def test_non_matching_not_suppressed(self):
        store = AlertStore()
        store.suppress("usb", 300)
        alert = Alert(alert_type=AlertType.PROCESS, message="Process started")
        assert store.add_with_policy(alert) is not None

    def test_get_suppressed(self):
        store = AlertStore()
        store.suppress("a", 300)
        store.suppress("b", 600)
        d = store.get_suppressed()
        assert "a" in d
        assert "b" in d

    def test_suppressed_expired_not_listed(self):
        store = AlertStore()
        store.suppress("x", 0.01)
        import time
        time.sleep(0.02)
        d = store.get_suppressed()
        assert "x" not in d


class TestDedup:
    def test_exact_duplicate_dropped(self):
        store = AlertStore(dedup_window=60)
        a1 = Alert(alert_type=AlertType.SYSTEM, message="same")
        a2 = Alert(alert_type=AlertType.SYSTEM, message="same")
        assert store.add_with_policy(a1) is not None
        assert store.add_with_policy(a2) is None
        assert len(store.get_all()) == 1

    def test_different_message_not_deduped(self):
        store = AlertStore(dedup_window=60)
        store.add_with_policy(Alert(alert_type=AlertType.SYSTEM, message="first"))
        store.add_with_policy(Alert(alert_type=AlertType.SYSTEM, message="second"))
        assert len(store.get_all()) == 2

    def test_different_type_not_deduped(self):
        store = AlertStore(dedup_window=60)
        store.add_with_policy(Alert(alert_type=AlertType.PROCESS, message="same"))
        store.add_with_policy(Alert(alert_type=AlertType.USB, message="same"))
        assert len(store.get_all()) == 2

    def test_outside_window_not_deduped(self):
        store = AlertStore(dedup_window=0.01)
        store.add_with_policy(Alert(alert_type=AlertType.SYSTEM, message="brief"))
        import time
        time.sleep(0.02)
        store.add_with_policy(Alert(alert_type=AlertType.SYSTEM, message="brief"))
        assert len(store.get_all()) == 2


class TestAggregation:
    def test_same_group_key_merged(self):
        store = AlertStore(dedup_window=0, aggregation_window=60)
        a1 = Alert(alert_type=AlertType.PROCESS, message="Malware detected",
                    group_key="yara:rule1", details={"pids": [100]})
        a2 = Alert(alert_type=AlertType.PROCESS, message="Malware detected",
                    group_key="yara:rule1", details={"pids": [200]})
        r1 = store.add_with_policy(a1)
        r2 = store.add_with_policy(a2)
        assert r1 is not None
        assert r2 is not None
        # Second call returns the aggregated (original) alert
        assert r2 is a1
        assert a1.count == 2
        assert len(store.get_all()) == 1

    def test_aggregation_outside_window(self):
        store = AlertStore(dedup_window=0, aggregation_window=0.01)
        store.add_with_policy(Alert(alert_type=AlertType.PROCESS, message="detected",
                                     group_key="yara:rule1"))
        import time
        time.sleep(0.02)
        store.add_with_policy(Alert(alert_type=AlertType.PROCESS, message="detected",
                                     group_key="yara:rule1"))
        assert len(store.get_all()) == 2

    def test_no_group_key_no_aggregation(self):
        store = AlertStore(aggregation_window=60)
        store.add_with_policy(Alert(alert_type=AlertType.PROCESS, message="first"))
        store.add_with_policy(Alert(alert_type=AlertType.PROCESS, message="second"))
        assert len(store.get_all()) == 2

    def test_zero_window_disables_aggregation(self):
        store = AlertStore(aggregation_window=0)
        store.add_with_policy(Alert(alert_type=AlertType.PROCESS, message="first",
                                     group_key="yara:rule1"))
        store.add_with_policy(Alert(alert_type=AlertType.PROCESS, message="second",
                                     group_key="yara:rule1"))
        assert len(store.get_all()) == 2  # no aggregation, different msgs → no dedup

    def test_aggregation_detail_merge(self):
        """List-type details from multiple alerts are merged."""
        store = AlertStore(dedup_window=0, aggregation_window=60)
        a1 = Alert(alert_type=AlertType.PROCESS, message="detected",
                    group_key="yara:rule1", details={"pids": [100], "paths": ["a.exe"]})
        a2 = Alert(alert_type=AlertType.PROCESS, message="detected",
                    group_key="yara:rule1", details={"pids": [200], "paths": ["b.exe"]})
        store.add_with_policy(a1)
        store.add_with_policy(a2)
        assert a1.count == 2
        assert sorted(a1.details["pids"]) == [100, 200]
        assert sorted(a1.details["paths"]) == ["a.exe", "b.exe"]


class TestPolicyCombined:
    def test_suppress_before_dedup(self):
        """Suppression checked first — suppressed alerts don't register fingerprints."""
        store = AlertStore(dedup_window=60)
        store.suppress("usb", 0.01)
        alert = Alert(alert_type=AlertType.USB, message="USB inserted")
        store.add_with_policy(alert)  # suppressed
        import time
        time.sleep(0.02)
        store.add_with_policy(alert)  # suppression expired → should go through
        assert len(store.get_all()) == 1

    def test_dedup_before_aggregation(self):
        """Dedup check happens before aggregation check."""
        store = AlertStore(dedup_window=60, aggregation_window=60)
        a1 = Alert(alert_type=AlertType.PROCESS, message="Same", group_key="grp1")
        a2 = Alert(alert_type=AlertType.PROCESS, message="Same", group_key="grp1")
        store.add_with_policy(a1)
        store.add_with_policy(a2)  # dedup catches it → None
        assert len(store.get_all()) == 1
        assert store.get_all()[0].count == 1  # not aggregated
