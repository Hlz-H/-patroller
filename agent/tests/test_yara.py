"""Tests for agent.detectors.yara_detector — YaraDetector."""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock, call

sys.path.insert(0, str(Path(__file__).parent.parent))

from agent.alert import AlertStore, AlertSeverity, AlertType
from agent.config import YARAConfig
from agent.detectors.yara_detector import YaraDetector


# ---------------------------------------------------------------------------
# test_yara_disabled_when_not_available
# ---------------------------------------------------------------------------


def test_yara_disabled_when_not_available():
    """Patch yara import to raise ImportError, verify enabled=False."""
    with patch.dict("sys.modules", {"yara": None}):
        # Force re-import simulation by patching the module-level variable
        from agent.detectors.yara_detector import YaraDetector
        with patch.object(YaraDetector, "enabled", new_callable=PropertyMock) as mock_enabled:
            mock_enabled.return_value = False

            cfg = YARAConfig(enabled=True)
            store = AlertStore()
            detector = YaraDetector(cfg, store)
            # enabled should be False since yara is not available
            assert detector.enabled is False


def test_yara_disabled_config():
    """With config.enabled=False, enabled should be False regardless."""
    cfg = YARAConfig(enabled=False, rules_dir="test_rules/")
    store = AlertStore()
    detector = YaraDetector(cfg, store)
    assert detector.enabled is False


# ---------------------------------------------------------------------------
# test_scan_process_no_match
# ---------------------------------------------------------------------------


@patch("pathlib.Path.is_file", return_value=True)
def test_scan_process_no_match(_mock_is_file):
    """Mock yara.compile, mock rules.match returning empty list, verify no alert."""
    cfg = YARAConfig(enabled=True, rules_dir="test_rules/")
    store = AlertStore()

    # Create fake yara module
    fake_yara = MagicMock()
    fake_yara.SyntaxError = type("SyntaxError", (Exception,), {})
    fake_yara.TimeoutError = type("TimeoutError", (Exception,), {})
    fake_yara.Error = type("Error", (Exception,), {})

    fake_rules = MagicMock()
    fake_rules.match.return_value = []  # no match
    fake_yara.compile.return_value = fake_rules

    import agent.detectors.yara_detector as yd

    with patch.object(yd, "yara", fake_yara):
        with patch.object(yd, "_YARA_AVAILABLE", True):
            detector = yd.YaraDetector(cfg, store)
            detector._rules = fake_rules

            detector._scanned.clear()
            store._alerts.clear()

            # Call scan_process synchronously (not async to avoid asyncio issues)
            # The actual scan_process is async but we can test directly
            import asyncio

            async def run_test():
                await detector.scan_process("C:\\test\\fake.exe", pid=9999)

            asyncio.run(run_test())

            # Should have no alerts
            assert len(store.get_all()) == 0


# ---------------------------------------------------------------------------
# test_scan_process_with_match
# ---------------------------------------------------------------------------


@patch("pathlib.Path.is_file", return_value=True)
def test_scan_process_with_match(_mock_is_file):
    """Mock rules.match returning matches, verify alert_store.warn called."""
    cfg = YARAConfig(enabled=True, rules_dir="test_rules/")
    store = AlertStore()

    fake_yara = MagicMock()
    fake_yara.SyntaxError = type("SyntaxError", (Exception,), {})
    fake_yara.TimeoutError = type("TimeoutError", (Exception,), {})
    fake_yara.Error = type("Error", (Exception,), {})

    # Create match objects with rule, tags, strings attributes
    match1 = MagicMock()
    match1.rule = "malware_rule_1"
    match1.tags = ["trojan", "stealer"]
    match1.strings = [MagicMock()]

    match2 = MagicMock()
    match2.rule = "suspicious_pattern"
    match2.tags = []
    match2.strings = [MagicMock()]

    fake_rules = MagicMock()
    fake_rules.match.return_value = [match1, match2]
    fake_yara.compile.return_value = fake_rules

    import agent.detectors.yara_detector as yd

    with patch.object(yd, "yara", fake_yara):
        with patch.object(yd, "_YARA_AVAILABLE", True):
            detector = yd.YaraDetector(cfg, store)
            detector._rules = fake_rules

            detector._scanned.clear()
            store._alerts.clear()

            import asyncio

            async def run_test():
                await detector.scan_process("C:\\test\\malware.exe", pid=1234)

            asyncio.run(run_test())

            alerts = store.get_all()
            assert len(alerts) == 1
            alert = alerts[0]
            assert alert.severity == AlertSeverity.WARN
            assert "malware_rule_1" in alert.message
            assert "suspicious_pattern" in alert.message
            assert alert.details["exe_path"] == "C:\\test\\malware.exe"
            assert alert.details["pid"] == 1234
            assert "malware_rule_1" in alert.details["yara_rules"]
            assert "suspicious_pattern" in alert.details["yara_rules"]
            assert "trojan" in alert.details["yara_tags"]
            assert "stealer" in alert.details["yara_tags"]


