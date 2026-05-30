"""Tests for agent.backend_client — BackendClient WebSocket client."""

import sys
import json
import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch, call

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from agent.backend_client import BackendClient


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def client():
    """Create a BackendClient with test parameters."""
    return BackendClient(
        host="127.0.0.1",
        port=9999,
        device_id="test-device-001",
        device_name="Test PC",
    )


# ---------------------------------------------------------------------------
# Registration on connect
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_register_on_connect(client):
    """Mock websockets.connect, verify register message sent."""
    mock_ws = AsyncMock()
    mock_ws.__aiter__.return_value = []  # no incoming messages

    async def fake_connect(url):
        return mock_ws

    with patch("agent.backend_client.websockets.connect", side_effect=fake_connect):
        # Start run() as a task so we can cancel it after the register message
        task = asyncio.create_task(client.run())
        # Give it a moment to connect and send register
        await asyncio.sleep(0.05)
        await client.stop()
        await task

    # Verify connect was called with correct URL
    assert mock_ws.send.call_count >= 1
    register_call = mock_ws.send.call_args_list[0]
    sent_json = json.loads(register_call[0][0])
    assert sent_json["type"] == "register"
    assert sent_json["deviceId"] == "test-device-001"
    assert sent_json["name"] == "Test PC"


# ---------------------------------------------------------------------------
# Send metrics / alerts
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_send_metrics(client):
    """Verify send_metrics sends {"type": "metrics", "data": ...} format."""
    mock_ws = AsyncMock()
    client._ws = mock_ws
    client._connected = True

    await client.send_metrics({"cpu": 50.0, "memory": 70.0})

    mock_ws.send.assert_called_once()
    sent_json = json.loads(mock_ws.send.call_args[0][0])
    assert sent_json["type"] == "metrics"
    assert sent_json["data"] == {"cpu": 50.0, "memory": 70.0}


@pytest.mark.asyncio
async def test_send_alert(client):
    """Verify send_alert sends {"type": "alert", "data": ...} format."""
    mock_ws = AsyncMock()
    client._ws = mock_ws
    client._connected = True

    await client.send_alert({"alert_id": "abc", "message": "test"})

    mock_ws.send.assert_called_once()
    sent_json = json.loads(mock_ws.send.call_args[0][0])
    assert sent_json["type"] == "alert"
    assert sent_json["data"] == {"alert_id": "abc", "message": "test"}


@pytest.mark.asyncio
async def test_send_metrics_when_not_connected(client):
    """send_metrics should be a no-op when not connected."""
    client._connected = False
    await client.send_metrics({"cpu": 50})
    # Nothing should happen, no exception


@pytest.mark.asyncio
async def test_send_alert_when_not_connected(client):
    """send_alert should be a no-op when not connected."""
    client._connected = False
    await client.send_alert({"msg": "x"})
    # Nothing should happen, no exception


# ---------------------------------------------------------------------------
# Command handler
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_command_handler_invoked(client):
    """Simulate incoming command, verify handler called with (action, payload)."""
    handler_calls = []

    def handler(action, payload):
        handler_calls.append((action, payload))
        return {"result": "ok"}

    client.set_command_handler(handler)

    mock_ws = AsyncMock()
    client._ws = mock_ws
    client._connected = True

    # Simulate incoming command message via _on_message
    await client._on_message(json.dumps({
        "type": "command",
        "action": "kill_process",
        "payload": {"pid": 1234},
    }))

    assert len(handler_calls) == 1
    assert handler_calls[0] == ("kill_process", {"pid": 1234})

    # Verify command_result was sent back
    # Find the command_result send call
    result_sent = False
    for call_args in mock_ws.send.call_args_list:
        msg = json.loads(call_args[0][0])
        if msg.get("type") == "command_result":
            assert msg["action"] == "kill_process"
            assert msg["result"] == {"result": "ok"}
            result_sent = True
    assert result_sent, "command_result should have been sent"


@pytest.mark.asyncio
async def test_command_no_handler(client):
    """When no handler is set, commands return error result."""
    mock_ws = AsyncMock()
    client._ws = mock_ws
    client._connected = True

    await client._on_message(json.dumps({
        "type": "command",
        "action": "unknown_cmd",
        "payload": {},
    }))

    # Check command_result sent with error
    result_sent = False
    for call_args in mock_ws.send.call_args_list:
        msg = json.loads(call_args[0][0])
        if msg.get("type") == "command_result":
            assert "error" in msg["result"]
            result_sent = True
    assert result_sent


# ---------------------------------------------------------------------------
# Ping / pong
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ping_pong(client):
    """Verify incoming ping triggers pong response."""
    mock_ws = AsyncMock()
    client._ws = mock_ws
    client._connected = True

    await client._on_message(json.dumps({"type": "ping"}))

    pong_sent = False
    for call_args in mock_ws.send.call_args_list:
        msg = json.loads(call_args[0][0])
        if msg.get("type") == "pong":
            pong_sent = True
    assert pong_sent, "pong should have been sent"


# ---------------------------------------------------------------------------
# Stop
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_stop(client):
    """Verify stop() closes connection."""
    mock_ws = AsyncMock()
    client._ws = mock_ws
    client._connected = True
    client._running = True

    await client.stop()

    mock_ws.close.assert_called_once()
    assert client._connected is False
    assert client._running is False


# ---------------------------------------------------------------------------
# Connected property
# ---------------------------------------------------------------------------


def test_connected_property(client):
    """connected property reflects internal _connected flag."""
    assert client.connected is False
    client._connected = True
    assert client.connected is True


# ---------------------------------------------------------------------------
# Unknown message types
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_unknown_message_type(client):
    """Unknown message types should not cause errors."""
    mock_ws = AsyncMock()
    client._ws = mock_ws
    client._connected = True

    # Should not raise
    await client._on_message(json.dumps({"type": "bogus", "data": 1}))


@pytest.mark.asyncio
async def test_invalid_json(client):
    """Invalid JSON should not crash the message handler."""
    mock_ws = AsyncMock()
    client._ws = mock_ws
    client._connected = True

    # Should not raise
    await client._on_message("not valid json {{{")
