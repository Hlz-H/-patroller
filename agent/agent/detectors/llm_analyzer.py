"""LLM-based alert analysis and enrichment using local ollama.

Buffers incoming alerts and periodically sends them in batches to an ollama
instance for contextual analysis. Critical alerts are analyzed immediately.
Uses raw HTTP (httpx / aiohttp) – no ollama Python package dependency.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from agent.config import LLMConfig
    from agent.alert import Alert, AlertStore

logger = logging.getLogger(__name__)

# Optional httpx import – fall back to aiohttp if not available
try:
    import httpx

    _HTTPX_AVAILABLE = True
except ImportError:
    _HTTPX_AVAILABLE = False
    logger.info("httpx not installed – will use aiohttp for LLM HTTP requests")

_PROMPT_TEMPLATE = """You are a security analyst. Analyze these alerts from a Windows security tool:

{alert_text}

Return a JSON array with each alert analyzed:
[{{"severity": "critical/high/medium/low", "summary": "...", "recommended_action": "..."}}]"""


class LLMAnalyzer:
    """Batches alerts and sends them to ollama for enrichment."""

    def __init__(self, config: LLMConfig, alert_store: AlertStore) -> None:
        self._config = config
        self._alert_store = alert_store
        self._running = False

        # Thread-safe buffer
        self._buffer: list[Alert] = []
        self._buffer_lock = asyncio.Lock()
        self._buffer_event = asyncio.Event()

        # HTTP client (created lazily)
        self._client: httpx.AsyncClient | None = None

        # Subscribe to new alerts
        alert_store.subscribe(self.on_alert)

    @property
    def enabled(self) -> bool:
        return self._config.enabled

    def on_alert(self, alert: Alert) -> None:
        """Callback invoked by AlertStore when a new alert is raised."""
        try:
            if hasattr(alert, "severity"):
                sev = alert.severity
                severity_str = (sev.value if hasattr(sev, "value") else str(sev)).upper()
            else:
                severity_str = ""
            if severity_str == "CRITICAL":
                # Analyze immediately (real-time) – fire-and-forget
                asyncio.create_task(self._analyze_batch([alert]))
            else:
                asyncio.create_task(self._buffer_alert(alert))
        except Exception:
            logger.exception("LLMAnalyzer on_alert error")

    async def _buffer_alert(self, alert: Alert) -> None:
        async with self._buffer_lock:
            self._buffer.append(alert)
        if len(self._buffer) >= self._config.batch_size:
            self._buffer_event.set()

    async def start(self) -> None:
        if not self.enabled:
            logger.info("LLMAnalyzer disabled – skipping run")
            return

        self._running = True
        logger.info(
            "LLMAnalyzer running (batch_interval=%dm, batch_size=%d, endpoint=%s, model=%s)",
            self._config.batch_interval_minutes,
            self._config.batch_size,
            self._config.endpoint,
            self._config.model,
        )

        batch_interval = self._config.batch_interval_minutes * 60

        while self._running:
            try:
                try:
                    await asyncio.wait_for(
                        self._buffer_event.wait(),
                        timeout=batch_interval,
                    )
                except asyncio.TimeoutError:
                    pass

                await self._flush_and_analyze()
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("LLMAnalyzer run loop error")

        await self._flush_and_analyze()

    async def stop(self) -> None:
        self._running = False
        self._buffer_event.set()

    async def _flush_and_analyze(self) -> None:
        async with self._buffer_lock:
            if not self._buffer:
                self._buffer_event.clear()
                return
            batch: list[Alert] = list(self._buffer)
            self._buffer.clear()
            self._buffer_event.clear()

        await self._analyze_batch(batch)

    async def _analyze_batch(self, alerts: list[Alert]) -> None:
        if not alerts:
            return

        alert_lines: list[str] = []
        for i, alert in enumerate(alerts):
            ts = getattr(alert, "timestamp", "N/A")
            severity = getattr(alert, "severity", "N/A")
            alert_type = getattr(alert, "alert_type", "SYSTEM")
            message = getattr(alert, "message", str(alert))
            details = getattr(alert, "details", {})
            details_str = json.dumps(details, default=str) if details else "{}"

            alert_lines.append(
                f"[{i}] [{alert_type}] [{severity}] {ts}\n"
                f"    Message: {message}\n"
                f"    Details: {details_str}"
            )
        alert_text = "\n\n".join(alert_lines)

        prompt = _PROMPT_TEMPLATE.format(alert_text=alert_text)

        url = f"{self._config.endpoint.rstrip('/')}/api/generate"
        payload = {
            "model": self._config.model,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0.1},
        }

        try:
            response_text = await self._http_post(url, payload)
        except Exception:
            logger.exception("LLMAnalyzer HTTP request failed – is ollama running?")
            return

        # Parse the response
        try:
            data = json.loads(response_text)
            if isinstance(data, dict):
                raw_response = data.get("response", response_text)
            else:
                raw_response = response_text
        except json.JSONDecodeError:
            raw_response = response_text

        analyses = self._parse_json_response(raw_response)

        if analyses:
            for i, analysis in enumerate(analyses):
                enriched = analysis if isinstance(analysis, dict) else {}
                severity = enriched.get("severity", "unknown")
                summary = enriched.get("summary", "N/A")
                action = enriched.get("recommended_action", "N/A")
                logger.info(
                    "LLM analysis [%d] severity=%s summary=%s action=%s",
                    i, severity, summary[:80], action[:80],
                )

    async def _http_post(self, url: str, payload: dict) -> str:
        if _HTTPX_AVAILABLE:
            if self._client is None:
                self._client = httpx.AsyncClient(timeout=30.0)
            resp = await self._client.post(url, json=payload)
            resp.raise_for_status()
            return resp.text
        else:
            import aiohttp

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url, json=payload, timeout=aiohttp.ClientTimeout(total=30)
                ) as resp:
                    resp.raise_for_status()
                    return await resp.text()

    @staticmethod
    def _parse_json_response(raw: str) -> list[dict] | None:
        try:
            result = json.loads(raw)
            if isinstance(result, list):
                return result
            if isinstance(result, dict):
                for v in result.values():
                    if isinstance(v, list):
                        return v
                return [result]
        except json.JSONDecodeError:
            pass

        import re

        match = re.search(r"\[.*\]", raw, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                pass

        logger.debug("Could not parse LLM response as JSON: %s", raw[:500])
        return None
