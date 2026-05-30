"""Main orchestrator for 巡查者 (Patroller) agent.

Initialises configuration, alert system, monitors, API server, and
system tray; runs everything in an asyncio event loop with graceful
shutdown on SIGINT / SIGTERM.
"""

from __future__ import annotations

import asyncio
import logging
import signal
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any, Dict, List

from agent.alert import Alert, AlertStore, AlertType  # noqa: F401
from agent.config import AgentConfig, load_config
from agent.config import ProcessConfig, USBConfig
from agent.detectors.yara_detector import YaraDetector
from agent.detectors.ml_anomaly import MLAnomalyDetector
from agent.detectors.llm_analyzer import LLMAnalyzer
from agent.monitors.process_monitor import ProcessMonitor
from agent.monitors.system_resource import SystemResourceMonitor
from agent.monitors.usb_control import USBMonitor
from agent.monitors.registry_monitor import RegistryMonitor
from agent.monitors.service_monitor import ServiceMonitor
from agent.monitors.directory_integrity import DirectoryIntegrityMonitor
from agent.api.server import APIServer, set_smart_control_engine
from agent.backend_client import BackendClient
from agent.tray import SystemTray
from agent.sandbox import SandboxManager
from agent.controllers.smart_control import SmartControlEngine

logger = logging.getLogger(__name__)


