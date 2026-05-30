"""SandboxManager — Windows Sandbox lifecycle controller.

Creates .wsb configuration files, launches WindowsSandbox.exe, monitors
execution, and collects behavior reports from the sandbox output folder.

Relies on Windows Sandbox (Windows 10/11 Pro/Enterprise). Falls back
gracefully if the feature is not available.
"""

from __future__ import annotations

import asyncio
import logging
import os
import platform
import subprocess
import tempfile
import time
import uuid
from pathlib import Path
from typing import Optional

from agent.alert import Alert, AlertStore, AlertType
from agent.config import SandboxConfig
from agent.sandbox.reporter import BehaviorReporter

logger = logging.getLogger(__name__)

_SANDBOX_EXE = "WindowsSandbox.exe"

# PowerShell monitor script — embedded to avoid external file dependencies.
_MONITOR_SCRIPT = r"""
param(
    [string]$TargetExe,
    [string]$OutputDir
)

$report = @{
    processes = @()
    files = @{ created = @(); modified = @(); deleted = @() }
    network = @()
    start_time = [DateTime]::UtcNow.ToString("o")
    exit_code = -1
}

# Start monitoring
$script:running = $true

# File watcher
$watcher = New-Object System.IO.FileSystemWatcher
$watcher.Path = "C:\Users\WDAGUtilityAccount\Desktop"
$watcher.IncludeSubdirectories = $true
$watcher.EnableRaisingEvents = $true

Register-ObjectEvent $watcher "Created" -Action {
    $report.files.created += $Event.SourceEventArgs.FullPath
} | Out-Null

Register-ObjectEvent $watcher "Deleted" -Action {
    $report.files.deleted += $Event.SourceEventArgs.FullPath
} | Out-Null

Register-ObjectEvent $watcher "Changed" -Action {
    $report.files.modified += $Event.SourceEventArgs.FullPath
} | Out-Null

# Network monitor (if available)
$netMon = $null
try {
    $netMon = Get-NetAdapter -Name "*" -ErrorAction Stop
} catch {}

# Run the target
$proc = $null
$psi = New-Object System.Diagnostics.ProcessStartInfo
$psi.FileName = $TargetExe
$psi.UseShellExecute = $false
$psi.RedirectStandardOutput = $true
$psi.RedirectStandardError = $true

try {
    $proc = [System.Diagnostics.Process]::Start($psi)
    $report.processes += @{
        name = $proc.ProcessName
        id = $proc.Id
        start_time = $proc.StartTime.ToString("o")
    }

    # Monitor while running
    while (!$proc.HasExited) {
        # Collect child processes
        Get-Process | Where-Object { $_.Parent -eq $proc.Id -or $_.Id -eq $proc.Id } | ForEach-Object {
            $entry = @{ name = $_.ProcessName; id = $_.Id; cpu = $_.CPU }
            if ($report.processes -notcontains $entry) {
                $report.processes += $entry
            }
        }
        Start-Sleep -Milliseconds 500
    }

    $report.exit_code = $proc.ExitCode

    # Collect network connections
    if ($netMon) {
        try {
            $connections = Get-NetTCPConnection -State Established -ErrorAction SilentlyContinue
            $report.network = $connections | ForEach-Object {
                @{ local = $_.LocalAddress + ":" + $_.LocalPort; remote = $_.RemoteAddress + ":" + $_.RemotePort; state = $_.State }
            }
        } catch {}
    }
} catch {
    $report.exit_code = -999
    $report.error = $_.Exception.Message
}

$report.end_time = [DateTime]::UtcNow.ToString("o")
$report | ConvertTo-Json -Depth 5 | Out-File -FilePath (Join-Path $OutputDir "report.json") -Encoding utf8

# Signal completion
$null = New-Item -Path (Join-Path $OutputDir "done.txt") -ItemType File -Force
"""


