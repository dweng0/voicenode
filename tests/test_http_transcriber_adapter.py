import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch
import httpx

from voicenode.ports import AudioFrame


def test_config_supports_stt_mode_and_server_http_url():
    """Config schema should include stt_mode and server_http_url fields."""
    from voicenode.core import NodeConfig
    from voicenode.adapters.json_config_adapter import JsonConfigAdapter
    
    with tempfile.TemporaryDirectory() as tmpdir:
        config_path = Path(tmpdir) / "config.json"
        adapter = JsonConfigAdapter(str(config_path))
        
        adapter.create_default()
        config = adapter.load()
        
        assert hasattr(config, 'stt_mode')
        assert config.stt_mode == "local"
        assert hasattr(config, 'server_http_url')
        assert config.server_http_url is None


def test_http_transcriber_posts_pcm_to_server():
    """HttpTranscriberAdapter should POST PCM audio to server and return transcript."""
    from voicenode.adapters.http_transcriber_adapter import HttpTranscriberAdapter, TranscriberError
    
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"transcript": "turn on the lights", "nodeId": "test-node"}
    
    with patch("httpx.post") as mock_post:
        mock_post.return_value = mock_response
        
        adapter = HttpTranscriberAdapter(
            server_http_url="http://192.168.1.112:3000",
            node_id="test-node"
        )
        
        frames = [
            AudioFrame(data=b"audio_chunk_1", timestamp_ms=0),
            AudioFrame(data=b"audio_chunk_2", timestamp_ms=100),
        ]
        
        result = adapter.transcribe(frames)
        
        assert result == "turn on the lights"
        mock_post.assert_called_once()
        call_args = mock_post.call_args
        assert call_args[0][0] == "http://192.168.1.112:3000/api/voice/transcribe"
        assert call_args[1]["headers"]["X-Node-Id"] == "test-node"
        assert call_args[1]["headers"]["Content-Type"] == "application/octet-stream"
        assert call_args[1]["content"] == b"audio_chunk_1audio_chunk_2"


def test_http_transcriber_includes_node_id_header():
    """HttpTranscriberAdapter should include X-Node-Id header in request."""
    from voicenode.adapters.http_transcriber_adapter import HttpTranscriberAdapter
    
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"transcript": "test", "nodeId": "node-123"}
    
    with patch("httpx.post") as mock_post:
        mock_post.return_value = mock_response
        
        adapter = HttpTranscriberAdapter(
            server_http_url="http://localhost:3000",
            node_id="node-123"
        )
        
        frames = [AudioFrame(data=b"audio", timestamp_ms=0)]
        adapter.transcribe(frames)
        
        assert mock_post.call_args[1]["headers"]["X-Node-Id"] == "node-123"


def test_http_transcriber_handles_connection_error():
    """HttpTranscriberAdapter should raise TranscriberError on connection failure."""
    from voicenode.adapters.http_transcriber_adapter import HttpTranscriberAdapter, TranscriberError
    
    with patch("httpx.post") as mock_post:
        mock_post.side_effect = httpx.ConnectError("Connection refused")
        
        adapter = HttpTranscriberAdapter(
            server_http_url="http://localhost:3000",
            node_id="test-node"
        )
        
        frames = [AudioFrame(data=b"audio", timestamp_ms=0)]
        
        try:
            adapter.transcribe(frames)
            assert False, "Should have raised TranscriberError"
        except TranscriberError as e:
            assert "Failed to connect" in str(e)


def test_http_transcriber_handles_timeout():
    """HttpTranscriberAdapter should raise TranscriberError on timeout."""
    from voicenode.adapters.http_transcriber_adapter import HttpTranscriberAdapter, TranscriberError
    
    with patch("httpx.post") as mock_post:
        mock_post.side_effect = httpx.TimeoutException("Timeout")
        
        adapter = HttpTranscriberAdapter(
            server_http_url="http://localhost:3000",
            node_id="test-node",
            timeout=5.0
        )
        
        frames = [AudioFrame(data=b"audio", timestamp_ms=0)]
        
        try:
            adapter.transcribe(frames)
            assert False, "Should have raised TranscriberError"
        except TranscriberError as e:
            assert "timed out" in str(e)


def test_http_transcriber_handles_4xx_error():
    """HttpTranscriberAdapter should raise TranscriberError on 4xx response."""
    from voicenode.adapters.http_transcriber_adapter import HttpTranscriberAdapter, TranscriberError
    
    mock_response = MagicMock()
    mock_response.status_code = 400
    
    with patch("httpx.post") as mock_post:
        mock_post.return_value = mock_response
        
        adapter = HttpTranscriberAdapter(
            server_http_url="http://localhost:3000",
            node_id="test-node"
        )
        
        frames = [AudioFrame(data=b"audio", timestamp_ms=0)]
        
        try:
            adapter.transcribe(frames)
            assert False, "Should have raised TranscriberError"
        except TranscriberError as e:
            assert "HTTP 400" in str(e)


def test_http_transcriber_handles_5xx_error():
    """HttpTranscriberAdapter should raise TranscriberError on 5xx response."""
    from voicenode.adapters.http_transcriber_adapter import HttpTranscriberAdapter, TranscriberError
    
    mock_response = MagicMock()
    mock_response.status_code = 500
    
    with patch("httpx.post") as mock_post:
        mock_post.return_value = mock_response
        
        adapter = HttpTranscriberAdapter(
            server_http_url="http://localhost:3000",
            node_id="test-node"
        )
        
        frames = [AudioFrame(data=b"audio", timestamp_ms=0)]
        
        try:
            adapter.transcribe(frames)
            assert False, "Should have raised TranscriberError"
        except TranscriberError as e:
            assert "HTTP 500" in str(e)


