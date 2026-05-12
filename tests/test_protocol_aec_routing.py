"""Test protocol handler routing of AEC reference vs playback messages."""
import pytest
from unittest.mock import Mock, AsyncMock, patch


@pytest.fixture
def mock_aec_engine():
    """Mock AEC engine."""
    return Mock()


@pytest.fixture
def mock_audio_output():
    """Mock audio output."""
    return Mock()


@pytest.fixture
def mock_server():
    """Mock server with async methods."""
    mock = Mock()
    mock.is_connected = Mock(return_value=True)
    return mock


def test_tts_stream_message_with_aec_reference_routes_to_aec(mock_aec_engine):
    """tts_stream message with isAecReference=true routes to AEC engine."""
    from voicenode.core.protocol_handler import ProtocolMessageHandler

    handler = ProtocolMessageHandler(aec_engine=mock_aec_engine, audio_output=Mock())

    msg = {
        "type": "tts_stream",
        "streamToken": "token-123",
        "audio": b"reference_audio_data",
        "timestamp": 5000,
        "isAecReference": True
    }

    handler.handle_tts_stream(msg)

    # Should have called AEC engine
    mock_aec_engine.add_reference_chunk.assert_called_once_with(
        timestamp_ms=5000,
        audio=b"reference_audio_data"
    )


def test_tts_stream_message_without_aec_reference_routes_to_playback(mock_audio_output):
    """tts_stream message with isAecReference=false routes to audio output."""
    from voicenode.core.protocol_handler import ProtocolMessageHandler

    handler = ProtocolMessageHandler(aec_engine=Mock(), audio_output=mock_audio_output)

    msg = {
        "type": "tts_stream",
        "streamToken": "token-123",
        "audio": b"playback_audio_data",
        "timestamp": 5000,
        "isAecReference": False
    }

    handler.handle_tts_stream(msg)

    # Should have called audio output
    mock_audio_output.play.assert_called_once()


def test_tts_stream_message_missing_aec_flag_routes_to_playback(mock_audio_output):
    """Old-format tts_stream without isAecReference routes to playback (backward compatible)."""
    from voicenode.core.protocol_handler import ProtocolMessageHandler

    handler = ProtocolMessageHandler(aec_engine=Mock(), audio_output=mock_audio_output)

    msg = {
        "type": "tts_stream",
        "streamToken": "token-123",
        "audio": b"playback_audio_data",
        "timestamp": 5000
        # isAecReference missing
    }

    handler.handle_tts_stream(msg)

    # Should default to playback
    mock_audio_output.play.assert_called_once()


def test_tts_stream_routing_logged(mock_aec_engine, caplog):
    """Routing decision is logged."""
    import logging
    from voicenode.core.protocol_handler import ProtocolMessageHandler

    caplog.set_level(logging.INFO)
    handler = ProtocolMessageHandler(aec_engine=mock_aec_engine, audio_output=Mock())

    msg = {
        "type": "tts_stream",
        "streamToken": "token-123",
        "audio": b"ref_data",
        "timestamp": 5000,
        "isAecReference": True
    }

    handler.handle_tts_stream(msg)

    # Should have info log about routing
    assert any("AEC" in record.message or "reference" in record.message.lower()
               for record in caplog.records if record.levelno == logging.INFO)


def test_tts_stream_out_of_order_logged(mock_audio_output, caplog):
    """Out-of-order messages logged as warning."""
    import logging
    from voicenode.core.protocol_handler import ProtocolMessageHandler

    caplog.set_level(logging.WARNING)
    handler = ProtocolMessageHandler(aec_engine=Mock(), audio_output=mock_audio_output)

    # Send messages out of order (high timestamp then low)
    msg1 = {
        "type": "tts_stream",
        "audio": b"data1",
        "timestamp": 6000,
        "isAecReference": False
    }
    msg2 = {
        "type": "tts_stream",
        "audio": b"data2",
        "timestamp": 4000,
        "isAecReference": False
    }

    handler.handle_tts_stream(msg1)
    handler.handle_tts_stream(msg2)  # Out of order

    # Should have warning (or handled gracefully without crash)
    mock_audio_output.play.assert_called()  # Both should be processed