def _is_windows_sandbox_available() -> bool:
    """Check if Windows Sandbox is available on this system.

    Returns True only on Windows 10/11 Pro/Enterprise with Sandbox enabled.
    """
    if platform.system() != "Windows":
        return False

    try:
        result = subprocess.run(
            ["where", _SANDBOX_EXE],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def _build_wsb_config(
    host_file: Path,
    sandbox_output: Path,
    monitor_script: Path,
    config: SandboxConfig,
) -> str:
    """Generate a .wsb XML configuration string.

    Maps the target file and monitor script into the sandbox,
    and configures VM features per user settings.
    """
    vm = config.vm
    # Use forward slashes in XML paths to avoid Python backslash escaping issues.
    # Windows Sandbox accepts forward slashes in MappedFolders paths.
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<Configuration>
  <VGpu>{str(vm.gpu).lower()}</VGpu>
  <Networking>{str(vm.networking).lower()}</Networking>
  <AudioInput>{str(vm.audio).lower()}</AudioInput>
  <VideoInput>{str(vm.audio).lower()}</VideoInput>
  <Clipboard>{str(vm.clipboard).lower()}</Clipboard>
  <Printer>{str(vm.printer).lower()}</Printer>
  <MappedFolders>
    <MappedFolder>
      <HostFolder>{host_file.parent}</HostFolder>
      <SandboxFolder>C:/Users/WDAGUtilityAccount/Desktop/input</SandboxFolder>
      <ReadOnly>true</ReadOnly>
    </MappedFolder>
    <MappedFolder>
      <HostFolder>{sandbox_output.parent}</HostFolder>
      <SandboxFolder>C:/Users/WDAGUtilityAccount/Desktop/output</SandboxFolder>
      <ReadOnly>false</ReadOnly>
    </MappedFolder>
  </MappedFolders>
  <LogonCommand>
    <Command>powershell.exe -ExecutionPolicy Bypass -File "C:/Users/WDAGUtilityAccount/Desktop/input/{monitor_script.name}" -TargetExe "C:/Users/WDAGUtilityAccount/Desktop/input/{host_file.name}" -OutputDir "C:/Users/WDAGUtilityAccount/Desktop/output"</Command>
  </LogonCommand>
</Configuration>
"""


class SandboxManager:
    """Manages the lifecycle of a Windows Sandbox execution.

    Usage::

        mgr = SandboxManager(config, alert_store)
        report = await mgr.run_file("/path/to/suspicious.exe")
        if report:
            analysis = await mgr.analyze_report(report)
    """

    def __init__(self, config: SandboxConfig, alert_store: AlertStore) -> None:
        self._config = config
        self._alert_store = alert_store
        self._work_dir = Path(config.work_dir)
        self._work_dir.mkdir(parents=True, exist_ok=True)
        self._available = _is_windows_sandbox_available()

        if not self._available:
            logger.warning(
                "Windows Sandbox not available on this system. "
                "SandboxManager will report errors on run attempts."
            )

    @property
    def enabled(self) -> bool:
        return self._config.enabled

    @property
    def available(self) -> bool:
        return self._available

    async def run_file(
        self,
        file_path: str,
        timeout: Optional[int] = None,
    ) -> Optional[dict]:
        """Execute a file in Windows Sandbox and return the behavior report.

        Parameters
        ----------
        file_path : str
            Absolute path to the file to execute in the sandbox.
        timeout : int, optional
            Override the default timeout in seconds.

        Returns
        -------
        dict or None
            Parsed behavior report, or None if execution failed.
        """
        if not self._available:
            self._alert_store.warn(
                AlertType.SYSTEM,
                "Sandbox not available — Windows Sandbox feature is not installed/enabled",
            )
            return None

        host_file = Path(file_path).resolve()
        if not host_file.exists():
            logger.error("Sandbox target file not found: %s", file_path)
            return None

        # Create a unique session directory
        session_id = uuid.uuid4().hex[:12]
        session_dir = self._work_dir / session_id
        session_dir.mkdir(parents=True, exist_ok=True)

        monitor_script = session_dir / "monitor.ps1"
        monitor_script.write_text(_MONITOR_SCRIPT, encoding="utf-8")

        output_dir = session_dir / "output"
        output_dir.mkdir(exist_ok=True)

        wsb_content = _build_wsb_config(
            host_file=host_file,
            sandbox_output=output_dir,
            monitor_script=monitor_script,
            config=self._config,
        )
        wsb_path = session_dir / "config.wsb"
        wsb_path.write_text(wsb_content, encoding="utf-8")

        try:
            proc = await asyncio.create_subprocess_exec(
                _SANDBOX_EXE,
                str(wsb_path),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            # Wait for completion or timeout
            try:
                await asyncio.wait_for(
                    proc.wait(),
                    timeout=timeout or self._config.timeout_seconds,
                )
            except asyncio.TimeoutError:
                logger.warning("Sandbox timed out for session %s — terminating", session_id)
                try:
                    proc.terminate()
                except ProcessLookupError:
                    pass
                return await self._collect_report(session_dir, output_dir, timed_out=True)

            # Collect the report
            return await self._collect_report(session_dir, output_dir)

        except FileNotFoundError:
            logger.error("WindowsSandbox.exe not found — is Windows Sandbox installed?")
            self._alert_store.error(
                AlertType.SYSTEM,
                "Sandbox execution failed: WindowsSandbox.exe not found",
            )
            return None
        except Exception:
            logger.exception("Sandbox execution error for session %s", session_id)
            return None

    async def analyze_report(self, report: dict, llm_endpoint: str, model: str) -> Optional[dict]:
        """Send a behavior report to the LLM for AI analysis.

        Parameters
        ----------
        report : dict
            The behavior report from a sandbox execution.
        llm_endpoint : str
            Base URL of the ollama API (e.g. http://localhost:11434).
        model : str
            Model name (e.g. qwen2.5:7b).

        Returns
        -------
        dict or None
            Parsed LLM analysis with classification, confidence, reasoning.
        """
        if not self._config.ai_analysis.enabled:
            logger.info("Sandbox AI analysis disabled in config")
            return None

        import httpx

        prompt_template = self._config.ai_analysis.prompt_template
        if not prompt_template:
            prompt_template = (
                "You are a malware analyst. A file was executed in a Windows Sandbox.\n"
                "Below is the behavior report:\n\n{report}\n\n"
                "Classify the behavior as: SAFE / SUSPICIOUS / MALICIOUS.\n"
                "Provide a confidence score (0-100) and a brief reasoning.\n"
                'Return JSON: {{"classification": "...", "confidence": ..., "reasoning": "..."}}'
            )

        import json
        prompt = prompt_template.replace("{report}", json.dumps(report, indent=2, default=str))

        url = f"{llm_endpoint.rstrip('/')}/api/generate"
        payload = {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0.1},
        }

        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                resp = await client.post(url, json=payload)
                resp.raise_for_status()
                data = resp.json()
                raw = data.get("response", "")

            # Parse JSON from LLM response
            import re
            json_match = re.search(r"\{.*\}", raw, re.DOTALL)
            if json_match:
                return json.loads(json_match.group(0))
            return {"classification": "UNKNOWN", "confidence": 0, "reasoning": raw[:500]}

        except Exception:
            logger.exception("Sandbox AI analysis HTTP request failed")
            return None

    async def _collect_report(
        self,
        session_dir: Path,
        output_dir: Path,
        timed_out: bool = False,
    ) -> Optional[dict]:
        """Read and parse the behavior report from the sandbox output folder."""
        report_file = output_dir / "report.json"
        done_file = output_dir / "done.txt"

        if timed_out:
            # Give the sandbox a moment to flush output
            await asyncio.sleep(2)

        if not report_file.exists():
            logger.warning("No report file found in sandbox output (session timed out?)")
            return {
                "session": session_dir.name,
                "timed_out": timed_out,
                "error": "No behavior report generated",
                "processes": [],
                "files": {"created": [], "modified": [], "deleted": []},
                "network": [],
            }

        try:
            import json
            text = report_file.read_text(encoding="utf-8")
            report = json.loads(text)
            report["session"] = session_dir.name
            report["timed_out"] = timed_out
            return report
        except (json.JSONDecodeError, IOError) as err:
            logger.error("Failed to parse sandbox report: %s", err)
            return {
                "session": session_dir.name,
                "error": f"Report parse error: {err}",
                "raw_text": report_file.read_text(encoding="utf-8", errors="replace")[:2000],
            }
