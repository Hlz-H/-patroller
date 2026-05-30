"""Monitor modules for 巡查者 agent.

Each monitor runs as an independent async background task, collecting
data and feeding it to the alert engine and API layer.
"""

from agent.monitors.system_resource import SystemResourceMonitor
from agent.monitors.process_monitor import ProcessMonitor
from agent.monitors.usb_control import USBMonitor
from agent.monitors.registry_monitor import RegistryMonitor
from agent.monitors.service_monitor import ServiceMonitor
from agent.monitors.directory_integrity import DirectoryIntegrityMonitor

__all__ = [
    "SystemResourceMonitor",
    "ProcessMonitor",
    "USBMonitor",
    "RegistryMonitor",
    "ServiceMonitor",
    "DirectoryIntegrityMonitor",
]
