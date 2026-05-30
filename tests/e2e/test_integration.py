"""End-to-end integration tests for Patroller Backend."""

import os
import sys
import json
import time
import subprocess
import asyncio
import shutil
from pathlib import Path

import pytest
import httpx
import websockets

PROJECT_ROOT = Path(__file__).parent.parent.parent
BACKEND_DIR = PROJECT_ROOT / "backend"


def find_npx():
    """Locate npx executable."""
    npx = shutil.which("npx")
    if npx:
        return npx
    # Fallback: look for npx in common Windows locations
    candidates = [
        "C:\\Program Files\\nodejs\\npx.cmd",
        os.path.expanduser("~\\AppData\\Roaming\\npm\\npx.cmd"),
    ]
    for c in candidates:
        if os.path.exists(c):
            return c
    return "npx.cmd"


@pytest.fixture(scope="module")
def backend_server():
    """Start Backend server, yield port number, terminate on teardown."""
    npx = find_npx()
    db_path = os.path.join(str(PROJECT_ROOT), "data", "e2e_test.db")
    env = os.environ.copy()
    env["PORT"] = "3099"
    env["DB_PATH"] = db_path
    env["TAILSCALE_AUTH"] = "false"
    env["LOG_LEVEL"] = "error"

    # Clean up any previous test DB
    if os.path.exists(db_path):
        try:
            os.remove(db_path)
        except OSError:
            pass

    proc = subprocess.Popen(
        [npx, "tsx", "src/index.ts"],
        cwd=str(BACKEND_DIR),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    # Wait for server to be ready
    for attempt in range(30):
        try:
            resp = httpx.get("http://localhost:3099/api/v1/health", timeout=2)
            if resp.status_code == 200:
                break
        except (httpx.ConnectError, httpx.TimeoutException):
            pass
        time.sleep(1)
    else:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
        pytest.fail("Backend failed to start within 30 seconds")

    yield 3099

    # Cleanup — terminate entire process tree on Windows
    try:
        if sys.platform == "win32":
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                capture_output=True,
            )
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                pass
        else:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
    except Exception:
        try:
            proc.kill()
            proc.wait()
        except Exception:
            pass

    # Clean up test DB
    if os.path.exists(db_path):
        try:
            os.remove(db_path)
        except OSError:
            pass


