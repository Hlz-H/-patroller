"""Tests for agent.detectors.llm_analyzer — LLMAnalyzer."""

import asyncio
import json
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock, AsyncMock

sys.path.insert(0, str(Path(__file__).parent.parent))

from agent.alert import Alert, AlertStore, AlertSeverity, AlertType
from agent.config import LLMConfig
from agent.detectors.llm_analyzer import LLMAnalyzer


# ---------------------------------------------------------------------------
# TestEnabled
# ---------------------------------------------------------------------------


class TestEnabled:
    def test_enabled_true(self):
        analyzer = LLMAnalyzer(LLMConfig(enabled=True), AlertStore())
        assert analyzer.enabled is True

    def test_enabled_false(self):
        analyzer = LLMAnalyzer(LLMConfig(enabled=False), AlertStore())
        assert analyzer.enabled is False


# ---------------------------------------------------------------------------
# TestOnAlert
# ---------------------------------------------------------------------------


class TestOnAlert:
    def setup_method(self):
        self.config = LLMConfig(enabled=True, batch_size=50)
        self.store = AlertStore()
        self.analyzer = LLMAnalyzer(self.config, self.store)

    def test_critical_alert_triggers_immediate_analysis(self):
        """Critical severity → _analyze_batch called, not _buffer_alert."""
        async def _test():
            alert = Alert(severity=AlertSeverity.CRITICAL, message="critical")
            captured_coros = []

            def capture_task(coro):
                captured_coros.append(coro)

            ba = AsyncMock()
            with patch.object(self.analyzer, "_analyze_batch", AsyncMock()) as ab:
                with patch.object(self.analyzer, "_buffer_alert", ba):
                    with patch("asyncio.create_task", side_effect=capture_task):
                        self.analyzer.on_alert(alert)

                    for coro in captured_coros:
                        await coro

            ab.assert_called_once()
            assert ab.call_args[0][0][0].message == "critical"
            ba.assert_not_called()

        asyncio.run(_test())

    def test_warn_alert_buffered_not_analyzed(self):
        """WARN severity → buffered, no immediate analysis."""
        async def _test():
            alert = Alert(severity=AlertSeverity.WARN, message="warn")
            with patch.object(self.analyzer, "_analyze_batch", AsyncMock()) as ab:
                with patch.object(self.analyzer, "_buffer_alert", AsyncMock()) as ba:
                    self.analyzer.on_alert(alert)
                    await asyncio.sleep(0.02)
                    ab.assert_not_called()
                    ba.assert_called_once_with(alert)

        asyncio.run(_test())

    def test_info_alert_buffered_not_analyzed(self):
        """INFO severity → buffered, no immediate analysis."""
        async def _test():
            alert = Alert(severity=AlertSeverity.INFO, message="info")
            with patch.object(self.analyzer, "_analyze_batch", AsyncMock()) as ab:
                with patch.object(self.analyzer, "_buffer_alert", AsyncMock()) as ba:
                    self.analyzer.on_alert(alert)
                    await asyncio.sleep(0.02)
                    ab.assert_not_called()
                    ba.assert_called_once()

        asyncio.run(_test())

    def test_lowercase_critical_also_triggers_analysis(self):
        """Severity string 'critical' (lowercase from enum) still triggers."""
        async def _test():
            alert = Alert(severity=AlertSeverity.CRITICAL, message="low crit")
            captured_coros = []

            def capture_task(coro):
                captured_coros.append(coro)

            with patch.object(self.analyzer, "_analyze_batch", AsyncMock()) as ab:
                with patch("asyncio.create_task", side_effect=capture_task):
                    self.analyzer.on_alert(alert)

                for coro in captured_coros:
                    await coro

            ab.assert_called_once()

        asyncio.run(_test())


# ---------------------------------------------------------------------------
# TestStartStop
# ---------------------------------------------------------------------------


