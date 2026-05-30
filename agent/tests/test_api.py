"""Tests for the Agent REST API (FastAPI endpoints)."""

import sys
import time
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

# Ensure project root and agent module are on path
sys.path.insert(0, str(Path(__file__).parent.parent / "agent"))

from agent.alert import AlertStore, AlertType
from agent.api.server import create_app
from agent.config import APIConfig


@pytest.fixture
def alert_store():
    return AlertStore()


@pytest.fixture
def mock_monitors():
    sys_mon = MagicMock()
    sys_mon.latest_metrics = {
        "cpu": {"percent": 45.2, "per_core": [50.0, 40.0]},
        "memory": {"total": 16000000000, "used": 8000000000, "percent": 50.0},
        "disk": {"total": 500000000000, "used": 250000000000, "percent": 50.0},
        "network": {"bytes_sent": 1000000, "bytes_recv": 2000000},
    }
    sys_mon.status.return_value = {"running": True, "uptime": 123.45}

    proc_mon = MagicMock()
    proc_mon.latest_snapshot = [
        {"pid": 1, "name": "System", "exe": "C:\\Windows\\System32\\ntoskrnl.exe",
         "cpu_percent": 0.5, "memory_percent": 0.1, "status": "running"},
        {"pid": 1000, "name": "chrome.exe",
         "exe": "C:\\Program Files\\Google\\Chrome\\chrome.exe",
         "cpu_percent": 15.2, "memory_percent": 5.3, "status": "running"},
    ]
    proc_mon.status.return_value = {"running": True, "total_processes": 2}
    proc_mon.latest_total = 200
    proc_mon.update_config = MagicMock()

    usb_mon = MagicMock()
    usb_mon.latest_devices = [
        {"device_id": "USB\\VID_0781", "name": "SanDisk USB Drive", "connected": True}
    ]
    usb_mon.events = [
        {"type": "connected", "device_id": "USB\\VID_0781", "timestamp": time.time()}
    ]
    usb_mon.status.return_value = {"running": True, "devices_count": 1}
    usb_mon.update_config = MagicMock()

    return sys_mon, proc_mon, usb_mon


@pytest.fixture
def config():
    cfg = MagicMock()
    cfg.api = APIConfig(host="127.0.0.1", port=8099, cors_origins=["*"])
    return cfg


@pytest.fixture
def client(alert_store, mock_monitors, config):
    sys_mon, proc_mon, usb_mon = mock_monitors
    app, _ = create_app(config, alert_store, sys_mon, proc_mon, usb_mon)
    return TestClient(app)


class TestStatusEndpoint:
    def test_get_status_returns_running(self, client):
        resp = client.get("/api/v1/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "running"
        assert "version" in data
        assert "monitors" in data

    def test_status_contains_monitor_statuses(self, client):
        resp = client.get("/api/v1/status")
        data = resp.json()
        assert "system_resource" in data["monitors"]
        assert "process" in data["monitors"]
        assert "usb" in data["monitors"]


class TestSystemEndpoint:
    def test_get_system_with_metrics(self, client):
        resp = client.get("/api/v1/system")
        assert resp.status_code == 200
        data = resp.json()
        assert "cpu" in data
        assert data["cpu"]["percent"] == 45.2

    def test_get_system_no_metrics(self, alert_store, mock_monitors, config):
        sys_mon, proc_mon, usb_mon = mock_monitors
        sys_mon.latest_metrics = None
        app, _ = create_app(config, alert_store, sys_mon, proc_mon, usb_mon)
        c = TestClient(app)
        resp = c.get("/api/v1/system")
        assert resp.status_code == 200
        assert "error" in resp.json()


class TestProcessesEndpoint:
    def test_get_processes_returns_list(self, client):
        resp = client.get("/api/v1/processes")
        data = resp.json()
        assert "total" in data
        assert len(data["processes"]) == 2

    def test_get_processes_pagination(self, alert_store, mock_monitors, config):
        sys_mon, proc_mon, usb_mon = mock_monitors
        proc_mon.latest_snapshot = proc_mon.latest_snapshot[:1]
        app, _ = create_app(config, alert_store, sys_mon, proc_mon, usb_mon)
        c = TestClient(app)
        resp = c.get("/api/v1/processes?limit=1&offset=0")
        data = resp.json()
        assert len(data["processes"]) == 1
        assert data["limit"] == 1


class TestAlertsEndpoint:
    def test_get_alerts_empty(self, client):
        resp = client.get("/api/v1/alerts")
        data = resp.json()
        assert data["total"] == 0
        assert data["alerts"] == []

    def test_get_alerts_with_data(self, alert_store, mock_monitors, config):
        alert_store.info(AlertType.SYSTEM, "Startup")
        alert_store.warn(AlertType.PROCESS, "High CPU")
        alert_store.critical(AlertType.USB, "Unauthorized device")
        app, _ = create_app(config, alert_store, *mock_monitors)
        c = TestClient(app)
        resp = c.get("/api/v1/alerts")
        data = resp.json()
        assert data["total"] == 3
        assert len(data["alerts"]) == 3

    def test_get_alerts_filter_by_severity(self, alert_store, mock_monitors, config):
        alert_store.info(AlertType.SYSTEM, "Info")
        alert_store.warn(AlertType.PROCESS, "Warning")
        app, _ = create_app(config, alert_store, *mock_monitors)
        c = TestClient(app)
        resp = c.get("/api/v1/alerts?severity=warn")
        data = resp.json()
        assert data["total"] == 1
        assert data["alerts"][0]["severity"] == "warn"


class TestConfigEndpoint:
    def test_post_config_updates_monitors(self, alert_store, mock_monitors, config):
        sys_mon, proc_mon, usb_mon = mock_monitors
        app, _ = create_app(config, alert_store, sys_mon, proc_mon, usb_mon)
        c = TestClient(app)
        resp = c.post("/api/v1/config", json={
            "process": {"whitelist": ["notepad.exe"]},
            "usb": {"blocklist": ["VID_0781"]}
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        proc_mon.update_config.assert_called_once()
        usb_mon.update_config.assert_called_once()