def test_http_transcriber_returns_empty_string_on_empty_transcript():
    """HttpTranscriberAdapter should return empty string when transcript is empty."""
    from voicenode.adapters.http_transcriber_adapter import HttpTranscriberAdapter
    
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"transcript": "", "nodeId": "test-node"}
    
    with patch("httpx.post") as mock_post:
        mock_post.return_value = mock_response
        
        adapter = HttpTranscriberAdapter(
            server_http_url="http://localhost:3000",
            node_id="test-node"
        )
        
        frames = [AudioFrame(data=b"audio", timestamp_ms=0)]
        result = adapter.transcribe(frames)
        
        assert result == ""


def test_app_uses_http_transcriber_when_stt_mode_remote():
    """VoiceNodeApplication should use HttpTranscriberAdapter when stt_mode='remote'."""
    from voicenode.core import VoiceNodeApplication
    from voicenode.adapters.json_config_adapter import JsonConfigAdapter
    from voicenode.adapters.http_transcriber_adapter import HttpTranscriberAdapter
    
    mock_webrtcvad = MagicMock()
    mock_vad = MagicMock()
    mock_webrtcvad.Vad.return_value = mock_vad
    
    with patch.dict("sys.modules", {"webrtcvad": mock_webrtcvad}):
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.json"
            adapter = JsonConfigAdapter(str(config_path))
            
            config = adapter.create_default()
            config.stt_mode = "remote"
            config.server_http_url = "http://localhost:3000"
            adapter.save(config)
            
            app = VoiceNodeApplication(config_adapter=adapter)
            
            assert isinstance(app.transcriber, HttpTranscriberAdapter)
            assert app.transcriber.server_http_url == "http://localhost:3000"
            assert app.transcriber.node_id == config.id


def test_app_uses_whisper_when_stt_mode_local():
    """VoiceNodeApplication should use WhisperCppAdapter when stt_mode='local'."""
    from voicenode.core import VoiceNodeApplication
    from voicenode.adapters.json_config_adapter import JsonConfigAdapter
    from voicenode.adapters.whisper_cpp_adapter import WhisperCppAdapter
    
    mock_pywhispercpp = MagicMock()
    mock_model_cls = MagicMock()
    mock_pywhispercpp.Model = mock_model_cls
    
    mock_webrtcvad = MagicMock()
    mock_vad = MagicMock()
    mock_webrtcvad.Vad.return_value = mock_vad
    
    with patch.dict("sys.modules", {"pywhispercpp": mock_pywhispercpp, "pywhispercpp.model": mock_pywhispercpp, "webrtcvad": mock_webrtcvad}):
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.json"
            adapter = JsonConfigAdapter(str(config_path))
            
            config = adapter.create_default()
            config.stt_mode = "local"
            adapter.save(config)
            
            app = VoiceNodeApplication(config_adapter=adapter)
            
            assert isinstance(app.transcriber, WhisperCppAdapter)


def test_app_raises_error_when_remote_mode_missing_http_url():
    """VoiceNodeApplication should raise error when stt_mode='remote' but no server_http_url."""
    from voicenode.core import VoiceNodeApplication
    from voicenode.adapters.json_config_adapter import JsonConfigAdapter
    
    mock_webrtcvad = MagicMock()
    mock_vad = MagicMock()
    mock_webrtcvad.Vad.return_value = mock_vad
    
    with patch.dict("sys.modules", {"webrtcvad": mock_webrtcvad}):
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.json"
            adapter = JsonConfigAdapter(str(config_path))
            
            config = adapter.create_default()
            config.stt_mode = "remote"
            config.server_http_url = None
            adapter.save(config)
            
            try:
                app = VoiceNodeApplication(config_adapter=adapter)
                assert False, "Should have raised ValueError"
            except ValueError as e:
                assert "server_http_url required" in str(e)


def test_pywhispercpp_not_imported_when_remote_mode():
    """WhisperCppAdapter should not be imported when stt_mode='remote'."""
    from voicenode.core import VoiceNodeApplication
    from voicenode.adapters.json_config_adapter import JsonConfigAdapter
    import sys
    
    mock_webrtcvad = MagicMock()
    mock_vad = MagicMock()
    mock_webrtcvad.Vad.return_value = mock_vad
    
    mock_httpx = MagicMock()
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"transcript": "test", "nodeId": "test"}
    mock_httpx.post.return_value = mock_response
    
    with patch.dict("sys.modules", {"webrtcvad": mock_webrtcvad, "httpx": mock_httpx}):
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.json"
            adapter = JsonConfigAdapter(str(config_path))
            
            config = adapter.create_default()
            config.stt_mode = "remote"
            config.server_http_url = "http://localhost:3000"
            adapter.save(config)
            
            # Ensure pywhispercpp is not in sys.modules before creating app
            if "pywhispercpp" in sys.modules:
                del sys.modules["pywhispercpp"]
            if "pywhispercpp.model" in sys.modules:
                del sys.modules["pywhispercpp.model"]
            
            app = VoiceNodeApplication(config_adapter=adapter)
            
            # Verify pywhispercpp was not imported
            assert "pywhispercpp" not in sys.modules
            assert "pywhispercpp.model" not in sys.modules