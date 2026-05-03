import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch, AsyncMock
import io
import asyncio


def test_app_prints_speech_detected():
    """Test that VoiceNodeApplication prints 'Speech detected' on speech start."""
    mock_sd = MagicMock()
    mock_webrtcvad = MagicMock()
    mock_transcriber = MagicMock()
    
    mock_frame_data = MagicMock()
    mock_frame_data.tobytes.return_value = b"speech_audio"
    mock_sd.read.return_value = (mock_frame_data, False)
    mock_sd.InputStream.return_value.__enter__ = MagicMock()
    mock_sd.InputStream.return_value.__exit__ = MagicMock(return_value=False)
    
    mock_vad = MagicMock()
    mock_vad.is_speech.return_value = True
    mock_webrtcvad.Vad.return_value = mock_vad
    
    with patch.dict("sys.modules", {"sounddevice": mock_sd, "webrtcvad": mock_webrtcvad}):
        from voicenode.core import VoiceNodeApplication
        from voicenode.adapters.json_config_adapter import JsonConfigAdapter
        
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.json"
            config_adapter = JsonConfigAdapter(str(config_path))
            config_adapter.create_default()
            
            captured_output = io.StringIO()
            with patch("sys.stdout", captured_output):
                app = VoiceNodeApplication(config_adapter=config_adapter, transcriber=mock_transcriber)
                
                def stop_after_one_frame():
                    from voicenode.ports import AudioFrame
                    frame = AudioFrame(data=b"speech", timestamp_ms=0)
                    event = app.process_frame(frame)
                    app.stop()
                    return event
                
                stop_after_one_frame()
            
            output = captured_output.getvalue()
            assert "Speech detected" in output


def test_app_prints_speech_boundary():
    """Test that VoiceNodeApplication prints 'Speech boundary' on silence."""
    mock_webrtcvad = MagicMock()
    mock_vad = MagicMock()
    mock_transcriber = MagicMock()
    mock_transcriber.transcribe.return_value = "test"
    
    mock_vad.is_speech.return_value = False
    mock_webrtcvad.Vad.return_value = mock_vad
    
    with patch.dict("sys.modules", {"webrtcvad": mock_webrtcvad}):
        from voicenode.core import VoiceNodeApplication
        from voicenode.ports import AudioFrame, VADState
        from voicenode.adapters.json_config_adapter import JsonConfigAdapter
        
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.json"
            config_adapter = JsonConfigAdapter(str(config_path))
            config_adapter.create_default()
            
            captured_output = io.StringIO()
            with patch("sys.stdout", captured_output):
                app = VoiceNodeApplication(config_adapter=config_adapter, transcriber=mock_transcriber)
                
                app.vad_tracker.set_state(VADState.SPEECH)
                
                for i in range(9):
                    frame = AudioFrame(data=b"silence", timestamp_ms=100 + i * 100)
                    app.process_frame(frame)
            
            output = captured_output.getvalue()
            assert "Speech boundary" in output


def test_sends_utterance_when_connected():
    """Test that utterance message is sent when transcription completes and connected."""
    mock_transcriber = MagicMock()
    mock_transcriber.transcribe.return_value = "hello world"
    
    mock_server = MagicMock()
    mock_server.send = AsyncMock()
    mock_server.is_connected = MagicMock(return_value=True)
    
    mock_webrtcvad = MagicMock()
    mock_vad = MagicMock()
    mock_vad.is_speech.side_effect = [True, True, False, False, False, False, False, False, False, False, False]
    mock_webrtcvad.Vad.return_value = mock_vad
    
    with patch.dict("sys.modules", {"webrtcvad": mock_webrtcvad}):
        from voicenode.ports import AudioFrame
        from voicenode.core import VoiceNodeApplication
        from voicenode.adapters.json_config_adapter import JsonConfigAdapter
        
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.json"
            config_adapter = JsonConfigAdapter(str(config_path))
            config_adapter.create_default()
            
            app = VoiceNodeApplication(
                config_adapter=config_adapter, 
                transcriber=mock_transcriber,
                server=mock_server
            )
            
            for i in range(11):
                frame = AudioFrame(data=f"audio_{i}".encode(), timestamp_ms=i * 100)
                app.process_frame(frame)
            
            import time
            time.sleep(0.1)
            
            mock_server.send.assert_called()
            call_args = mock_server.send.call_args[0][0]
            assert call_args["type"] == "utterance"
            assert call_args["text"] == "hello world"


