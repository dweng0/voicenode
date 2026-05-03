import io
import numpy as np
from unittest.mock import patch, MagicMock

from voicenode.cli import main


def test_monitor_command_parses_device_id():
    with patch("sys.argv", ["voicenode", "monitor", "2"]):
        with patch("voicenode.cli.get_audio_adapter") as mock_get_adapter:
            with patch("voicenode.cli.run_monitor") as mock_run_monitor:
                mock_get_adapter.return_value = MagicMock()
                main()
                mock_run_monitor.assert_called_once()
                args = mock_run_monitor.call_args[0]
                assert args[0] == 2


def test_monitor_calculates_rms_for_audio_frames():
    mock_adapter = MagicMock()
    
    audio_data = np.array([1000, -1000, 1000, -1000], dtype=np.int16).tobytes()
    
    from voicenode.ports import AudioFrame, VADState
    mock_adapter.capture_frames.return_value = iter([
        AudioFrame(data=audio_data, timestamp_ms=0),
    ])
    
    mock_adapter.list_devices.return_value = []
    
    mock_vad_tracker = MagicMock()
    mock_vad_tracker.process_frame.return_value = None
    mock_vad_tracker.current_state = VADState.SILENCE
    
    mock_transcriber = MagicMock()
    
    captured_output = io.StringIO()
    
    with patch("sys.stdout", captured_output):
        from voicenode.cli import run_monitor
        run_monitor(2, mock_adapter, vad_tracker=mock_vad_tracker, transcriber=mock_transcriber, stop_after=1)
    
    output = captured_output.getvalue()
    assert "Level" in output


def test_monitor_displays_vad_status():
    mock_adapter = MagicMock()
    
    audio_data = np.array([1000, -1000, 1000, -1000], dtype=np.int16).tobytes()
    
    from voicenode.ports import AudioFrame, VADState
    mock_adapter.capture_frames.return_value = iter([
        AudioFrame(data=audio_data, timestamp_ms=0),
        AudioFrame(data=audio_data, timestamp_ms=100),
    ])
    
    mock_adapter.list_devices.return_value = []
    
    mock_vad_tracker = MagicMock()
    mock_vad_tracker.process_frame.return_value = None
    mock_vad_tracker.current_state = VADState.SPEECH
    
    mock_transcriber = MagicMock()
    
    captured_output = io.StringIO()
    
    with patch("sys.stdout", captured_output):
        from voicenode.cli import run_monitor
        run_monitor(2, mock_adapter, vad_tracker=mock_vad_tracker, transcriber=mock_transcriber, stop_after=2)
    
    output = captured_output.getvalue()
    assert "speech" in output.lower() or "silence" in output.lower()


def test_monitor_displays_transcription_on_speech_boundary():
    mock_adapter = MagicMock()
    
    audio_data = np.array([1000, -1000, 1000, -1000], dtype=np.int16).tobytes()
    
    from voicenode.ports import AudioFrame, VADState, VADEvent
    frames = [
        AudioFrame(data=audio_data, timestamp_ms=0),
        AudioFrame(data=audio_data, timestamp_ms=100),
        AudioFrame(data=audio_data, timestamp_ms=200),
        AudioFrame(data=audio_data, timestamp_ms=300),
    ]
    mock_adapter.capture_frames.return_value = iter(frames)
    
    mock_adapter.list_devices.return_value = []
    
    mock_vad_tracker = MagicMock()
    mock_vad_tracker.process_frame.side_effect = [VADEvent.SPEECH_START, None, None, VADEvent.SPEECH_BOUNDARY]
    mock_vad_tracker.current_state = VADState.SILENCE
    
    mock_transcriber = MagicMock()
    mock_transcriber.transcribe.return_value = "hello world"
    
    captured_output = io.StringIO()
    
    with patch("sys.stdout", captured_output):
        from voicenode.cli import run_monitor
        run_monitor(2, mock_adapter, vad_tracker=mock_vad_tracker, transcriber=mock_transcriber, stop_after=4)
    
    output = captured_output.getvalue()
    assert "hello world" in output


def test_monitor_exits_gracefully_on_keyboard_interrupt():
    mock_adapter = MagicMock()
    
    audio_data = np.array([1000, -1000, 1000, -1000], dtype=np.int16).tobytes()
    
    from voicenode.ports import AudioFrame, VADState
    
    def frame_generator():
        yield AudioFrame(data=audio_data, timestamp_ms=0)
        raise KeyboardInterrupt()
    
    mock_adapter.capture_frames.return_value = frame_generator()
    mock_adapter.list_devices.return_value = []
    
    mock_vad_tracker = MagicMock()
    mock_vad_tracker.process_frame.return_value = None
    mock_vad_tracker.current_state = VADState.SILENCE
    
    mock_transcriber = MagicMock()
    
    captured_output = io.StringIO()
    
    with patch("sys.stdout", captured_output):
        from voicenode.cli import run_monitor
        run_monitor(2, mock_adapter, vad_tracker=mock_vad_tracker, transcriber=mock_transcriber)
    
    output = captured_output.getvalue()
    assert "Stopping" in output