"""Test stop-word detector state machine."""
from unittest.mock import AsyncMock
import pytest


@pytest.fixture
def mock_server():
    """Mock server with async send method."""
    mock = AsyncMock()
    mock.send = AsyncMock()
    return mock


def test_detector_inactive_on_init():
    """Detector starts inactive (not listening)."""
    from voicenode.core.stop_word_detector import StopWordDetector

    detector = StopWordDetector(server=None)
    assert detector.is_listening is False


@pytest.mark.asyncio
async def test_detector_enters_listening_on_tts_stream_start(mock_server):
    """Entering listening on tts_stream_start message."""
    from voicenode.core.stop_word_detector import StopWordDetector

    detector = StopWordDetector(server=mock_server)
    detector.on_tts_stream_start()

    assert detector.is_listening is True


@pytest.mark.asyncio
async def test_detector_exits_listening_on_tts_stream_end(mock_server):
    """Exiting listening on tts_stream_end message."""
    from voicenode.core.stop_word_detector import StopWordDetector

    detector = StopWordDetector(server=mock_server)
    detector.on_tts_stream_start()
    assert detector.is_listening is True

    detector.on_tts_stream_end()
    assert detector.is_listening is False


@pytest.mark.asyncio
async def test_detector_sends_stop_word_signal_when_listening(mock_server):
    """Send stop_word message when listening and utterance matches."""
    from voicenode.core.stop_word_detector import StopWordDetector

    detector = StopWordDetector(server=mock_server)
    detector.on_tts_stream_start()

    await detector.check_utterance("wait a minute")

    mock_server.send.assert_called_once_with({
        "type": "stop_word",
        "keyword": "wait"
    })


@pytest.mark.asyncio
async def test_detector_ignores_utterance_when_not_listening(mock_server):
    """Don't send signal if not listening."""
    from voicenode.core.stop_word_detector import StopWordDetector

    detector = StopWordDetector(server=mock_server)
    # Don't call on_tts_stream_start, stay inactive

    await detector.check_utterance("wait a minute")

    mock_server.send.assert_not_called()


@pytest.mark.asyncio
async def test_detector_ignores_non_matching_utterance(mock_server):
    """Don't send signal if utterance doesn't match."""
    from voicenode.core.stop_word_detector import StopWordDetector

    detector = StopWordDetector(server=mock_server)
    detector.on_tts_stream_start()

    await detector.check_utterance("continue playing")

    mock_server.send.assert_not_called()


@pytest.mark.asyncio
async def test_detector_handles_out_of_order_end_before_start(mock_server):
    """Handle stream_end arriving before stream_start (out-of-order)."""
    from voicenode.core.stop_word_detector import StopWordDetector

    detector = StopWordDetector(server=mock_server)
    # Call end() without calling start() first — out-of-order
    detector.on_tts_stream_end()

    # Should still be in not-listening state, no error
    assert detector.is_listening is False


@pytest.mark.asyncio
async def test_detector_prevents_double_start(mock_server):
    """Prevent double-start (stream_start called twice without end)."""
    from voicenode.core.stop_word_detector import StopWordDetector

    detector = StopWordDetector(server=mock_server)
    detector.on_tts_stream_start()
    assert detector.is_listening is True

    # Call start again without end — should handle gracefully
    detector.on_tts_stream_start()

    # Should still be listening (no crash, no double-gating)
    assert detector.is_listening is True


@pytest.mark.asyncio
async def test_detector_prevents_double_end(mock_server):
    """Prevent double-end (stream_end called twice with same token)."""
    from voicenode.core.stop_word_detector import StopWordDetector

    detector = StopWordDetector(server=mock_server)
    detector.on_tts_stream_start()
    detector.on_tts_stream_end()
    assert detector.is_listening is False

    # Call end again — should handle gracefully
    detector.on_tts_stream_end()
    assert detector.is_listening is False


@pytest.mark.asyncio
async def test_detector_tracks_stream_token(mock_server):
    """Track streamToken from start and validate on end."""
    from voicenode.core.stop_word_detector import StopWordDetector

    detector = StopWordDetector(server=mock_server)

    # Start stream with token
    detector.on_tts_stream_start(stream_token="token-123")
    assert detector.is_listening is True

    # End stream with same token
    detector.on_tts_stream_end(stream_token="token-123")
    assert detector.is_listening is False