def test_skips_empty_transcriptions():
    """Test that empty transcriptions are not sent to server."""
    mock_transcriber = MagicMock()
    mock_transcriber.transcribe.return_value = ""
    
    mock_server = MagicMock()
    mock_server.send = AsyncMock()
    mock_server.is_connected = MagicMock(return_value=True)
    
    mock_webrtcvad = MagicMock()
    mock_vad = MagicMock()
    mock_vad.is_speech.side_effect = [True, True, False, False, False, False, False, False, False, False, False]
    mock_webrtcvad.Vad.return_value = mock_vad
    
    mock_structlog = MagicMock()
    mock_logger = MagicMock()
    mock_structlog.get_logger.return_value = mock_logger
    
    with patch.dict("sys.modules", {"webrtcvad": mock_webrtcvad, "structlog": mock_structlog}):
        from voicenode.ports import AudioFrame
        from voicenode.core import VoiceNodeApplication
        from voicenode.adapters.json_config_adapter import JsonConfigAdapter
        
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.json"
            config_adapter = JsonConfigAdapter(str(config_path))
            config_adapter.create_default()
            
            app = VoiceNodeApplication(
                config_adapter=config_adapter,
                transcriber=mock_transcriber,
                server=mock_server
            )
            
            for i in range(11):
                frame = AudioFrame(data=f"audio_{i}".encode(), timestamp_ms=i * 100)
                app.process_frame(frame)
            
            import time
            time.sleep(0.1)
            
            mock_server.send.assert_not_called()


def test_queues_utterance_when_disconnected():
    """Test that utterances are queued when disconnected."""
    mock_transcriber = MagicMock()
    mock_transcriber.transcribe.return_value = "hello world"
    
    mock_server = MagicMock()
    mock_server.send = AsyncMock()
    mock_server.is_connected = MagicMock(return_value=False)
    
    mock_webrtcvad = MagicMock()
    mock_vad = MagicMock()
    mock_vad.is_speech.side_effect = [True, True, False, False, False, False, False, False, False, False, False]
    mock_webrtcvad.Vad.return_value = mock_vad
    
    with patch.dict("sys.modules", {"webrtcvad": mock_webrtcvad}):
        from voicenode.ports import AudioFrame
        from voicenode.core import VoiceNodeApplication
        from voicenode.adapters.json_config_adapter import JsonConfigAdapter
        
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.json"
            config_adapter = JsonConfigAdapter(str(config_path))
            config_adapter.create_default()
            
            app = VoiceNodeApplication(
                config_adapter=config_adapter,
                transcriber=mock_transcriber,
                server=mock_server
            )
            
            for i in range(11):
                frame = AudioFrame(data=f"audio_{i}".encode(), timestamp_ms=i * 100)
                app.process_frame(frame)
            
            import time
            time.sleep(0.1)
            
            assert "hello world" in app.pending_utterances
            mock_server.send.assert_not_called()


def test_flushes_queue_on_reconnect():
    """Test that queued utterances are sent when connection is restored."""
    mock_transcriber = MagicMock()
    mock_transcriber.transcribe.return_value = "hello world"
    
    mock_server = MagicMock()
    mock_server.send = AsyncMock()
    mock_server.is_connected = MagicMock(side_effect=[False, True])
    
    mock_webrtcvad = MagicMock()
    mock_vad = MagicMock()
    mock_vad.is_speech.side_effect = [True, True, False, False, False, False, False, False, False, False, False]
    mock_webrtcvad.Vad.return_value = mock_vad
    
    with patch.dict("sys.modules", {"webrtcvad": mock_webrtcvad}):
        from voicenode.ports import AudioFrame
        from voicenode.core import VoiceNodeApplication
        from voicenode.adapters.json_config_adapter import JsonConfigAdapter
        
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.json"
            config_adapter = JsonConfigAdapter(str(config_path))
            config_adapter.create_default()
            
            app = VoiceNodeApplication(
                config_adapter=config_adapter,
                transcriber=mock_transcriber,
                server=mock_server
            )
            
            for i in range(11):
                frame = AudioFrame(data=f"audio_{i}".encode(), timestamp_ms=i * 100)
                app.process_frame(frame)
            
            import time
            time.sleep(0.1)
            
            assert len(app.pending_utterances) == 1
            
            asyncio.run(app.flush_pending_utterances())
            
            mock_server.send.assert_called()
            call_args = mock_server.send.call_args[0][0]
            assert call_args["type"] == "utterance"
            assert call_args["text"] == "hello world"