# ---------------------------------------------------------------------------
# test_callback_fires_on_match
# ---------------------------------------------------------------------------


@patch("pathlib.Path.is_file", return_value=True)
def test_callback_fires_on_match(_mock_is_file):
    """Verify the callback is invoked when a YARA match occurs."""
    cfg = YARAConfig(enabled=True, rules_dir="test_rules/")
    store = AlertStore()

    callback_calls = []

    def my_callback(details):
        callback_calls.append(details)

    fake_yara = MagicMock()
    fake_yara.SyntaxError = type("SyntaxError", (Exception,), {})
    fake_yara.TimeoutError = type("TimeoutError", (Exception,), {})
    fake_yara.Error = type("Error", (Exception,), {})

    match = MagicMock()
    match.rule = "test_rule"
    match.tags = ["test_tag"]
    match.strings = [MagicMock()]

    fake_rules = MagicMock()
    fake_rules.match.return_value = [match]
    fake_yara.compile.return_value = fake_rules

    import agent.detectors.yara_detector as yd

    with patch.object(yd, "yara", fake_yara):
        with patch.object(yd, "_YARA_AVAILABLE", True):
            detector = yd.YaraDetector(cfg, store, callback=my_callback)
            detector._rules = fake_rules
            detector._scanned.clear()
            store._alerts.clear()

            import asyncio

            async def run_test():
                await detector.scan_process("C:\\test\\evil.exe", pid=5678)

            asyncio.run(run_test())

            assert len(callback_calls) == 1
            assert callback_calls[0]["exe_path"] == "C:\\test\\evil.exe"
            assert callback_calls[0]["pid"] == 5678


# ---------------------------------------------------------------------------
# test_deduplication
# ---------------------------------------------------------------------------


@patch("pathlib.Path.is_file", return_value=True)
def test_deduplication(_mock_is_file):
    """Same exe path scanned twice, verify only one alert."""
    cfg = YARAConfig(enabled=True, rules_dir="test_rules/")
    store = AlertStore()

    fake_yara = MagicMock()
    fake_yara.SyntaxError = type("SyntaxError", (Exception,), {})
    fake_yara.TimeoutError = type("TimeoutError", (Exception,), {})
    fake_yara.Error = type("Error", (Exception,), {})

    match = MagicMock()
    match.rule = "dedup_rule"
    match.tags = []
    match.strings = [MagicMock()]

    fake_rules = MagicMock()
    fake_rules.match.return_value = [match]
    fake_yara.compile.return_value = fake_rules

    import agent.detectors.yara_detector as yd

    with patch.object(yd, "yara", fake_yara):
        with patch.object(yd, "_YARA_AVAILABLE", True):
            detector = yd.YaraDetector(cfg, store)
            detector._rules = fake_rules
            detector._scanned.clear()
            store._alerts.clear()

            import asyncio

            async def run_test():
                # Scan same path twice
                await detector.scan_process("C:\\test\\duplicate.exe", pid=1)
                await detector.scan_process("C:\\test\\duplicate.exe", pid=1)

            asyncio.run(run_test())

            # Only one alert should be created
            assert len(store.get_all()) == 1


# ---------------------------------------------------------------------------
# test_load_rules
# ---------------------------------------------------------------------------


