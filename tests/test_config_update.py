import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch, AsyncMock
import asyncio


def test_config_update_handler_exists():
    """Test that ConfigUpdateHandler class exists."""
    from voicenode.core import ConfigUpdateHandler
    
    handler = ConfigUpdateHandler(config_adapter=MagicMock())
    assert handler is not None


def test_handles_config_update_message():
    """Test that handler processes config_update message."""
    mock_structlog = MagicMock()
    mock_logger = MagicMock()
    mock_structlog.get_logger.return_value = mock_logger
    
    with patch.dict("sys.modules", {"structlog": mock_structlog}):
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.json"
            
            from voicenode.adapters.json_config_adapter import JsonConfigAdapter
            config_adapter = JsonConfigAdapter(str(config_path))
            config_adapter.create_default()
            
            from voicenode.core import ConfigUpdateHandler
            
            handler = ConfigUpdateHandler(config_adapter=config_adapter)
            
            message = {
                "type": "config_update",
                "label": "Kitchen Node",
                "location": "kitchen"
            }
            
            asyncio.run(handler.handle_config_update(message))
            
            updated_config = config_adapter.load()
            assert updated_config.label == "Kitchen Node"
            assert updated_config.location == "kitchen"


def test_sends_acknowledgment_success():
    """Test that handler sends config_updated acknowledgment."""
    mock_server = MagicMock()
    mock_server.send = AsyncMock()
    
    mock_structlog = MagicMock()
    mock_logger = MagicMock()
    mock_structlog.get_logger.return_value = mock_logger
    
    with patch.dict("sys.modules", {"structlog": mock_structlog}):
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.json"
            
            from voicenode.adapters.json_config_adapter import JsonConfigAdapter
            config_adapter = JsonConfigAdapter(str(config_path))
            config_adapter.create_default()
            
            from voicenode.core import ConfigUpdateHandler
            
            handler = ConfigUpdateHandler(config_adapter=config_adapter, server=mock_server)
            
            message = {
                "type": "config_update",
                "label": "Bedroom Node"
            }
            
            asyncio.run(handler.handle_config_update(message))
            
            mock_server.send.assert_called()
            call_args = mock_server.send.call_args[0][0]
            assert call_args["type"] == "config_updated"
            assert call_args["success"] is True


def test_invalid_update_sends_failure():
    """Test that invalid update sends failure acknowledgment."""
    mock_server = MagicMock()
    mock_server.send = AsyncMock()
    
    mock_audio_adapter = MagicMock()
    mock_audio_adapter.list_devices.return_value = []
    
    mock_structlog = MagicMock()
    mock_logger = MagicMock()
    mock_structlog.get_logger.return_value = mock_logger
    
    with patch.dict("sys.modules", {"structlog": mock_structlog}):
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.json"
            
            from voicenode.adapters.json_config_adapter import JsonConfigAdapter
            config_adapter = JsonConfigAdapter(str(config_path))
            config_adapter.create_default()
            
            from voicenode.core import ConfigUpdateHandler
            
            handler = ConfigUpdateHandler(
                config_adapter=config_adapter,
                server=mock_server,
                audio_adapter=mock_audio_adapter
            )
            
            message = {
                "type": "config_update",
                "devices": {"input": 999, "output": 888}
            }
            
            asyncio.run(handler.handle_config_update(message))
            
            mock_server.send.assert_called()
            call_args = mock_server.send.call_args[0][0]
            assert call_args["type"] == "config_updated"
            assert call_args["success"] is False
            assert "error" in call_args


def test_device_change_triggers_callback():
    """Test that device change triggers restart callback."""
    mock_restart_callback = MagicMock()
    
    mock_structlog = MagicMock()
    mock_logger = MagicMock()
    mock_structlog.get_logger.return_value = mock_logger
    
    with patch.dict("sys.modules", {"structlog": mock_structlog}):
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.json"
            
            from voicenode.adapters.json_config_adapter import JsonConfigAdapter
            config_adapter = JsonConfigAdapter(str(config_path))
            config_adapter.create_default()
            
            from voicenode.core import ConfigUpdateHandler
            
            handler = ConfigUpdateHandler(
                config_adapter=config_adapter,
                on_device_change=mock_restart_callback
            )
            
            message = {
                "type": "config_update",
                "devices": {"input": 2, "output": 3}
            }
            
            asyncio.run(handler.handle_config_update(message))
            
            mock_restart_callback.assert_called()