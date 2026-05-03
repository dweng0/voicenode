from unittest.mock import MagicMock, patch


def test_audio_capture_yields_frames():
    """Test that AudioInputPort captures 16kHz mono frames."""
    mock_sd = MagicMock()
    
    mock_frame_data = MagicMock()
    mock_frame_data.tobytes.return_value = b"audio_data"
    
    mock_stream = MagicMock()
    mock_stream.read.return_value = (mock_frame_data, False)
    mock_stream.__enter__ = MagicMock(return_value=mock_stream)
    mock_stream.__exit__ = MagicMock(return_value=False)
    mock_sd.InputStream.return_value = mock_stream

    with patch.dict("sys.modules", {"sounddevice": mock_sd}):
        from voicenode.ports import AudioFrame
        from voicenode.adapters import SounddeviceAudioAdapter
        
        adapter = SounddeviceAudioAdapter()
        
        frame_gen = adapter.capture_frames(device_id=0, duration_ms=100)
        frame = next(frame_gen)
        
        assert isinstance(frame, AudioFrame)
        assert frame.data == b"audio_data"
        assert frame.timestamp_ms >= 0
        
        mock_sd.InputStream.assert_called_once_with(
            device=0,
            samplerate=16000,
            channels=1,
            dtype="int16",
            blocksize=1600,
        )


def test_vad_detects_speech():
    """Test that VADPort detects speech start/end."""
    mock_webrtcvad = MagicMock()
    mock_vad = MagicMock()
    
    mock_vad.is_speech.return_value = True
    mock_webrtcvad.Vad.return_value = mock_vad
    
    with patch.dict("sys.modules", {"webrtcvad": mock_webrtcvad}):
        from voicenode.ports import AudioFrame, VADState
        from voicenode.adapters import WebRTCVADAdapter
        
        adapter = WebRTCVADAdapter(aggressiveness=3)
        
        frame = AudioFrame(data=b"speech_audio", timestamp_ms=100)
        state = adapter.process_frame(frame)
        
        assert state == VADState.SPEECH
        mock_vad.is_speech.assert_called_once_with(b"speech_audio", 16000)


def test_vad_detects_silence():
    """Test that VADPort detects silence."""
    mock_webrtcvad = MagicMock()
    mock_vad = MagicMock()
    
    mock_vad.is_speech.return_value = False
    mock_webrtcvad.Vad.return_value = mock_vad
    
    with patch.dict("sys.modules", {"webrtcvad": mock_webrtcvad}):
        from voicenode.ports import AudioFrame, VADState
        from voicenode.adapters import WebRTCVADAdapter
        
        adapter = WebRTCVADAdapter(aggressiveness=3)
        
        frame = AudioFrame(data=b"silence_audio", timestamp_ms=100)
        state = adapter.process_frame(frame)
        
        assert state == VADState.SILENCE
        mock_vad.is_speech.assert_called_once_with(b"silence_audio", 16000)


def test_vad_tracker_speech_boundary():
    """Test that VADTracker detects speech boundary after silence duration threshold."""
    mock_webrtcvad = MagicMock()
    mock_vad = MagicMock()
    
    mock_vad.is_speech.return_value = False
    mock_webrtcvad.Vad.return_value = mock_vad
    
    with patch.dict("sys.modules", {"webrtcvad": mock_webrtcvad}):
        from voicenode.ports import AudioFrame, VADState, VADEvent
        from voicenode.core import VADTracker
        
        tracker = VADTracker(
            aggressiveness=3,
            silence_duration_ms=800,
            frame_duration_ms=100,
        )
        
        tracker.set_state(VADState.SPEECH)
        
        for i in range(9):
            frame = AudioFrame(data=b"silence", timestamp_ms=100 + i * 100)
            event = tracker.process_frame(frame)
            if i < 8:
                assert event is None
            else:
                assert event == VADEvent.SPEECH_BOUNDARY


def test_vad_tracker_max_utterance_length():
    """Test that VADTracker triggers boundary after max utterance length."""
    mock_webrtcvad = MagicMock()
    mock_vad = MagicMock()
    
    mock_vad.is_speech.return_value = True
    mock_webrtcvad.Vad.return_value = mock_vad
    
    with patch.dict("sys.modules", {"webrtcvad": mock_webrtcvad}):
        from voicenode.ports import AudioFrame, VADEvent
        from voicenode.core import VADTracker
        
        tracker = VADTracker(
            aggressiveness=3,
            silence_duration_ms=800,
            frame_duration_ms=100,
            max_utterance_length_ms=30000,
        )
        
        for i in range(301):
            frame = AudioFrame(data=b"speech", timestamp_ms=i * 100)
            event = tracker.process_frame(frame)
            if i == 0:
                assert event == VADEvent.SPEECH_START
            elif i < 300:
                assert event is None
            else:
                assert event == VADEvent.MAX_UTTERANCE_LENGTH