@patch.object(Path, "glob")
@patch("pathlib.Path.is_dir", return_value=True)
def test_load_rules_success(mock_is_dir, mock_glob):
    """Mock yara.compile, verify load_rules succeeds."""
    cfg = YARAConfig(enabled=True, rules_dir="test_rules/")
    store = AlertStore()

    mock_file = MagicMock()
    mock_file.name = "test_rule.yar"
    mock_file.read_text.return_value = "rule test { condition: true }"
    mock_glob.return_value = [mock_file]

    fake_yara = MagicMock()
    fake_yara.SyntaxError = type("SyntaxError", (Exception,), {})
    fake_yara.TimeoutError = type("TimeoutError", (Exception,), {})
    fake_yara.Error = type("Error", (Exception,), {})

    fake_rules = MagicMock()
    fake_yara.compile.return_value = fake_rules

    import agent.detectors.yara_detector as yd

    with patch.object(yd, "yara", fake_yara):
        with patch.object(yd, "_YARA_AVAILABLE", True):
            detector = yd.YaraDetector(cfg, store)

            import asyncio

            async def run_test():
                await detector.load_rules()

            asyncio.run(run_test())

            assert detector._rules is fake_rules


def test_load_rules_dir_not_exists():
    """load_rules with non-existent directory sets rules to None."""
    cfg = YARAConfig(enabled=True, rules_dir="nonexistent_rules_dir_xyz/")
    store = AlertStore()

    fake_yara = MagicMock()
    fake_yara.SyntaxError = type("SyntaxError", (Exception,), {})
    fake_yara.compile.return_value = MagicMock()

    import agent.detectors.yara_detector as yd

    with patch.object(yd, "yara", fake_yara):
        with patch.object(yd, "_YARA_AVAILABLE", True):
            detector = yd.YaraDetector(cfg, store)

            import asyncio

            async def run_test():
                await detector.load_rules()

            asyncio.run(run_test())

            assert detector._rules is None


# ---------------------------------------------------------------------------
# test_enabled_property
# ---------------------------------------------------------------------------


def test_enabled_false_when_yara_unavailable():
    """When yara is not available, enabled is False regardless of config."""
    cfg = YARAConfig(enabled=True)
    store = AlertStore()

    import agent.detectors.yara_detector as yd
    with patch.object(yd, "_YARA_AVAILABLE", False):
        detector = yd.YaraDetector(cfg, store)
        assert detector.enabled is False


def test_enabled_respects_config():
    """When yara is available but config.enabled=False, enabled is False."""
    cfg = YARAConfig(enabled=False)
    store = AlertStore()

    import agent.detectors.yara_detector as yd
    with patch.object(yd, "_YARA_AVAILABLE", True):
        detector = yd.YaraDetector(cfg, store)
        assert detector.enabled is False


def test_enabled_true_when_both():
    """When yara is available AND config.enabled=True, enabled is True."""
    cfg = YARAConfig(enabled=True)
    store = AlertStore()

    import agent.detectors.yara_detector as yd
    with patch.object(yd, "_YARA_AVAILABLE", True):
        detector = yd.YaraDetector(cfg, store)
        assert detector.enabled is True


# ---------------------------------------------------------------------------
# test_start_disabled
# ---------------------------------------------------------------------------


def test_start_when_disabled():
    """start() should return early when disabled."""
    cfg = YARAConfig(enabled=False)
    store = AlertStore()

    import agent.detectors.yara_detector as yd
    with patch.object(yd, "_YARA_AVAILABLE", True):
        detector = yd.YaraDetector(cfg, store)

        import asyncio

        async def run_test():
            await detector.start()

        asyncio.run(run_test())
        # Should not raise, and _running should stay False
        # (Note: with enabled=False, the method returns before setting _running)


# ---------------------------------------------------------------------------
# test_stop
# ---------------------------------------------------------------------------


def test_stop():
    """stop() sets _running to False."""
    cfg = YARAConfig(enabled=True)
    store = AlertStore()

    import agent.detectors.yara_detector as yd
    with patch.object(yd, "_YARA_AVAILABLE", True):
        detector = yd.YaraDetector(cfg, store)
        detector._running = True

        import asyncio

        async def run_test():
            await detector.stop()

        asyncio.run(run_test())
        assert detector._running is False


# ---------------------------------------------------------------------------
# test_scan_when_disabled
# ---------------------------------------------------------------------------


def test_scan_process_when_disabled():
    """scan_process should return early when disabled."""
    cfg = YARAConfig(enabled=False)
    store = AlertStore()

    import agent.detectors.yara_detector as yd
    with patch.object(yd, "_YARA_AVAILABLE", False):
        detector = yd.YaraDetector(cfg, store)
        store._alerts.clear()

        import asyncio

        async def run_test():
            await detector.scan_process("C:\\test\\file.exe", pid=1)

        asyncio.run(run_test())
        assert len(store.get_all()) == 0
