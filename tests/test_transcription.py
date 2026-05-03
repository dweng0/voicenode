import tempfile
import threading
import time
from io import StringIO
from pathlib import Path
from unittest.mock import MagicMock, patch


def test_transcriber_returns_text_from_frames():
    """Test that TranscriberPort transcribes buffered audio frames to text."""
    mock_pywhispercpp = MagicMock()
    mock_model_cls = MagicMock()
    mock_model_instance = MagicMock()
    mock_segments = [MagicMock(text="Hello world")]
    mock_model_instance.transcribe.return_value = mock_segments
    mock_model_cls.return_value = mock_model_instance
    mock_pywhispercpp.Model = mock_model_cls

    with patch.dict("sys.modules", {"pywhispercpp": mock_pywhispercpp, "pywhispercpp.model": mock_pywhispercpp}):
        from voicenode.ports import AudioFrame
        from voicenode.adapters.whisper_cpp_adapter import WhisperCppAdapter

        adapter = WhisperCppAdapter(model="base.en")

        frames = [
            AudioFrame(data=b"audio_chunk_1", timestamp_ms=0),
            AudioFrame(data=b"audio_chunk_2", timestamp_ms=100),
        ]

        result = adapter.transcribe(frames)

        assert result == "Hello world"


def test_app_transcribes_on_speech_boundary():
    """Test that application transcribes buffered audio on speech boundary."""
    mock_transcriber = MagicMock()
    mock_transcriber.transcribe.return_value = "test transcription"

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

            captured_output = StringIO()
            with patch("sys.stdout", captured_output):
                app = VoiceNodeApplication(config_adapter=config_adapter, transcriber=mock_transcriber)

                for i in range(11):
                    frame = AudioFrame(data=f"audio_{i}".encode(), timestamp_ms=i * 100)
                    app.process_frame(frame)

            output = captured_output.getvalue()
            assert "test transcription" in output


def test_app_prints_transcription_with_timestamp():
    """Test that transcription is printed with timestamp format."""
    mock_transcriber = MagicMock()
    mock_transcriber.transcribe.return_value = "hello world"

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

            captured_output = StringIO()
            with patch("sys.stdout", captured_output):
                app = VoiceNodeApplication(config_adapter=config_adapter, transcriber=mock_transcriber)

                for i in range(11):
                    frame = AudioFrame(data=f"audio_{i}".encode(), timestamp_ms=i * 100)
                    app.process_frame(frame)

            output = captured_output.getvalue()
            assert "[00:00:" in output
            assert "hello world" in output


def test_app_does_not_print_empty_transcription():
    """Test that empty transcriptions are not printed to console."""
    mock_transcriber = MagicMock()
    mock_transcriber.transcribe.return_value = ""

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

            captured_output = StringIO()
            with patch("sys.stdout", captured_output):
                app = VoiceNodeApplication(config_adapter=config_adapter, transcriber=mock_transcriber)

                for i in range(11):
                    frame = AudioFrame(data=f"audio_{i}".encode(), timestamp_ms=i * 100)
                    app.process_frame(frame)

            output = captured_output.getvalue()
            assert "[00:00:" not in output


def test_transcription_runs_async():
    """Test that transcription doesn't block frame processing."""
    transcription_started = threading.Event()
    transcription_can_finish = threading.Event()
    
    def slow_transcribe(frames):
        transcription_started.set()
        transcription_can_finish.wait()
        return "async result"
    
    mock_transcriber = MagicMock()
    mock_transcriber.transcribe.side_effect = slow_transcribe

    mock_webrtcvad = MagicMock()
    mock_vad = MagicMock()
    mock_vad.is_speech.side_effect = [True, True, False, False, False, False, False, False, False, False, False, True]
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

            captured_output = StringIO()
            with patch("sys.stdout", captured_output):
                app = VoiceNodeApplication(config_adapter=config_adapter, transcriber=mock_transcriber)

                for i in range(11):
                    frame = AudioFrame(data=f"audio_{i}".encode(), timestamp_ms=i * 100)
                    app.process_frame(frame)

                transcription_started.wait(timeout=1)
                transcription_can_finish.set()
                
                time.sleep(0.1)

            output = captured_output.getvalue()
            assert transcription_started.is_set()
            assert "async result" in output