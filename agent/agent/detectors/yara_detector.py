"""YARA-based malware detection for new and running processes.

Scans process executables against compiled YARA rules and generates alerts on match.
Falls back gracefully if yara-python is not installed.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Optional, TYPE_CHECKING

from agent.alert import AlertType, AlertSeverity

if TYPE_CHECKING:
    from agent.config import YARAConfig
    from agent.alert import AlertStore

logger = logging.getLogger(__name__)

# Try importing yara – gracefully degrade if not installed
try:
    import yara

    _YARA_AVAILABLE = True
except ImportError:
    logger.warning("yara-python not installed – YaraDetector will be disabled")
    yara = None  # type: ignore
    _YARA_AVAILABLE = False


class YaraDetector:
    """Scans process executables with YARA rules and creates alerts on match."""

    def __init__(
        self,
        config: YARAConfig,
        alert_store: AlertStore,
        callback: Optional[callable] = None,
    ) -> None:
        self._config = config
        self._alert_store = alert_store
        self._callback = callback
        self._rules: yara.Rules | None = None
        self._running = False
        self._scanned: set[str] = set()
        self._process_monitor = None

    @property
    def enabled(self) -> bool:
        if not _YARA_AVAILABLE:
            return False
        return self._config.enabled

    def set_callback(self, cb: callable) -> None:
        self._callback = cb

    def set_process_monitor(self, monitor) -> None:
        self._process_monitor = monitor

    async def load_rules(self) -> None:
        if not _YARA_AVAILABLE:
            logger.warning("Cannot load YARA rules – yara-python not installed")
            return

        rules_dir = Path(self._config.rules_dir)
        if not rules_dir.is_dir():
            logger.warning("YARA rules directory does not exist: %s", rules_dir)
            self._rules = None
            return

        rule_sources: dict[str, str] = {}
        for yar_file in sorted(rules_dir.glob("*.yar")):
            try:
                key = yar_file.name
                rule_sources[key] = yar_file.read_text(encoding="utf-8")
                logger.debug("Loaded YARA rule file: %s", yar_file)
            except Exception:
                logger.exception("Failed to read YARA file: %s", yar_file)

        if not rule_sources:
            logger.warning("No .yar files found in %s", rules_dir)
            self._rules = None
            return

        try:
            self._rules = yara.compile(sources=rule_sources)
            logger.info("Compiled %d YARA rule file(s)", len(rule_sources))
        except yara.SyntaxError:
            logger.exception("YARA compilation failed – check rule syntax")
            self._rules = None

    async def scan_process(self, exe_path: str, pid: int | None = None) -> None:
        if not self.enabled or self._rules is None:
            return

        # Dedup: skip paths already scanned
        if exe_path in self._scanned:
            return
        self._scanned.add(exe_path)

        if not Path(exe_path).is_file():
            return

        try:
            matches = await asyncio.to_thread(self._rules.match, exe_path, timeout=15)
        except yara.TimeoutError:
            logger.debug("YARA scan timed out for %s", exe_path)
            return
        except yara.Error:
            logger.debug("YARA scan error on %s", exe_path, exc_info=True)
            return

        if matches:
            rule_names = [m.rule for m in matches]
            tags = list({t for m in matches for t in (m.tags or [])})
            logger.warning(
                "YARA match on %s (pid=%s): rules=%s tags=%s",
                exe_path, pid, rule_names, tags,
            )

            alert_details = {
                "exe_path": exe_path,
                "pid": pid,
                "yara_rules": rule_names,
                "yara_tags": tags,
                "severity": "high",
            }

            self._alert_store.warn(
                AlertType.SYSTEM,
                f"YARA alert: {', '.join(rule_names)} matched {exe_path}",
                group_key=f"yara:{','.join(rule_names)}",
                **alert_details,
            )

            if self._callback:
                try:
                    self._callback(alert_details)
                except Exception:
                    logger.exception("YARA callback error")

    async def start(self) -> None:
        if not self.enabled:
            logger.info("YaraDetector disabled – skipping run")
            return

        await self.load_rules()
        if self._rules is None:
            return

        self._running = True
        logger.info(
            "YaraDetector running (interval=%ds, rules_dir=%s)",
            self._config.scan_interval_seconds,
            self._config.rules_dir,
        )

        while self._running:
            try:
                await self._scan_cycle()
            except Exception:
                logger.exception("YaraDetector scan cycle error")
            await asyncio.sleep(self._config.scan_interval_seconds)

    async def stop(self) -> None:
        self._running = False

    async def _scan_cycle(self) -> None:
        if self._process_monitor is None:
            return

        snapshot: list[dict] = self._process_monitor.latest_snapshot

        for proc in snapshot:
            exe = proc.get("exe") or ""
            if not exe:
                continue
            await self.scan_process(exe, pid=proc.get("pid"))
