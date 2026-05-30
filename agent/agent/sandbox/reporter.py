"""Behavior report models and parser for sandbox execution results.

Transforms raw JSON reports from the sandbox monitor script into structured,
analysis-friendly data.  Also provides a human-readable summary generation
for alert descriptions and UI display.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class FileChange:
    path: str
    change_type: str  # created | modified | deleted


@dataclass
class NetworkConnection:
    local: str
    remote: str
    state: str


@dataclass
class ProcessInfo:
    name: str
    id: int
    start_time: Optional[str] = None
    cpu: Optional[float] = None


@dataclass
class BehaviorReport:
    """Structured, validated behavior report from a sandbox run."""

    session: str = ""
    timed_out: bool = False
    error: Optional[str] = None
    raw_text: Optional[str] = None

    start_time: Optional[str] = None
    end_time: Optional[str] = None
    exit_code: int = -1

    processes: List[ProcessInfo] = field(default_factory=list)
    files: Dict[str, List[str]] = field(default_factory=lambda: {
        "created": [],
        "modified": [],
        "deleted": [],
    })
    network: List[NetworkConnection] = field(default_factory=list)

    @property
    def process_count(self) -> int:
        return len(self.processes)

    @property
    def file_changes_count(self) -> int:
        return (
            len(self.files.get("created", []))
            + len(self.files.get("modified", []))
            + len(self.files.get("deleted", []))
        )

    @property
    def suspicious_indicators(self) -> List[str]:
        """Return a list of human-readable suspicion signals."""
        signals = []

        if self.exit_code < 0 and self.exit_code != -1:
            signals.append(f"Process crashed or was killed (exit code {self.exit_code})")

        suspicious_procs = {
            "powershell", "cmd", "wscript", "cscript", "mshta",
            "regsvr32", "rundll32", "certutil", "bitsadmin",
        }
        procs_found = {p.name.lower() for p in self.processes}
        hits = suspicious_procs & procs_found
        if hits:
            signals.append(f"Suspicious processes spawned: {', '.join(sorted(hits))}")

        created = self.files.get("created", [])
        modified = self.files.get("modified", [])
        deleted = self.files.get("deleted", [])

        if created:
            signals.append(f"Created {len(created)} file(s)")
            # Check for executable creation
            exe_created = [f for f in created if f.lower().endswith((".exe", ".dll", ".ps1", ".bat", ".vbs"))]
            if exe_created:
                signals.append(f"Dropped {len(exe_created)} executable(s)")
        if deleted:
            signals.append(f"Deleted {len(deleted)} file(s)")

        if self.network:
            # Filter out loopback
            external = [c for c in self.network if "127.0.0.1" not in c.remote and "localhost" not in c.remote.lower()]
            if external:
                signals.append(f"External network connections: {len(external)}")

        return signals

    @property
    def is_suspicious(self) -> bool:
        """Quick heuristic: does this report contain red flags?"""
        if self.error:
            return False
        bad_procs = {"powershell", "cmd", "wscript", "cscript", "mshta", "certutil"}
        procs = {p.name.lower() for p in self.processes}
        if procs & bad_procs:
            return True
        if self.network:
            external = [c for c in self.network if "127.0.0.1" not in c.remote]
            if external:
                return True
        created = self.files.get("created", [])
        if any(f.lower().endswith((".exe", ".dll", ".ps1")) for f in created):
            return True
        return False

    def to_summary(self) -> str:
        """Human-readable summary for alert descriptions."""
        lines = [
            f"Sandbox session: {self.session}",
            f"Processes spawned: {self.process_count}",
            f"File changes: {self.file_changes_count}",
            f"Network connections: {len(self.network)}",
        ]
        signals = self.suspicious_indicators
        if signals:
            lines.append("Suspicious indicators:")
            lines.extend(f"  • {s}" for s in signals)
        if self.timed_out:
            lines.append("⚠ Sandbox execution timed out")
        return "\n".join(lines)


class BehaviorReporter:
    """Parses raw sandbox JSON reports into BehaviorReport dataclasses."""

    @staticmethod
    def parse(raw: dict) -> BehaviorReport:
        """Convert a raw JSON report dict to a structured BehaviorReport."""
        report = BehaviorReport(
            session=raw.get("session", ""),
            timed_out=bool(raw.get("timed_out", False)),
            error=raw.get("error"),
            raw_text=raw.get("raw_text"),
            start_time=raw.get("start_time"),
            end_time=raw.get("end_time"),
            exit_code=int(raw.get("exit_code", -1)),
        )

        for proc in raw.get("processes", []):
            if isinstance(proc, dict):
                report.processes.append(
                    ProcessInfo(
                        name=str(proc.get("name", "unknown")),
                        id=int(proc.get("id", 0)),
                        start_time=str(proc.get("start_time", "")),
                        cpu=float(proc.get("cpu", 0)) if proc.get("cpu") else None,
                    )
                )

        files = raw.get("files", {})
        if isinstance(files, dict):
            for k in ("created", "modified", "deleted"):
                items = files.get(k, [])
                if isinstance(items, list):
                    report.files[k] = [str(f) for f in items if isinstance(f, str)]

        for conn in raw.get("network", []):
            if isinstance(conn, dict):
                report.network.append(
                    NetworkConnection(
                        local=str(conn.get("local", "")),
                        remote=str(conn.get("remote", "")),
                        state=str(conn.get("state", "")),
                    )
                )

        return report

    @staticmethod
    def parse_file(path: Path) -> Optional[BehaviorReport]:
        """Load and parse a report from a JSON file on disk."""
        try:
            text = path.read_text(encoding="utf-8")
            raw = json.loads(text)
            return BehaviorReporter.parse(raw)
        except (FileNotFoundError, json.JSONDecodeError, IOError) as err:
            logger.error("Failed to parse report file %s: %s", path, err)
            return None
