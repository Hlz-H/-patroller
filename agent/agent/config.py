"""Configuration management for 巡查者 agent.

Loads YAML configuration from bundled default, with optional user override
at %APPDATA%/巡查者/config.yaml.
"""

from __future__ import annotations

import logging
import os
import platform
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

logger = logging.getLogger(__name__)

# -- Configuration data models --


@dataclass
class MonitorConfig:
    """Per-monitor enable/interval settings."""

    enabled: bool = True
    interval_seconds: float = 5.0


@dataclass
class MonitorsConfig:

    system_resource: MonitorConfig = field(default_factory=MonitorConfig)
    process: MonitorConfig = field(default_factory=MonitorConfig)
    usb: MonitorConfig = field(default_factory=MonitorConfig)
    registry: MonitorConfig = field(default_factory=MonitorConfig)
    service: MonitorConfig = field(default_factory=MonitorConfig)
    directory_integrity: MonitorConfig = field(default_factory=MonitorConfig)


@dataclass
class USBConfig:
    """USB device control configuration."""

    blocklist: List[str] = field(default_factory=list)


@dataclass
class RegistryConfig:
    """Registry monitoring configuration.

    Attributes
    ----------
    monitored_keys : list
        List of registry key paths to monitor. Each entry is a tuple
        of (hive, subkey) like HKEY_LOCAL_MACHINE and a subkey.
    """
    monitored_keys: List[str] = field(default_factory=list)


@dataclass
class DirectoryIntegrityConfig:
    """Critical directory integrity monitoring configuration.

    Attributes
    ----------
    monitored_paths : list
        List of directory paths to monitor for file changes.
    watch_recursive : bool
        Whether to monitor subdirectories recursively.
    check_hash : bool
        Whether to compute SHA-256 hashes (expensive) or just stat.
    """
    monitored_paths: List[str] = field(default_factory=list)
    watch_recursive: bool = True
    check_hash: bool = False


@dataclass
class ServiceConfig:
    """Service monitoring configuration.

    Attributes
    ----------
    monitored_names : list
        List of specific service names to watch. Empty = watch all.
    alert_on_state_change : bool
        Whether to alert when a service changes state.
    alert_on_new_service : bool
        Whether to alert when a new service appears.
    """
    monitored_names: List[str] = field(default_factory=list)
    alert_on_state_change: bool = True
    alert_on_new_service: bool = True


@dataclass
class ProcessConfig:

    whitelist: List[str] = field(default_factory=list)
    blacklist: List[str] = field(default_factory=list)


@dataclass
class APIConfig:

    host: str = "127.0.0.1"
    port: int = 8099
    cors_origins: List[str] = field(default_factory=list)


@dataclass
class LoggingConfig:

    level: str = "INFO"
    file: str = "agent.log"
    max_bytes: int = 10_485_760
    backup_count: int = 3


@dataclass
class BackendConfig:
    """Backend WebSocket connection configuration."""

    host: str = "127.0.0.1"
    port: int = 3099
    device_id: str = ""
    device_name: str = ""
    enabled: bool = True
    reconnect_max_retries: int = -1


@dataclass
class YARAConfig:
    enabled: bool = False
    rules_dir: str = "rules/"
    scan_new_processes: bool = True
    scan_process_memory: bool = False
    scan_interval_seconds: float = 30.0


@dataclass
class MLAnomalyConfig:
    enabled: bool = False
    model_path: str = "models/anomaly_detector.joblib"
    contamination: float = 0.01
    training_hours: int = 24
    retrain_interval_hours: int = 4


@dataclass
class LLMConfig:
    enabled: bool = False
    endpoint: str = "http://localhost:11434"
    model: str = "qwen2.5:7b"
    batch_interval_minutes: int = 30
    batch_size: int = 50


@dataclass
class AIConfig:
    enabled: bool = False
    yara: YARAConfig = field(default_factory=YARAConfig)
    ml_anomaly: MLAnomalyConfig = field(default_factory=MLAnomalyConfig)
    llm: LLMConfig = field(default_factory=LLMConfig)


@dataclass
class VMConfig:
    networking: bool = False
    audio: bool = False
    gpu: bool = False
    clipboard: bool = False
    printer: bool = False


@dataclass
class SandboxAIAnalysisConfig:
    enabled: bool = True
    model: str = "qwen2.5:7b"
    prompt_template: str = ""


@dataclass
class TunerConfig:
    enabled: bool = True
    idle_multiplier: float = 2.0
    stress_multiplier: float = 0.25


@dataclass
class ResponderConfig:
    enabled: bool = True
    auto_respond_critical: bool = True
    auto_respond_warning: bool = False
    llm_threshold: int = 3


@dataclass
class BaselineConfig:
    enabled: bool = True
    learning_period: int = 7200
    storage_path: str = "data/baseline.json"