class TestStartStop:
    def test_start_when_disabled_returns_early(self):
        async def _test():
            analyzer = LLMAnalyzer(LLMConfig(enabled=False), AlertStore())
            await analyzer.start()
            assert analyzer._running is False

        asyncio.run(_test())

    def test_start_sets_running_and_enters_loop(self):
        """CancelledError breaks loop; _running stays True."""
        async def _test():
            analyzer = LLMAnalyzer(LLMConfig(enabled=True), AlertStore())
            with patch.object(analyzer, "_flush_and_analyze", AsyncMock()):
                with patch("asyncio.wait_for", side_effect=asyncio.CancelledError()):
                    await analyzer.start()
            assert analyzer._running is True

        asyncio.run(_test())

    def test_stop_clears_running_and_sets_event(self):
        async def _test():
            analyzer = LLMAnalyzer(LLMConfig(enabled=True), AlertStore())
            analyzer._running = True
            await analyzer.stop()
            assert analyzer._running is False

        asyncio.run(_test())

    def test_stop_sets_buffer_event(self):
        """stop() sets _buffer_event so a waiting loop can exit."""
        async def _test():
            analyzer = LLMAnalyzer(LLMConfig(enabled=True), AlertStore())
            analyzer._running = True
            with patch.object(analyzer._buffer_event, "set") as mock_set:
                await analyzer.stop()
            mock_set.assert_called_once()

        asyncio.run(_test())


# ---------------------------------------------------------------------------
# TestFlushAndAnalyze
# ---------------------------------------------------------------------------


class TestFlushAndAnalyze:
    def setup_method(self):
        self.config = LLMConfig(enabled=True)
        self.analyzer = LLMAnalyzer(self.config, AlertStore())

    def test_empty_buffer_noop(self):
        async def _test():
            with patch.object(self.analyzer, "_analyze_batch", AsyncMock()) as ab:
                await self.analyzer._flush_and_analyze()
                ab.assert_not_called()

        asyncio.run(_test())

    def test_buffer_drained_and_analyzed(self):
        async def _test():
            alert = Alert(severity=AlertSeverity.WARN, message="flush test")
            self.analyzer._buffer = [alert]
            with patch.object(self.analyzer, "_analyze_batch", AsyncMock()) as ab:
                await self.analyzer._flush_and_analyze()
                ab.assert_called_once()
                batch = ab.call_args[0][0]
                assert len(batch) == 1
                assert batch[0].message == "flush test"
                assert self.analyzer._buffer == []

        asyncio.run(_test())

    def test_buffer_event_cleared(self):
        async def _test():
            self.analyzer._buffer_event.set()
            with patch.object(self.analyzer, "_analyze_batch", AsyncMock()):
                await self.analyzer._flush_and_analyze()
            assert not self.analyzer._buffer_event.is_set()

        asyncio.run(_test())


# ---------------------------------------------------------------------------
# TestAnalyzeBatch
# ---------------------------------------------------------------------------


class TestAnalyzeBatch:
    def setup_method(self):
        self.config = LLMConfig(
            enabled=True, endpoint="http://localhost:11434", model="llama3"
        )
        self.analyzer = LLMAnalyzer(self.config, AlertStore())

    def test_empty_alerts_noop(self):
        async def _test():
            with patch.object(self.analyzer, "_http_post", AsyncMock()) as post:
                await self.analyzer._analyze_batch([])
                post.assert_not_called()

        asyncio.run(_test())

    def test_prompt_contains_alert_data(self):
        """Verify HTTP payload includes alert fields in the prompt."""
        async def _test():
            alert = Alert(
                severity=AlertSeverity.CRITICAL,
                alert_type=AlertType.PROCESS,
                message="suspicious process",
                details={"pid": 9999, "path": r"C:\evil.exe"},
            )
            resp = json.dumps({
                "response": json.dumps([
                    {"severity": "high", "summary": "bad", "recommended_action": "block"}
                ])
            })
            with patch.object(self.analyzer, "_http_post", AsyncMock(return_value=resp)) as post:
                await self.analyzer._analyze_batch([alert])

            post.assert_called_once()
            url = post.call_args[0][0]
            payload = post.call_args[0][1]
            assert url.endswith("/api/generate")
            assert payload["model"] == "llama3"
            assert payload["stream"] is False
            assert "suspicious process" in payload["prompt"]
            assert "CRITICAL" in payload["prompt"] or "critical" in payload["prompt"].lower()
            assert "9999" in payload["prompt"]

        asyncio.run(_test())

    def test_http_failure_silent(self):
        """Connection error → caught, does not propagate."""
        async def _test():
            alert = Alert(severity=AlertSeverity.WARN, message="will fail")
            with patch.object(
                self.analyzer, "_http_post",
                AsyncMock(side_effect=ConnectionRefusedError("no ollama"))
            ):
                await self.analyzer._analyze_batch([alert])
            # No exception raised

        asyncio.run(_test())

    def test_timeout_silent(self):
        """Timeout → caught, does not propagate."""
        async def _test():
            alert = Alert(severity=AlertSeverity.CRITICAL, message="timeout")
            with patch.object(
                self.analyzer, "_http_post",
                AsyncMock(side_effect=asyncio.TimeoutError())
            ):
                await self.analyzer._analyze_batch([alert])

        asyncio.run(_test())

    def test_response_without_response_key(self):
        """ollama response missing 'response' key → uses raw text as fallback."""
        async def _test():
            alert = Alert(severity=AlertSeverity.WARN, message="x")
            raw = json.dumps([{"severity": "low", "summary": "ok"}])
            with patch.object(self.analyzer, "_http_post", AsyncMock(return_value=raw)):
                await self.analyzer._analyze_batch([alert])

        asyncio.run(_test())