@pytest.mark.asyncio
async def test_detector_detects_token_mismatch(mock_server):
    """Detect and warn on streamToken mismatch (end doesn't match start)."""
    from voicenode.core.stop_word_detector import StopWordDetector

    detector = StopWordDetector(server=mock_server)

    # Start stream with token-123
    detector.on_tts_stream_start(stream_token="token-123")
    assert detector.is_listening is True

    # End stream with DIFFERENT token — should still end but log warning
    detector.on_tts_stream_end(stream_token="token-456")
    assert detector.is_listening is False


@pytest.mark.asyncio
async def test_detector_logs_token_mismatch_warning(mock_server, caplog):
    """Log warning when streamToken doesn't match between start and end."""
    import logging
    from voicenode.core.stop_word_detector import StopWordDetector

    caplog.set_level(logging.WARNING)
    detector = StopWordDetector(server=mock_server)

    # Start with token-123
    detector.on_tts_stream_start(stream_token="token-123")

    # End with token-456 (mismatch)
    detector.on_tts_stream_end(stream_token="token-456")

    # Should have warning in logs mentioning mismatch
    assert any("token" in record.message.lower() and "mismatch" in record.message.lower()
               for record in caplog.records)


@pytest.mark.asyncio
async def test_detector_logs_stream_start_event(mock_server, caplog):
    """Log info-level event when stream starts."""
    import logging
    from voicenode.core.stop_word_detector import StopWordDetector

    caplog.set_level(logging.INFO)
    detector = StopWordDetector(server=mock_server)

    detector.on_tts_stream_start(stream_token="token-abc-123")

    # Should have info log about stream start
    assert any("stream" in record.message.lower() and "start" in record.message.lower()
               for record in caplog.records if record.levelno == logging.INFO)
    # Token should be in the log
    assert any("token-abc-123" in record.message for record in caplog.records)


@pytest.mark.asyncio
async def test_detector_logs_stream_end_event(mock_server, caplog):
    """Log info-level event when stream ends."""
    import logging
    from voicenode.core.stop_word_detector import StopWordDetector

    caplog.set_level(logging.INFO)
    detector = StopWordDetector(server=mock_server)

    detector.on_tts_stream_start(stream_token="token-xyz-789")
    caplog.clear()  # Clear start log
    detector.on_tts_stream_end(stream_token="token-xyz-789")

    # Should have info log about stream end
    assert any("stream" in record.message.lower() and "end" in record.message.lower()
               for record in caplog.records if record.levelno == logging.INFO)
    # Token should be in the log
    assert any("token-xyz-789" in record.message for record in caplog.records)


@pytest.mark.asyncio
async def test_detector_logs_timeout_event(mock_server, caplog):
    """Log info-level event when stream timeout occurs."""
    import logging
    from voicenode.core.stop_word_detector import StopWordDetector

    caplog.set_level(logging.INFO)
    detector = StopWordDetector(server=mock_server)

    detector.on_tts_stream_start(stream_token="token-timeout")
    caplog.clear()  # Clear start log

    # Manually trigger timeout
    detector.on_timeout()

    # Should have info log about timeout
    assert any("timeout" in record.message.lower() or "stream" in record.message.lower()
               for record in caplog.records if record.levelno == logging.INFO)


@pytest.mark.asyncio
async def test_detector_logs_listening_mode_change_to_gated(mock_server, caplog):
    """Log when listening transitions to gated (stop-word only) mode."""
    import logging
    from voicenode.core.stop_word_detector import StopWordDetector

    caplog.set_level(logging.INFO)
    detector = StopWordDetector(server=mock_server)

    detector.on_tts_stream_start(stream_token="token-123")

    # Should have log mentioning listening mode or gate
    assert any(("listening" in record.message.lower() and "gate" in record.message.lower()) or
               ("mode" in record.message.lower() and "stop" in record.message.lower())
               for record in caplog.records if record.levelno == logging.INFO)


@pytest.mark.asyncio
async def test_detector_logs_listening_mode_change_to_normal(mock_server, caplog):
    """Log when listening transitions back to normal mode."""
    import logging
    from voicenode.core.stop_word_detector import StopWordDetector

    caplog.set_level(logging.INFO)
    detector = StopWordDetector(server=mock_server)

    detector.on_tts_stream_start(stream_token="token-123")
    caplog.clear()  # Clear start log
    detector.on_tts_stream_end(stream_token="token-123")

    # Should have log mentioning restore or normal mode
    assert any(("listening" in record.message.lower() and "restore" in record.message.lower()) or
               ("mode" in record.message.lower() and "normal" in record.message.lower())
               for record in caplog.records if record.levelno == logging.INFO)