class TestHealthEndpoint:
    """Basic health check."""

    def test_health_returns_ok(self, backend_server):
        port = backend_server
        resp = httpx.get(f"http://localhost:{port}/api/v1/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert "uptime" in data
        assert "deviceCount" in data
        assert "timestamp" in data
        assert data["deviceCount"] == 0


class TestDeviceLifecycle:
    """Device REST API CRUD."""

    def test_register_device(self, backend_server):
        port = backend_server
        resp = httpx.post(
            f"http://localhost:{port}/api/v1/devices/e2e-device/heartbeat",
            json={"name": "E2E Device", "version": "0.1.0"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "timestamp" in data

    def test_get_device(self, backend_server):
        port = backend_server
        resp = httpx.get(f"http://localhost:{port}/api/v1/devices/e2e-device")
        assert resp.status_code == 200
        device = resp.json()
        assert device["id"] == "e2e-device"
        assert device["name"] == "E2E Device"
        assert device["status"] == "online"

    def test_get_all_devices(self, backend_server):
        port = backend_server
        resp = httpx.get(f"http://localhost:{port}/api/v1/devices")
        assert resp.status_code == 200
        devices = resp.json()
        assert isinstance(devices, list)
        assert any(d["id"] == "e2e-device" for d in devices)

    def test_update_device(self, backend_server):
        port = backend_server
        resp = httpx.put(
            f"http://localhost:{port}/api/v1/devices/e2e-device",
            json={"name": "Renamed Device"},
        )
        assert resp.status_code == 200
        assert resp.json()["name"] == "Renamed Device"

    def test_get_nonexistent_device(self, backend_server):
        port = backend_server
        resp = httpx.get(f"http://localhost:{port}/api/v1/devices/no-such-device")
        assert resp.status_code == 404

    def test_delete_device(self, backend_server):
        port = backend_server
        resp = httpx.delete(f"http://localhost:{port}/api/v1/devices/e2e-device")
        assert resp.status_code == 200
        assert resp.json()["success"] is True

        # Verify deleted
        resp = httpx.get(f"http://localhost:{port}/api/v1/devices/e2e-device")
        assert resp.status_code == 404


class TestAlertFlow:
    """Alert CRUD via REST."""

    def test_post_and_query_alert(self, backend_server):
        port = backend_server

        # Register device first
        httpx.post(
            f"http://localhost:{port}/api/v1/devices/e2e-alert-device/heartbeat",
            json={"name": "Alert Tester"},
        )

        # Post alert
        resp = httpx.post(
            f"http://localhost:{port}/api/v1/devices/e2e-alert-device/alerts",
            json={
                "type": "security_test",
                "severity": "critical",
                "message": "E2E test alert",
                "details": {"test": True},
            },
        )
        assert resp.status_code == 201
        alert = resp.json()
        assert alert["type"] == "security_test"
        assert alert["severity"] == "critical"
        assert alert["deviceId"] == "e2e-alert-device"
        alert_id = alert["id"]

        # Query alerts
        resp = httpx.get(
            f"http://localhost:{port}/api/v1/alerts?deviceId=e2e-alert-device"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 1
        assert any(a["id"] == alert_id for a in data["alerts"])

    def test_acknowledge_alert(self, backend_server):
        port = backend_server

        # Get unacknowledged count
        resp = httpx.get(f"http://localhost:{port}/api/v1/alerts/unacknowledged")
        assert resp.status_code == 200
        count_before = resp.json()["count"]

        # Get first alert ID
        resp = httpx.get(f"http://localhost:{port}/api/v1/alerts?limit=1")
        assert resp.status_code == 200
        alerts = resp.json()["alerts"]
        assert len(alerts) >= 1
        alert_id = alerts[0]["id"]

        # Acknowledge it
        resp = httpx.post(
            f"http://localhost:{port}/api/v1/alerts/{alert_id}/acknowledge"
        )
        assert resp.status_code == 200
        assert resp.json()["success"] is True

        # Count should decrease
        resp = httpx.get(f"http://localhost:{port}/api/v1/alerts/unacknowledged")
        assert resp.status_code == 200
        assert resp.json()["count"] == count_before - 1


class TestWebSocket:
    """WebSocket integration tests."""

    @pytest.mark.asyncio
    async def test_agent_register_and_online_event(self, backend_server):
        port = backend_server
        async with websockets.connect(f"ws://localhost:{port}/ws") as ws:
            await ws.send(
                json.dumps(
                    {
                        "type": "register",
                        "deviceId": "ws-e2e-agent",
                        "name": "WS E2E Agent",
                    }
                )
            )
            resp = json.loads(await asyncio.wait_for(ws.recv(), timeout=5))
            assert resp["type"] == "device:online"
            assert resp["deviceId"] == "ws-e2e-agent"

            # Verify via REST
            async with httpx.AsyncClient() as client:
                r = await client.get(
                    f"http://localhost:{port}/api/v1/devices/ws-e2e-agent"
                )
                assert r.status_code == 200
                assert r.json()["status"] == "online"

    @pytest.mark.asyncio
    async def test_alert_flow_ws_to_rest(self, backend_server):
        port = backend_server
        async with websockets.connect(f"ws://localhost:{port}/ws") as ws:
            await ws.send(
                json.dumps(
                    {
                        "type": "register",
                        "deviceId": "ws-alerter",
                        "name": "WS Alerter",
                    }
                )
            )
            await asyncio.wait_for(ws.recv(), timeout=5)  # Consume online event

            await ws.send(
                json.dumps(
                    {
                        "type": "alert",
                        "data": {
                            "type": "e2e_test",
                            "severity": "warn",
                            "message": "WS to REST alert test",
                            "details": {"source": "e2e"},
                        },
                    }
                )
            )
            await asyncio.wait_for(ws.recv(), timeout=5)  # Consume alert broadcast

            # Verify via REST
            async with httpx.AsyncClient() as client:
                r = await client.get(
                    f"http://localhost:{port}/api/v1/alerts?deviceId=ws-alerter&severity=warn"
                )
                assert r.status_code == 200
                data = r.json()
                assert data["total"] >= 1
                assert any(
                    a["message"] == "WS to REST alert test" for a in data["alerts"]
                )

    @pytest.mark.asyncio
    async def test_command_relay(self, backend_server):
        port = backend_server
        async with websockets.connect(f"ws://localhost:{port}/ws") as ws:
            await ws.send(
                json.dumps(
                    {
                        "type": "register",
                        "deviceId": "cmd-agent",
                        "name": "Command Agent",
                    }
                )
            )
            await asyncio.wait_for(ws.recv(), timeout=5)  # Consume online event

            # Send command via REST relay
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    f"http://localhost:{port}/api/v1/relay/command",
                    json={
                        "deviceId": "cmd-agent",
                        "action": "ping",
                        "payload": {"id": 42},
                    },
                )
                assert resp.status_code == 201
                result = resp.json()
                assert result["delivered"] is True
                assert result["deviceId"] == "cmd-agent"
                assert result["action"] == "ping"

            # Verify the WS client received the command
            cmd = json.loads(await asyncio.wait_for(ws.recv(), timeout=5))
            assert cmd["type"] == "command"
            assert cmd["action"] == "ping"
            assert cmd["payload"]["id"] == 42


class TestMetricsFlow:
    """Metrics via REST."""

    def test_post_metrics(self, backend_server):
        port = backend_server
        httpx.post(
            f"http://localhost:{port}/api/v1/devices/metrics-device/heartbeat",
            json={"name": "Metrics Device"},
        )

        resp = httpx.post(
            f"http://localhost:{port}/api/v1/devices/metrics-device/metrics",
            json={
                "cpu": {"percent": 50.0, "perCore": [45.0, 55.0]},
                "memory": {"total": 16000000000, "used": 8000000000, "percent": 50.0},
                "disk": {"total": 500000000000, "used": 250000000000, "percent": 50.0},
                "network": {"bytesSent": 1000, "bytesRecv": 2000},
            },
        )
        assert resp.status_code == 200
        assert resp.json()["success"] is True