# ---------------------------------------------------------------------------
# TestHttpPost
# ---------------------------------------------------------------------------


class TestHttpPost:
    def setup_method(self):
        self.analyzer = LLMAnalyzer(
            LLMConfig(enabled=True, endpoint="http://ollama:11434"), AlertStore()
        )

    def test_httpx_path(self):
        async def _test():
            import agent.detectors.llm_analyzer as la

            mock_client = AsyncMock()
            mock_resp = MagicMock()
            mock_resp.raise_for_status = MagicMock()
            mock_resp.text = '{"ok": true}'
            mock_client.post.return_value = mock_resp
            self.analyzer._client = mock_client

            with patch.object(la, "_HTTPX_AVAILABLE", True):
                result = await self.analyzer._http_post("http://x/api", {"k": "v"})

            assert result == '{"ok": true}'
            mock_client.post.assert_called_once_with("http://x/api", json={"k": "v"})
            mock_resp.raise_for_status.assert_called_once()

        asyncio.run(_test())

    def test_aiohttp_fallback(self):
        async def _test():
            import agent.detectors.llm_analyzer as la

            fake_aiohttp = MagicMock()
            fake_aiohttp.ClientTimeout = MagicMock(return_value=30)

            mock_resp = AsyncMock()
            mock_resp.raise_for_status = MagicMock()
            mock_resp.text = AsyncMock(return_value='{"fallback": true}')

            # session.post() returns a sync context manager, not a coroutine
            post_ctx_mgr = AsyncMock()
            post_ctx_mgr.__aenter__.return_value = mock_resp

            mock_session = AsyncMock()
            mock_session.__aenter__.return_value = mock_session
            mock_session.post = MagicMock(return_value=post_ctx_mgr)
            fake_aiohttp.ClientSession = MagicMock(return_value=mock_session)

            with patch.dict("sys.modules", {"aiohttp": fake_aiohttp}):
                with patch.object(la, "_HTTPX_AVAILABLE", False):
                    result = await self.analyzer._http_post("http://y/api", {"v": 1})

            assert result == '{"fallback": true}'

        asyncio.run(_test())


# ---------------------------------------------------------------------------
# TestParseJsonResponse
# ---------------------------------------------------------------------------


class TestParseJsonResponse:
    def test_direct_json_list(self):
        result = LLMAnalyzer._parse_json_response('[{"a": 1}, {"b": 2}]')
        assert result == [{"a": 1}, {"b": 2}]

    def test_direct_json_dict(self):
        result = LLMAnalyzer._parse_json_response('{"severity": "low"}')
        assert result == [{"severity": "low"}]

    def test_markdown_code_block(self):
        raw = '```json\n[{"severity": "high"}]\n```'
        result = LLMAnalyzer._parse_json_response(raw)
        assert result == [{"severity": "high"}]

    def test_dict_with_list_values(self):
        raw = '{"results": [{"severity": "medium"}]}'
        result = LLMAnalyzer._parse_json_response(raw)
        assert result == [{"severity": "medium"}]

    def test_malformed_text_returns_none(self):
        assert LLMAnalyzer._parse_json_response("random non-JSON") is None

    def test_empty_string_returns_none(self):
        assert LLMAnalyzer._parse_json_response("") is None

    def test_bare_json_object_with_array_value(self):
        raw = '{"analysis": [{"x": 1}, {"y": 2}]}'
        result = LLMAnalyzer._parse_json_response(raw)
        assert result == [{"x": 1}, {"y": 2}]

    def test_nested_markdown_code_block(self):
        raw = 'Sure! Here is the analysis:\n\n```json\n[\n  {"severity": "critical"}\n]\n```\n'
        result = LLMAnalyzer._parse_json_response(raw)
        assert result == [{"severity": "critical"}]