@pytest.mark.asyncio
async def test_detector_logs_double_start_warning(mock_server, caplog):
    """Log warning when stream_start called twice without end."""
    import logging
    from voicenode.core.stop_word_detector import StopWordDetector

    caplog.set_level(logging.WARNING)
    detector = StopWordDetector(server=mock_server)

    detector.on_tts_stream_start(stream_token="token-first")
    caplog.clear()  # Clear first start log

    # Call start again without end
    detector.on_tts_stream_start(stream_token="token-second")

    # Should have warning about double-start
    assert any("double" in record.message.lower() or "already" in record.message.lower()
               for record in caplog.records if record.levelno == logging.WARNING)


@pytest.mark.asyncio
async def test_detector_logs_double_end_warning(mock_server, caplog):
    """Log warning when stream_end called twice."""
    import logging
    from voicenode.core.stop_word_detector import StopWordDetector

    caplog.set_level(logging.WARNING)
    detector = StopWordDetector(server=mock_server)

    detector.on_tts_stream_start(stream_token="token-123")
    detector.on_tts_stream_end(stream_token="token-123")
    caplog.clear()  # Clear first end log

    # Call end again with same token
    detector.on_tts_stream_end(stream_token="token-123")

    # Should have warning about double-end or "not active"
    assert any("double" in record.message.lower() or "not active" in record.message.lower()
               for record in caplog.records if record.levelno == logging.WARNING)


@pytest.mark.asyncio
async def test_detector_stress_test_random_message_order(mock_server):
    """Stress test: send messages in various orders, verify listening state consistency."""
    from voicenode.core.stop_word_detector import StopWordDetector

    detector = StopWordDetector(server=mock_server)

    # Scenario 1: Normal start-end
    detector.on_tts_stream_start(stream_token="s1")
    assert detector.is_listening is True
    detector.on_tts_stream_end(stream_token="s1")
    assert detector.is_listening is False

    # Scenario 2: Out-of-order (end before start)
    detector.on_tts_stream_end(stream_token="s2")
    assert detector.is_listening is False

    # Scenario 3: Start after orphan end
    detector.on_tts_stream_start(stream_token="s3")
    assert detector.is_listening is True

    # Scenario 4: Multiple starts (no double-gating)
    detector.on_tts_stream_start(stream_token="s4")
    assert detector.is_listening is True
    detector.on_tts_stream_start(stream_token="s5")
    assert detector.is_listening is True  # Still listening, not locked up

    # Scenario 5: End the double-started stream
    detector.on_tts_stream_end(stream_token="s5")
    assert detector.is_listening is False

    # Scenario 6: Multiple ends (no crash)
    detector.on_tts_stream_end(stream_token="orphan")
    assert detector.is_listening is False

    # Scenario 7: Rapid start-end-start cycles
    for i in range(3):
        token = f"rapid-{i}"
        detector.on_tts_stream_start(stream_token=token)
        assert detector.is_listening is True
        detector.on_tts_stream_end(stream_token=token)
        assert detector.is_listening is False

    # Final state: should be listening=False and no active token
    assert detector.is_listening is False
    assert detector._current_stream_token is None


@pytest.mark.asyncio
async def test_detector_disconnect_recovery_implicit_end(mock_server):
    """Handle disconnect during stream: implicit stream_end on reconnect."""
    from voicenode.core.stop_word_detector import StopWordDetector

    detector = StopWordDetector(server=mock_server)

    # Stream starts normally
    detector.on_tts_stream_start(stream_token="token-active")
    assert detector.is_listening is True

    # Disconnect happens (connection lost, implicit end)
    detector.on_disconnect()

    # After disconnect, listening restored (no longer gated)
    assert detector.is_listening is False
    assert detector._current_stream_token is None

    # Can start new stream after reconnect
    detector.on_tts_stream_start(stream_token="token-new")
    assert detector.is_listening is True
    detector.on_tts_stream_end(stream_token="token-new")
    assert detector.is_listening is False