class PatrollerAgent:
    """Top-level agent that orchestrates all subsystems.

    Usage::

        agent = PatrollerAgent()
        agent.run()
    """

    def __init__(self) -> None:
        self._config: AgentConfig = None  # type: ignore[assignment]
        self._alert_store: AlertStore = AlertStore()

        # Monitors — created after config is loaded.
        self._sys_monitor: SystemResourceMonitor = None  # type: ignore[assignment]
        self._proc_monitor: ProcessMonitor = None  # type: ignore[assignment]
        self._usb_monitor: USBMonitor = None  # type: ignore[assignment]
        self._reg_monitor: RegistryMonitor = None  # type: ignore[assignment]
        self._svc_monitor: ServiceMonitor = None  # type: ignore[assignment]
        self._dir_monitor: DirectoryIntegrityMonitor = None  # type: ignore[assignment]

        self._api_server: APIServer = None  # type: ignore[assignment]
        self._backend_client: BackendClient = None  # type: ignore[assignment]
        self._tray: SystemTray = None  # type: ignore[assignment]

        self._yara_detector: YaraDetector = None  # type: ignore[assignment]
        self._ml_detector: MLAnomalyDetector = None  # type: ignore[assignment]
        self._llm_analyzer: LLMAnalyzer = None  # type: ignore[assignment]

        self._sandbox_mgr: SandboxManager = None  # type: ignore[assignment]
        self._smart_control: SmartControlEngine = None  # type: ignore[assignment]

        self._tasks: List[asyncio.Task[Any]] = []
        self._running = False

    # -- Public API --

    def run(self) -> None:
        self._setup_logging()
        logger.info("=" * 50)
        logger.info("巡查者 Agent v%s starting", "0.1.0")

        try:
            self._config = load_config()
        except Exception:
            logger.exception("Failed to load config; using defaults")
            self._config = AgentConfig()

        self._apply_logging_config()

        try:
            asyncio.run(self._main_loop())
        except KeyboardInterrupt:
            logger.info("KeyboardInterrupt received")
        finally:
            logger.info("Agent shut down complete")

    # -- Main async loop --

    async def _main_loop(self) -> None:
        """Async main loop: initialise → start → wait."""
        self._running = True

        # Register signal handlers (requires running event loop).
        self._register_signals()

        self._init_monitors()
        self._init_sandbox()
        self._init_api_server()
        self._init_tray()
        self._init_backend_client()
        self._init_ai_detectors()
        self._init_smart_control()
        if self._smart_control:
            set_smart_control_engine(self._smart_control)

        self._sys_monitor.set_callback(self._on_system_metrics)

        await self._start_monitors()
        await self._start_api_server()
        self._start_tray()

        if self._backend_client:
            backend_task = asyncio.create_task(self._backend_client.run())
            self._tasks.append(backend_task)
            logger.info("BackendClient started")

        if self._yara_detector and self._yara_detector.enabled:
            self._tasks.append(asyncio.create_task(self._yara_detector.start()))
        if self._ml_detector and self._ml_detector.enabled:
            self._tasks.append(asyncio.create_task(self._ml_detector.start()))
        if self._llm_analyzer and self._llm_analyzer.enabled:
            self._tasks.append(asyncio.create_task(self._llm_analyzer.start()))

        if self._smart_control:
            self._smart_control.start()

        self._alert_store.info(AlertType.SYSTEM, "Agent started successfully")
        logger.info(
            "Agent ready — API: http://%s:%d",
            self._config.api.host,
            self._config.api.port,
        )

        while self._running:
            await asyncio.sleep(0.5)

        await self._shutdown()

    # -- Subsystem initialisation --

    def _init_monitors(self) -> None:
        self._sys_monitor = SystemResourceMonitor(
            self._config.monitors.system_resource
        )
        self._proc_monitor = ProcessMonitor(
            self._config.monitors.process,
            self._config.process,
            self._alert_store,
        )
        self._usb_monitor = USBMonitor(
            self._config.monitors.usb,
            self._config.usb,
            self._alert_store,
        )
        self._reg_monitor = RegistryMonitor(
            self._config.monitors.registry,
            self._config.registry,
            self._alert_store,
        )
        self._svc_monitor = ServiceMonitor(
            self._config.monitors.service,
            self._config.service,
            self._alert_store,
        )
        self._dir_monitor = DirectoryIntegrityMonitor(
            self._config.monitors.directory_integrity,
            self._config.directory_integrity,
            self._alert_store,
        )

    def _init_api_server(self) -> None:
        self._api_server = APIServer(
            self._config,
            self._alert_store,
            self._sys_monitor,
            self._proc_monitor,
            self._usb_monitor,
            sandbox_mgr=self._sandbox_mgr,
            reg_monitor=self._reg_monitor,
            svc_monitor=self._svc_monitor,
            dir_monitor=self._dir_monitor,
        )

    def _init_tray(self) -> None:
        self._tray = SystemTray(
            self._alert_store,
            api_host=self._config.api.host,
            api_port=self._config.api.port,
        )
        # Provide a shutdown callback so tray "Exit" stops the agent gracefully.
        self._tray._request_shutdown = self.request_shutdown

    def _init_backend_client(self) -> None:
        """Create the Backend WebSocket client and wire up command/alert handlers."""
        if not self._config.backend.enabled:
            logger.info("Backend connection disabled in config")
            return

        backend_cfg = self._config.backend
        self._backend_client = BackendClient(
            host=backend_cfg.host,
            port=backend_cfg.port,
            device_id=backend_cfg.device_id,
            device_name=backend_cfg.device_name,
        )

        # Command handler: routes Backend commands to the appropriate monitor.
        async def _handle_command(action: str, payload: dict) -> Any:
            if action == "kill_process":
                success, msg = self._proc_monitor.kill_process(
                    int(payload.get("pid", 0))
                )
                return {"success": success, "message": msg}
            elif action == "usb_block":
                new_config = USBConfig(blocklist=list(payload.get("blocklist", [])))
                self._usb_monitor.update_config(new_config)
                return {"status": "ok"}
            elif action == "sandbox_run":
                if not self._sandbox_mgr or not self._sandbox_mgr.enabled:
                    return {"error": "Sandbox not enabled"}
                file_path = payload.get("file_path", "")
                if not file_path:
                    return {"error": "file_path required"}
                report = await self._sandbox_mgr.run_file(file_path)
                if report is None:
                    return {"error": "Sandbox execution failed"}
                # Also run AI analysis if available.
                llm_cfg = self._config.ai.llm
                analysis = None
                if llm_cfg.enabled and report:
                    analysis = await self._sandbox_mgr.analyze_report(
                        report, llm_endpoint=llm_cfg.endpoint, model=llm_cfg.model,
                    )
                return {"status": "completed", "report": report, "analysis": analysis}
            elif action == "config_update":
                proc_data = payload.get("process", {})
                usb_data = payload.get("usb", {})
                if proc_data:
                    proc_config = ProcessConfig(
                        whitelist=list(proc_data.get("whitelist", [])),
                        blacklist=list(proc_data.get("blacklist", [])),
                    )
                    self._proc_monitor.update_config(proc_config)
                if usb_data:
                    usb_config = USBConfig(
                        blocklist=list(usb_data.get("blocklist", []))
                    )
                    self._usb_monitor.update_config(usb_config)
                return {"status": "ok"}
            else:
                logger.warning("Unknown backend command action: %s", action)
                return {"error": f"unknown action: {action}"}

        self._backend_client.set_command_handler(_handle_command)

        # Subscribe to alert callbacks so every alert is forwarded to Backend.
        def _on_alert(alert: Alert) -> None:
            if self._backend_client and self._backend_client.connected:
                asyncio.create_task(
                    self._backend_client.send_alert(alert.to_dict())
                )

        self._alert_store.subscribe(_on_alert)
        logger.info("BackendClient initialized (host=%s:%d)", backend_cfg.host, backend_cfg.port)

    def _init_ai_detectors(self) -> None:
        ai_cfg = self._config.ai
        if not ai_cfg.enabled:
            logger.info("AI detection disabled")
            return

        if ai_cfg.yara.enabled:
            try:
                self._yara_detector = YaraDetector(ai_cfg.yara, self._alert_store)
                logger.info("YaraDetector initialized")
            except Exception:
                logger.exception("Failed to init YaraDetector")

        if ai_cfg.ml_anomaly.enabled:
            try:
                self._ml_detector = MLAnomalyDetector(ai_cfg.ml_anomaly, self._alert_store)
                self._ml_detector.set_process_monitor(self._proc_monitor)
                logger.info("MLAnomalyDetector initialized")
            except Exception:
                logger.exception("Failed to init MLAnomalyDetector")

        if ai_cfg.llm.enabled:
            try:
                self._llm_analyzer = LLMAnalyzer(ai_cfg.llm, self._alert_store)
                logger.info("LLMAnalyzer initialized")
            except Exception:
                logger.exception("Failed to init LLMAnalyzer")

        logger.info("AI detectors initialized (yara=%s, ml=%s, llm=%s)",
                     ai_cfg.yara.enabled, ai_cfg.ml_anomaly.enabled, ai_cfg.llm.enabled)

    def _init_smart_control(self) -> None:
        sc_cfg = self._config.smart_control
        if not sc_cfg.enabled:
            logger.info("SmartControl disabled in config")
            return

        def _kill_process(pid: int) -> None:
            if self._proc_monitor:
                self._proc_monitor.kill_process(pid)

        def _disable_usb() -> None:
            if self._usb_monitor:
                from agent.config import USBConfig
                self._usb_monitor.update_config(USBConfig(blocklist=["*"]))

        def _trigger_sandbox(file_path: str) -> None:
            if self._sandbox_mgr and self._sandbox_mgr.enabled:
                asyncio.create_task(self._sandbox_mgr.run_file(file_path))

        def _call_llm(alert: Alert) -> None:
            if self._llm_analyzer and self._llm_analyzer.enabled:
                asyncio.create_task(
                    self._llm_analyzer._analyze_batch([alert])
                )

        try:
            self._smart_control = SmartControlEngine(
                config=sc_cfg,
                alert_store=self._alert_store,
                monitors=[
                    self._sys_monitor,
                    self._proc_monitor,
                    self._usb_monitor,
                    self._reg_monitor,
                    self._svc_monitor,
                    self._dir_monitor,
                ],
                kill_process_fn=_kill_process,
                disable_usb_fn=_disable_usb,
                sandbox_fn=_trigger_sandbox,
                llm_analysis_fn=_call_llm,
            )
            logger.info("SmartControlEngine initialized")
        except Exception:
            logger.exception("Failed to init SmartControlEngine")

    def _init_sandbox(self) -> None:
        if not self._config.sandbox.enabled:
            logger.info("Sandbox disabled in config")
            return
        try:
            self._sandbox_mgr = SandboxManager(self._config.sandbox, self._alert_store)
            if self._sandbox_mgr.available:
                logger.info("SandboxManager initialized (available=%s)", self._sandbox_mgr.available)
            else:
                logger.warning("SandboxManager initialized but Windows Sandbox not available")
        except Exception:
            logger.exception("Failed to init SandboxManager")

    # -- Start / stop --

    async def _start_monitors(self) -> None:
        cfg = self._config.monitors

        if cfg.system_resource.enabled:
            task = asyncio.create_task(self._sys_monitor.run())
            self._tasks.append(task)
            logger.info("SystemResourceMonitor started (interval=%.1fs)", cfg.system_resource.interval_seconds)

        if cfg.process.enabled:
            task = asyncio.create_task(self._proc_monitor.run())
            self._tasks.append(task)
            logger.info("ProcessMonitor started (interval=%.1fs)", cfg.process.interval_seconds)

        if cfg.usb.enabled:
            task = asyncio.create_task(self._usb_monitor.run())
            self._tasks.append(task)
            logger.info("USBMonitor started (interval=%.1fs)", cfg.usb.interval_seconds)

        if cfg.registry.enabled:
            task = asyncio.create_task(self._reg_monitor.run())
            self._tasks.append(task)
            logger.info("RegistryMonitor started (interval=%.1fs)", cfg.registry.interval_seconds)

        if cfg.service.enabled:
            task = asyncio.create_task(self._svc_monitor.run())
            self._tasks.append(task)
            logger.info("ServiceMonitor started (interval=%.1fs)", cfg.service.interval_seconds)

        if cfg.directory_integrity.enabled:
            task = asyncio.create_task(self._dir_monitor.run())
            self._tasks.append(task)
            logger.info("DirectoryIntegrityMonitor started (interval=%.1fs)", cfg.directory_integrity.interval_seconds)

    async def _start_api_server(self) -> None:
        self._tasks.append(asyncio.create_task(self._api_server.run()))

    def _start_tray(self) -> None:
        self._tray.start()

    def request_shutdown(self) -> None:
        """Signal the agent to shut down (called from tray Exit or elsewhere)."""
        logger.info("Shutdown requested via tray / external signal")
        self._running = False

    async def _shutdown(self) -> None:
        """Stop all subsystems gracefully."""
        logger.info("Shutting down...")

        # Stop Backend client first (so we don't try to push during shutdown).
        if self._backend_client:
            try:
                await self._backend_client.stop()
            except Exception:
                logger.exception("Error stopping BackendClient")

        # Stop AI detectors.
        for detector in [self._yara_detector, self._ml_detector, self._llm_analyzer]:
            if detector:
                try:
                    await detector.stop()
                except Exception:
                    logger.exception("Error stopping AI detector")

        # Stop monitors.
        for name, monitor in [
            ("SystemResourceMonitor", self._sys_monitor),
            ("ProcessMonitor", self._proc_monitor),
            ("USBMonitor", self._usb_monitor),
            ("RegistryMonitor", self._reg_monitor),
            ("ServiceMonitor", self._svc_monitor),
            ("DirectoryIntegrityMonitor", self._dir_monitor),
        ]:
            try:
                await monitor.stop()
            except Exception:
                logger.exception("Error stopping %s", name)

        # Stop SmartControlEngine.
        if self._smart_control:
            try:
                await self._smart_control.stop()
            except Exception:
                logger.exception("Error stopping SmartControlEngine")

        # Stop API server.
        try:
            await self._api_server.stop()
        except Exception:
            logger.exception("Error stopping API server")

        # Stop tray.
        try:
            self._tray.stop()
        except Exception:
            logger.exception("Error stopping tray")

        # Cancel remaining tasks.
        for task in self._tasks:
            if not task.done():
                task.cancel()
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)

        self._alert_store.info(AlertType.SYSTEM, "Agent stopped")

    # -- Callbacks — bridge monitors → WebSocket / logs --

    def _on_system_metrics(self, metrics: Dict[str, Any]) -> None:
        """Called by SystemResourceMonitor each poll cycle.

        Broadcasts metrics to all connected WebSocket clients and the
        Node.js Backend.
        """
        if self._api_server and hasattr(self._api_server, "ws_manager"):
            asyncio.create_task(
                self._api_server.ws_manager.broadcast_metrics(metrics)
            )

        # Push to Node.js Backend if connected.
        if self._backend_client and self._backend_client.connected:
            asyncio.create_task(self._backend_client.send_metrics(metrics))

    # -- Signal handling --

    def _register_signals(self) -> None:
        try:
            loop = asyncio.get_running_loop()
            for sig in (signal.SIGINT, signal.SIGTERM):
                loop.add_signal_handler(sig, self.request_shutdown)
        except (NotImplementedError, RuntimeError):
            # Signal handling not available on this platform / event loop.
            pass

    # -- Logging setup --

    def _setup_logging(self) -> None:
        """Minimal bootstrap logging to console before config is loaded."""
        fmt = logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        root = logging.getLogger()
        root.setLevel(logging.INFO)

        if not any(isinstance(h, logging.StreamHandler) for h in root.handlers):
            ch = logging.StreamHandler(sys.stdout)
            ch.setFormatter(fmt)
            root.addHandler(ch)

    def _apply_logging_config(self) -> None:
        """Apply logging configuration from the config file."""
        log_cfg = self._config.logging
        root = logging.getLogger()
        root.setLevel(getattr(logging, log_cfg.level.upper(), logging.INFO))

        # Remove old file handlers and add a rotating file handler.
        for handler in list(root.handlers):
            if isinstance(handler, RotatingFileHandler):
                root.removeHandler(handler)

        log_path = Path(log_cfg.file)
        log_path.parent.mkdir(parents=True, exist_ok=True)

        fh = RotatingFileHandler(
            filename=str(log_path),
            maxBytes=log_cfg.max_bytes,
            backupCount=log_cfg.backup_count,
            encoding="utf-8",
        )
        fmt = logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        fh.setFormatter(fmt)
        root.addHandler(fh)

        logger.info("Logging configured: level=%s, file=%s", log_cfg.level, log_path)