@dataclass
class SmartControlConfig:
    enabled: bool = True
    evaluation_interval: int = 60
    tuner: TunerConfig = field(default_factory=TunerConfig)
    responder: ResponderConfig = field(default_factory=ResponderConfig)
    baseline: BaselineConfig = field(default_factory=BaselineConfig)


@dataclass
class SandboxConfig:
    enabled: bool = False
    timeout_seconds: int = 120
    work_dir: str = "sandbox_work"
    vm: VMConfig = field(default_factory=VMConfig)
    ai_analysis: SandboxAIAnalysisConfig = field(default_factory=SandboxAIAnalysisConfig)


@dataclass
class AgentConfig:

    monitors: MonitorsConfig = field(default_factory=MonitorsConfig)
    usb: USBConfig = field(default_factory=USBConfig)
    process: ProcessConfig = field(default_factory=ProcessConfig)
    registry: RegistryConfig = field(default_factory=RegistryConfig)
    service: ServiceConfig = field(default_factory=ServiceConfig)
    directory_integrity: DirectoryIntegrityConfig = field(default_factory=DirectoryIntegrityConfig)
    api: APIConfig = field(default_factory=APIConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)
    backend: BackendConfig = field(default_factory=BackendConfig)
    ai: AIConfig = field(default_factory=AIConfig)
    sandbox: SandboxConfig = field(default_factory=SandboxConfig)
    smart_control: SmartControlConfig = field(default_factory=SmartControlConfig)


# -- Configuration loader --


def _default_config_path() -> Path:
    return Path(__file__).resolve().parent / "config.yaml"


def _user_config_path() -> Optional[Path]:
    """Return the user override config path (if it exists).

    Windows: %APPDATA%/巡查者/config.yaml
    """
    appdata = os.environ.get("APPDATA")
    if not appdata:
        return None
    return Path(appdata) / "巡查者" / "config.yaml"


def _load_raw_yaml(path: Path) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    return data if isinstance(data, dict) else {}


def _deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    """Recursively merge override dict into base dict."""
    for key, value in override.items():
        if key in base and isinstance(base[key], dict) and isinstance(value, dict):
            base[key] = _deep_merge(base[key], value)
        else:
            base[key] = value
    return base


