"""Test AEC engine reference buffering and echo cancellation wrapper."""
from unittest.mock import Mock, patch

import pytest


@pytest.fixture
def mock_ap():
    """Mock the WebRTC AudioProcessingModule."""
    with patch("voicenode.audio.aec_engine.HAS_WEBRTC", True), \
         patch("voicenode.audio.aec_engine._AudioProcessingModule") as mock_class:
        instance = Mock()
        mock_class.return_value = instance
        yield instance


def test_add_reference_chunks_into_10ms_frames(mock_ap):
    from voicenode.audio.aec_engine import AecEngine, BYTES_PER_FRAME

    engine = AecEngine()
    # 30ms of audio = 3 x 10ms frames
    engine.add_reference_chunk(b"\x00" * (BYTES_PER_FRAME * 3))
    assert len(engine._ref_queue) == 3


def test_add_reference_carries_partial_frame_residual(mock_ap):
    from voicenode.audio.aec_engine import AecEngine, BYTES_PER_FRAME

    engine = AecEngine()
    # 15ms (1.5 frames). One full frame queued, 0.5 frame stored as residual.
    engine.add_reference_chunk(b"\x01" * (BYTES_PER_FRAME + BYTES_PER_FRAME // 2))
    assert len(engine._ref_queue) == 1
    assert len(engine._ref_residual) == BYTES_PER_FRAME // 2
    # Next 5ms completes the second frame
    engine.add_reference_chunk(b"\x02" * (BYTES_PER_FRAME // 2))
    assert len(engine._ref_queue) == 2
    assert engine._ref_residual == b""


def test_cancel_echo_feeds_reverse_then_processes_stream(mock_ap):
    from voicenode.audio.aec_engine import AecEngine, BYTES_PER_FRAME

    mock_ap.process_stream.side_effect = lambda b: b  # identity for assert
    engine = AecEngine()
    engine.add_reference_chunk(b"R" * BYTES_PER_FRAME)

    mic = b"M" * BYTES_PER_FRAME
    out = engine.cancel_echo(mic, timestamp_ms=0)

    mock_ap.process_reverse_stream.assert_called_once_with(b"R" * BYTES_PER_FRAME)
    mock_ap.process_stream.assert_called_once_with(mic)
    assert out == mic


def test_cancel_echo_chunks_30ms_into_three_10ms_calls(mock_ap):
    from voicenode.audio.aec_engine import AecEngine, BYTES_PER_FRAME

    mock_ap.process_stream.side_effect = lambda b: b
    engine = AecEngine()
    mic = b"\x10" * (BYTES_PER_FRAME * 3)
    out = engine.cancel_echo(mic)
    assert mock_ap.process_stream.call_count == 3
    assert out == mic


def test_cancel_echo_passthrough_when_no_webrtc():
    with patch("voicenode.audio.aec_engine.HAS_WEBRTC", False), \
         patch("voicenode.audio.aec_engine._AudioProcessingModule", None):
        from voicenode.audio.aec_engine import AecEngine

        engine = AecEngine()
        mic = b"\x00" * 640
        assert engine.cancel_echo(mic) == mic


def test_cancel_echo_passthrough_on_unaligned_mic(mock_ap):
    from voicenode.audio.aec_engine import AecEngine

    engine = AecEngine()
    mic = b"\x00" * 333  # not multiple of 640
    out = engine.cancel_echo(mic)
    assert out == mic
    mock_ap.process_stream.assert_not_called()


def test_stream_end_clears_buffer(mock_ap):
    from voicenode.audio.aec_engine import AecEngine, BYTES_PER_FRAME

    engine = AecEngine()
    engine.add_reference_chunk(b"\x00" * (BYTES_PER_FRAME * 2))
    engine._ref_residual = b"\x01" * 10
    engine.on_stream_end()
    assert len(engine._ref_queue) == 0
    assert engine._ref_residual == b""


def test_resample_pcm_24k_to_16k_changes_sample_count():
    from voicenode.audio.aec_engine import resample_pcm_s16
    import numpy as np

    src = np.zeros(2400, dtype=np.int16).tobytes()  # 100ms at 24kHz
    out = resample_pcm_s16(src, 24000, 16000)
    # 100ms at 16k = 1600 samples = 3200 bytes
    assert len(out) == 3200


def test_resample_passthrough_when_rates_equal():
    from voicenode.audio.aec_engine import resample_pcm_s16

    src = b"\x01\x02" * 480
    assert resample_pcm_s16(src, 16000, 16000) is src


def test_add_reference_resamples_when_source_rate_differs(mock_ap):
    from voicenode.audio.aec_engine import AecEngine, BYTES_PER_FRAME, SAMPLE_RATE
    import numpy as np

    engine = AecEngine()
    # 100ms at 24kHz = 4800 bytes. Resampled to 16k = 3200 bytes = 5 frames.
    src = np.zeros(2400, dtype=np.int16).tobytes()
    engine.add_reference_chunk(src, source_rate=24000)
    assert len(engine._ref_queue) == 3200 // BYTES_PER_FRAME


def test_add_reference_handles_odd_byte_chunks(mock_ap):
    """Streamed PCM chunks may have odd byte counts; engine must not crash."""
    from voicenode.audio.aec_engine import AecEngine

    engine = AecEngine()
    # 641-byte chunk: odd. Should not raise.
    engine.add_reference_chunk(b"\x00" * 641, source_rate=24000)
    # Next chunk carries the orphan byte forward.
    engine.add_reference_chunk(b"\x00" * 5, source_rate=24000)
    # No crash; AP not yet called (no mic frame), but residual handled.
    assert engine._ref_byte_residual in (b"", b"\x00")


def test_configures_ap_on_init(mock_ap):
    from voicenode.audio.aec_engine import AecEngine, SAMPLE_RATE

    AecEngine(aec_level=2, ns_level=1)
    mock_ap.set_stream_format.assert_called_once_with(SAMPLE_RATE, 1)
    mock_ap.set_reverse_stream_format.assert_called_once_with(SAMPLE_RATE, 1)
    mock_ap.set_aec_level.assert_called_once_with(2)
    mock_ap.set_ns_level.assert_called_once_with(1)
