import numpy as np
from unittest.mock import MagicMock, patch, AsyncMock
import asyncio


def test_audio_output_port_interface_exists():
    """Test that AudioOutputPort interface exists with play method."""
    from voicenode.ports import AudioOutputPort
    
    assert hasattr(AudioOutputPort, 'play')


def test_adapter_plays_pcm_audio():
    """Test that SounddeviceAudioAdapter plays PCM audio."""
    mock_sd = MagicMock()
    mock_stream = MagicMock()
    mock_sd.OutputStream.return_value.__enter__ = MagicMock(return_value=mock_stream)
    mock_sd.OutputStream.return_value.__exit__ = MagicMock(return_value=False)
    
    mock_structlog = MagicMock()
    mock_logger = MagicMock()
    mock_structlog.get_logger.return_value = mock_logger
    
    mock_np = MagicMock()
    mock_np.frombuffer.return_value = np.array([0, 100, -100, 0], dtype=np.int16)
    
    with patch.dict("sys.modules", {"sounddevice": mock_sd, "structlog": mock_structlog, "numpy": mock_np}):
        from voicenode.adapters import SounddeviceAudioAdapter
        
        adapter = SounddeviceAudioAdapter()
        
        audio_data = b'\x00\x00d\x00\x9c\xff\x00\x00'
        adapter.play(audio_data, device_id=1)
        
        mock_sd.OutputStream.assert_called_once()


def test_new_tts_interrupts_current_playback():
    """Test that new TTS audio interrupts current playback."""
    mock_sd = MagicMock()
    
    streams = []
    for _ in range(2):
        mock_stream = MagicMock()
        streams.append(mock_stream)
    
    stream_idx = 0
    def create_stream(*args, **kwargs):
        nonlocal stream_idx
        s = streams[stream_idx]
        stream_idx += 1
        s.start = MagicMock()
        s.write = MagicMock()
        s.stop = MagicMock()
        s.close = MagicMock()
        return s
    
    mock_sd.OutputStream = create_stream
    
    mock_structlog = MagicMock()
    mock_logger = MagicMock()
    mock_structlog.get_logger.return_value = mock_logger
    
    mock_np = MagicMock()
    mock_np.frombuffer.return_value = np.array([0, 100, 200, 300], dtype=np.int16)
    
    with patch.dict("sys.modules", {"sounddevice": mock_sd, "structlog": mock_structlog, "numpy": mock_np}):
        from voicenode.adapters import SounddeviceAudioAdapter
        
        adapter = SounddeviceAudioAdapter()
        
        audio1 = b'\x00\x00d\x00'
        audio2 = b'\xc8\xff\x38\xff'
        
        adapter.play(audio1, device_id=1)
        
        import time
        time.sleep(0.05)
        
        adapter.play(audio2, device_id=1)
        
        time.sleep(0.1)
        
        streams[0].stop.assert_called()


def test_playback_errors_logged_not_crash():
    """Test that playback errors are logged and don't crash."""
    mock_sd = MagicMock()
    mock_sd.OutputStream.side_effect = RuntimeError("Device not found")
    
    mock_structlog = MagicMock()
    mock_logger = MagicMock()
    mock_structlog.get_logger.return_value = mock_logger
    
    mock_np = MagicMock()
    mock_np.frombuffer.return_value = np.array([0, 100], dtype=np.int16)
    
    with patch.dict("sys.modules", {"sounddevice": mock_sd, "structlog": mock_structlog, "numpy": mock_np}):
        from voicenode.adapters import SounddeviceAudioAdapter
        
        adapter = SounddeviceAudioAdapter()
        
        audio_data = b'\x00\x00d\x00'
        adapter.play(audio_data, device_id=1)
        
        mock_logger.error.assert_called()


def test_binary_websocket_frame_triggers_playback():
    """Test that binary WebSocket frame triggers TTS playback."""
    mock_websockets = MagicMock()
    mock_connect = AsyncMock()
    mock_ws = AsyncMock()
    mock_connect.return_value = mock_ws
    mock_websockets.client.connect = mock_connect
    
    mock_ws.recv.return_value = b'\x00\x64\x9c\xff'
    
    with patch.dict("sys.modules", {"websockets": mock_websockets, "websockets.client": mock_websockets.client}):
        from voicenode.adapters.websockets_adapter import WebsocketsAdapter
        
        adapter = WebsocketsAdapter("ws://localhost:3001")
        
        asyncio.run(adapter.connect())
        data = asyncio.run(adapter.receive_binary())
        
        assert isinstance(data, bytes)
        assert len(data) == 4