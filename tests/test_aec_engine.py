"""Test AEC engine reference buffer and echo cancellation."""
import pytest
from unittest.mock import Mock, patch, MagicMock


@pytest.fixture
def mock_webrtc():
    """Mock WebRTC AEC library."""
    with patch("voicenode.audio.aec_engine.HAS_WEBRTC", True), \
         patch("voicenode.audio.aec_engine.WebRtcAec") as mock_class:
        mock_instance = Mock()
        mock_class.return_value = mock_instance
        yield mock_instance


def test_aec_engine_buffers_reference_chunk(mock_webrtc):
    """Reference chunks are buffered by timestamp."""
    from voicenode.audio.aec_engine import AecEngine

    engine = AecEngine(sample_rate=16000)

    # Add reference at timestamp 1000ms
    ref_audio = b"fake_audio_data_1000"
    engine.add_reference_chunk(timestamp_ms=1000, audio=ref_audio)

    # Buffer should contain the chunk
    assert engine._reference_buffer.get(1000) == ref_audio


def test_aec_engine_cancel_echo_returns_residual(mock_webrtc):
    """Echo cancellation returns residual audio."""
    from voicenode.audio.aec_engine import AecEngine

    engine = AecEngine(sample_rate=16000)

    # Add reference
    ref_audio = b"reference_audio_1000"
    engine.add_reference_chunk(timestamp_ms=1000, audio=ref_audio)

    # Mock WebRTC to return residual
    residual = b"residual_audio"
    mock_webrtc.process_frame.return_value = residual

    # Cancel echo
    mic_audio = b"mic_input_with_echo"
    result = engine.cancel_echo(mic_audio=mic_audio, timestamp_ms=1000)

    assert result == residual
    mock_webrtc.process_frame.assert_called_once()


def test_aec_engine_cleans_old_frames_on_ttl(mock_webrtc):
    """Old frames removed after TTL expires."""
    from voicenode.audio.aec_engine import AecEngine

    engine = AecEngine(sample_rate=16000, reference_ttl_ms=5000)

    # Add reference at 1000ms
    engine.add_reference_chunk(timestamp_ms=1000, audio=b"old_audio")

    # Add at 6100ms (1100ms past TTL)
    engine.add_reference_chunk(timestamp_ms=6100, audio=b"new_audio")

    # Old frame should be removed
    assert 1000 not in engine._reference_buffer
    assert 6100 in engine._reference_buffer


def test_aec_engine_timestamp_lookup_tolerance(mock_webrtc):
    """Timestamp lookup matches within ±100ms tolerance."""
    from voicenode.audio.aec_engine import AecEngine

    engine = AecEngine(sample_rate=16000)

    # Add reference at 1000ms
    ref_audio = b"reference_at_1000"
    engine.add_reference_chunk(timestamp_ms=1000, audio=ref_audio)

    # Mock WebRTC
    residual = b"result"
    mock_webrtc.process_frame.return_value = residual

    # Query at 1050ms (within ±100ms) should find 1000ms
    result = engine.cancel_echo(mic_audio=b"mic", timestamp_ms=1050)

    assert result == residual
    mock_webrtc.process_frame.assert_called_once()


def test_aec_engine_stream_end_clears_buffer(mock_webrtc):
    """Stream end clears reference buffer."""
    from voicenode.audio.aec_engine import AecEngine

    engine = AecEngine(sample_rate=16000)

    # Add references
    engine.add_reference_chunk(timestamp_ms=1000, audio=b"ref1")
    engine.add_reference_chunk(timestamp_ms=2000, audio=b"ref2")
    assert len(engine._reference_buffer) == 2

    # End stream
    engine.on_stream_end()

    # Buffer should be empty
    assert len(engine._reference_buffer) == 0
