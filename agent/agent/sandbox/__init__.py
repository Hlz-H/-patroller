"""Windows Sandbox integration for 巡查者 (Patroller).

Provides isolated execution of suspicious files via Windows Sandbox,
behavior monitoring, and AI-powered analysis of sandbox results.
"""

from agent.sandbox.manager import SandboxManager
from agent.sandbox.reporter import BehaviorReport, BehaviorReporter

__all__ = [
    "SandboxManager",
    "BehaviorReport",
    "BehaviorReporter",
]
