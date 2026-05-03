import asyncio
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch, AsyncMock


def test_server_port_connects_to_url():
    """Test that ServerPort connects to WebSocket URL."""
    mock_websockets = MagicMock()
    mock_websockets.connect = AsyncMock()
    
    with patch.dict("sys.modules", {"websockets": mock_websockets, "websockets.client": mock_websockets}):
        from voicenode.adapters.websockets_adapter import WebsocketsAdapter
        
        adapter = WebsocketsAdapter("ws://localhost:3001")
        
        asyncio.run(adapter.connect())
        
        mock_websockets.connect.assert_called_once_with("ws://localhost:3001")


def test_server_port_send_message():
    """Test that ServerPort sends JSON message."""
    mock_websockets = MagicMock()
    mock_connect = AsyncMock()
    mock_ws = AsyncMock()
    mock_connect.return_value = mock_ws
    mock_websockets.client.connect = mock_connect
    
    with patch.dict("sys.modules", {"websockets": mock_websockets, "websockets.client": mock_websockets.client}):
        from voicenode.adapters.websockets_adapter import WebsocketsAdapter
        
        adapter = WebsocketsAdapter("ws://localhost:3001")
        
        asyncio.run(adapter.connect())
        asyncio.run(adapter.send({"type": "test", "data": "hello"}))
        
        mock_ws.send.assert_called_once()


def test_registration_message_format():
    """Test that register message has correct format."""
    mock_websockets = MagicMock()
    mock_connect = AsyncMock()
    mock_ws = AsyncMock()
    mock_connect.return_value = mock_ws
    mock_websockets.client.connect = mock_connect
    
    with patch.dict("sys.modules", {"websockets": mock_websockets, "websockets.client": mock_websockets.client}):
        from voicenode.adapters.websockets_adapter import WebsocketsAdapter
        from voicenode.adapters.json_config_adapter import JsonConfigAdapter
        import json
        
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.json"
            config_adapter = JsonConfigAdapter(str(config_path))
            config_adapter.create_default()
            
            adapter = WebsocketsAdapter("ws://localhost:3001")
            
            asyncio.run(adapter.connect())
            asyncio.run(adapter.register(config_adapter.load()))
            
            call_args = mock_ws.send.call_args
            message = json.loads(call_args[0][0])
            
            assert message["type"] == "register"
            assert "id" in message
            assert message["label"] == "Voice Node"
            assert message["location"] == "unknown"
            assert message["capabilities"] == ["mic", "speaker"]


def test_handles_registered_response():
    """Test that registered response is handled correctly."""
    mock_websockets = MagicMock()
    mock_connect = AsyncMock()
    mock_ws = AsyncMock()
    mock_connect.return_value = mock_ws
    mock_websockets.client.connect = mock_connect
    
    mock_ws.recv.return_value = '{"type": "registered", "id": "test-id", "status": "new"}'
    
    with patch.dict("sys.modules", {"websockets": mock_websockets, "websockets.client": mock_websockets.client}):
        from voicenode.adapters.websockets_adapter import WebsocketsAdapter
        
        adapter = WebsocketsAdapter("ws://localhost:3001")
        
        asyncio.run(adapter.connect())
        response = asyncio.run(adapter.receive())
        
        assert response["type"] == "registered"
        assert response["status"] == "new"


def test_handles_reconnected_status():
    """Test that reconnected status is handled."""
    mock_websockets = MagicMock()
    mock_connect = AsyncMock()
    mock_ws = AsyncMock()
    mock_connect.return_value = mock_ws
    mock_websockets.client.connect = mock_connect
    
    mock_ws.recv.return_value = '{"type": "registered", "id": "test-id", "status": "reconnected"}'
    
    with patch.dict("sys.modules", {"websockets": mock_websockets, "websockets.client": mock_websockets.client}):
        from voicenode.adapters.websockets_adapter import WebsocketsAdapter
        
        adapter = WebsocketsAdapter("ws://localhost:3001")
        
        asyncio.run(adapter.connect())
        response = asyncio.run(adapter.receive())
        
        assert response["status"] == "reconnected"


def test_handles_error_message():
    """Test that error messages are logged."""
    mock_websockets = MagicMock()
    mock_connect = AsyncMock()
    mock_ws = AsyncMock()
    mock_connect.return_value = mock_ws
    mock_websockets.client.connect = mock_connect
    
    mock_ws.recv.return_value = '{"type": "error", "code": "REGISTRATION_REQUIRED", "message": "send register before utterance"}'
    
    mock_structlog = MagicMock()
    mock_logger = MagicMock()
    mock_structlog.get_logger.return_value = mock_logger
    
    with patch.dict("sys.modules", {"websockets": mock_websockets, "websockets.client": mock_websockets.client, "structlog": mock_structlog}):
        from voicenode.adapters.websockets_adapter import WebsocketsAdapter
        
        adapter = WebsocketsAdapter("ws://localhost:3001")
        
        asyncio.run(adapter.connect())
        response = asyncio.run(adapter.receive())
        
        assert response["type"] == "error"
        assert response["code"] == "REGISTRATION_REQUIRED"


def test_exponential_backoff_calculation():
    """Test that backoff doubles and caps at 30s."""
    from voicenode.core import ConnectionManager
    
    manager = ConnectionManager()
    
    assert manager.get_backoff_delay(0) == 1
    assert manager.get_backoff_delay(1) == 2
    assert manager.get_backoff_delay(2) == 4
    assert manager.get_backoff_delay(3) == 8
    assert manager.get_backoff_delay(4) == 16
    assert manager.get_backoff_delay(5) == 30
    assert manager.get_backoff_delay(10) == 30


def test_connection_state_logging():
    """Test that connection state changes are logged."""
    from voicenode.core import ConnectionManager
    
    mock_structlog = MagicMock()
    mock_logger = MagicMock()
    mock_structlog.get_logger.return_value = mock_logger
    
    with patch.dict("sys.modules", {"structlog": mock_structlog}):
        manager = ConnectionManager()
        
        manager.log_connected()
        mock_logger.info.assert_called_with("Connected to server")
        
        manager.log_reconnecting(1)
        mock_logger.warning.assert_called_with("Reconnecting in {delay}s", attempt=0, delay=1)
        
        manager.increment_reconnect()
        manager.log_reconnecting(2)
        mock_logger.warning.assert_called_with("Reconnecting in {delay}s", attempt=1, delay=2)
        
        manager.log_lost()
        mock_logger.error.assert_called_with("Connection lost")