def _parse_config(raw: Dict[str, Any]) -> AgentConfig:
    """Parse a raw dict into an AgentConfig dataclass."""

    def _monitor(name: str) -> MonitorConfig:
        data = raw.get("monitors", {}).get(name, {})
        return MonitorConfig(
            enabled=data.get("enabled", True),
            interval_seconds=float(data.get("interval_seconds", 5)),
        )

    def _usb() -> USBConfig:
        data = raw.get("usb", {})
        return USBConfig(blocklist=list(data.get("blocklist", [])))

    def _registry() -> RegistryConfig:
        data = raw.get("registry", {})
        return RegistryConfig(
            monitored_keys=list(data.get("monitored_keys", [])),
        )

    def _service() -> ServiceConfig:
        data = raw.get("service", {})
        return ServiceConfig(
            monitored_names=list(data.get("monitored_names", [])),
            alert_on_state_change=bool(data.get("alert_on_state_change", True)),
            alert_on_new_service=bool(data.get("alert_on_new_service", True)),
        )

    def _directory_integrity() -> DirectoryIntegrityConfig:
        data = raw.get("directory_integrity", {})
        return DirectoryIntegrityConfig(
            monitored_paths=list(data.get("monitored_paths", [])),
            watch_recursive=bool(data.get("watch_recursive", True)),
            check_hash=bool(data.get("check_hash", False)),
        )

    def _process() -> ProcessConfig:
        data = raw.get("process", {})
        return ProcessConfig(
            whitelist=list(data.get("whitelist", [])),
            blacklist=list(data.get("blacklist", [])),
        )

    def _api() -> APIConfig:
        data = raw.get("api", {})
        return APIConfig(
            host=data.get("host", "127.0.0.1"),
            port=int(data.get("port", 8099)),
            cors_origins=list(data.get("cors_origins", [])),
        )

    def _logging() -> LoggingConfig:
        data = raw.get("logging", {})
        return LoggingConfig(
            level=data.get("level", "INFO"),
            file=data.get("file", "agent.log"),
            max_bytes=int(data.get("max_bytes", 10_485_760)),
            backup_count=int(data.get("backup_count", 3)),
        )

    def _backend() -> BackendConfig:
        data = raw.get("backend", {})
        device_id = data.get("device_id", "") or platform.node()
        device_name = data.get("device_name", "") or os.environ.get(
            "COMPUTERNAME", platform.node()
        )
        return BackendConfig(
            host=data.get("host", "127.0.0.1"),
            port=int(data.get("port", 3099)),
            device_id=device_id,
            device_name=device_name,
            enabled=data.get("enabled", True),
            reconnect_max_retries=int(data.get("reconnect_max_retries", -1)),
        )

    def _yara() -> YARAConfig:
        data = raw.get("ai", {}).get("yara", {})
        return YARAConfig(
            enabled=bool(data.get("enabled", False)),
            rules_dir=str(data.get("rules_dir", "rules/")),
            scan_new_processes=bool(data.get("scan_new_processes", True)),
            scan_process_memory=bool(data.get("scan_process_memory", False)),
            scan_interval_seconds=float(data.get("scan_interval_seconds", 30)),
        )

    def _ml_anomaly() -> MLAnomalyConfig:
        data = raw.get("ai", {}).get("ml_anomaly", {})
        return MLAnomalyConfig(
            enabled=bool(data.get("enabled", False)),
            model_path=str(data.get("model_path", "models/anomaly_detector.joblib")),
            contamination=float(data.get("contamination", 0.01)),
            training_hours=int(data.get("training_hours", 24)),
            retrain_interval_hours=int(data.get("retrain_interval_hours", 4)),
        )

    def _llm() -> LLMConfig:
        data = raw.get("ai", {}).get("llm", {})
        return LLMConfig(
            enabled=bool(data.get("enabled", False)),
            endpoint=str(data.get("endpoint", "http://localhost:11434")),
            model=str(data.get("model", "qwen2.5:7b")),
            batch_interval_minutes=int(data.get("batch_interval_minutes", 30)),
            batch_size=int(data.get("batch_size", 50)),
        )

    def _vm() -> VMConfig:
        data = raw.get("sandbox", {}).get("vm", {})
        return VMConfig(
            networking=bool(data.get("networking", False)),
            audio=bool(data.get("audio", False)),
            gpu=bool(data.get("gpu", False)),
            clipboard=bool(data.get("clipboard", False)),
            printer=bool(data.get("printer", False)),
        )

    def _sandbox_ai() -> SandboxAIAnalysisConfig:
        data = raw.get("sandbox", {}).get("ai_analysis", {})
        return SandboxAIAnalysisConfig(
            enabled=bool(data.get("enabled", True)),
            model=str(data.get("model", "qwen2.5:7b")),
            prompt_template=str(data.get("prompt_template", "")),
        )

    def _sandbox() -> SandboxConfig:
        data = raw.get("sandbox", {})
        return SandboxConfig(
            enabled=bool(data.get("enabled", False)),
            timeout_seconds=int(data.get("timeout_seconds", 120)),
            work_dir=str(data.get("work_dir", "sandbox_work")),
            vm=_vm(),
            ai_analysis=_sandbox_ai(),
        )

    def _smart_control() -> SmartControlConfig:
        data = raw.get("smart_control", {})
        tuner = data.get("tuner", {})
        responder = data.get("responder", {})
        baseline = data.get("baseline", {})
        return SmartControlConfig(
            enabled=bool(data.get("enabled", True)),
            evaluation_interval=int(data.get("evaluation_interval", 60)),
            tuner=TunerConfig(
                enabled=bool(tuner.get("enabled", True)),
                idle_multiplier=float(tuner.get("idle_multiplier", 2.0)),
                stress_multiplier=float(tuner.get("stress_multiplier", 0.25)),
            ),
            responder=ResponderConfig(
                enabled=bool(responder.get("enabled", True)),
                auto_respond_critical=bool(responder.get("auto_respond_critical", True)),
                auto_respond_warning=bool(responder.get("auto_respond_warning", False)),
                llm_threshold=int(responder.get("llm_threshold", 3)),
            ),
            baseline=BaselineConfig(
                enabled=bool(baseline.get("enabled", True)),
                learning_period=int(baseline.get("learning_period", 7200)),
                storage_path=str(baseline.get("storage_path", "data/baseline.json")),
            ),
        )

    def _ai() -> AIConfig:
        data = raw.get("ai", {})
        return AIConfig(
            enabled=bool(data.get("enabled", False)),
            yara=_yara(),
            ml_anomaly=_ml_anomaly(),
            llm=_llm(),
        )

    return AgentConfig(
        monitors=MonitorsConfig(
            system_resource=_monitor("system_resource"),
            process=_monitor("process"),
            usb=_monitor("usb"),
            registry=_monitor("registry"),
            service=_monitor("service"),
            directory_integrity=_monitor("directory_integrity"),
        ),
        registry=_registry(),
        service=_service(),
        directory_integrity=_directory_integrity(),
        usb=_usb(),
        process=_process(),
        api=_api(),
        logging=_logging(),
        backend=_backend(),
        ai=_ai(),
        sandbox=_sandbox(),
        smart_control=_smart_control(),
    )


def load_config() -> AgentConfig:
    """Load configuration from default + optional user override.

    Priority: user override > bundled default.
    """
    default_path = _default_config_path()
    if not default_path.exists():
        logger.warning("Default config not found at %s, using hard-coded defaults", default_path)
        return AgentConfig()

    raw = _load_raw_yaml(default_path)

    user_path = _user_config_path()
    if user_path and user_path.exists():
        logger.info("Loading user config from %s", user_path)
        raw = _deep_merge(raw, _load_raw_yaml(user_path))

    return _parse_config(raw)
