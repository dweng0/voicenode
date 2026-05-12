"""Integration test: Pi detects stop-word, signals server."""
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock


@pytest.mark.asyncio
async def test_detector_integrated_with_receive_loop():
    """Mock server sends tts_stream_start, utterance matches, detector sends stop_word."""
    from voicenode.core.stop_word_detector import StopWordDetector

    # Create mock server
    mock_server = AsyncMock()
    messages_to_receive = [
        {"type": "tts_stream_start"},  # Server signals TTS playback starting
        # User says "wait" during playback (simulated via utterance check)
        {"type": "config_update"},  # Some other message while listening
    ]
    mock_server.receive = AsyncMock(side_effect=messages_to_receive)
    mock_server.send = AsyncMock()

    detector = StopWordDetector(server=mock_server)

    # Simulate receive loop
    msg = await mock_server.receive()  # Get tts_stream_start
    if msg.get("type") == "tts_stream_start":
        detector.on_tts_stream_start()

    # Simulate user utterance arriving (from transcription)
    await detector.check_utterance("wait a moment please")

    # Verify detector sent stop_word signal
    mock_server.send.assert_called_once_with({
        "type": "stop_word",
        "keyword": "wait"
    })


@pytest.mark.asyncio
async def test_detector_handles_tts_stream_end_message():
    """Server sends tts_stream_end, detector stops listening."""
    from voicenode.core.stop_word_detector import StopWordDetector

    mock_server = AsyncMock()
    mock_server.send = AsyncMock()

    detector = StopWordDetector(server=mock_server)
    detector.on_tts_stream_start()
    assert detector.is_listening is True

    # Simulate tts_stream_end message
    detector.on_tts_stream_end()
    assert detector.is_listening is False

    # Utterances after stream end should be ignored
    await detector.check_utterance("wait still")
    mock_server.send.assert_not_called()


@pytest.mark.asyncio
async def test_application_suppresses_utterances_during_tts_playback():
    """Utterances suppressed during TTS playback, only stop-words sent."""
    from unittest.mock import MagicMock
    from voicenode.core.stop_word_detector import StopWordDetector

    # Create mock server
    mock_server = AsyncMock()
    mock_server.send = AsyncMock()

    # Create detector
    detector = StopWordDetector(server=mock_server)

    # Simulate application's send logic with detector state check
    async def send_with_gating(message, text):
        """Simulates _send_and_check_stop_word logic."""
        if not detector.is_listening:
            await mock_server.send(message)
        await detector.check_utterance(text)

    # Test during normal listening (is_listening=False)
    message = {"type": "utterance", "text": "hello"}
    await send_with_gating(message, "hello")
    # Utterance sent normally
    assert mock_server.send.call_count == 1
    assert mock_server.send.call_args[0][0]["type"] == "utterance"

    # Start TTS stream
    mock_server.reset_mock()
    detector.on_tts_stream_start(stream_token="test-token")
    assert detector.is_listening is True

    # Test non-stop-word during playback
    message = {"type": "utterance", "text": "hello"}
    await send_with_gating(message, "hello")
    # Utterance suppressed (not sent)
    assert mock_server.send.call_count == 0

    # Test stop-word during playback
    mock_server.reset_mock()
    await send_with_gating(message, "wait a moment")
    # Stop-word signal sent
    assert mock_server.send.call_count == 1
    assert mock_server.send.call_args[0][0]["type"] == "stop_word"

    # End TTS stream
    mock_server.reset_mock()
    detector.on_tts_stream_end(stream_token="test-token")
    assert detector.is_listening is False

    # Test normal utterance after stream ends
    message = {"type": "utterance", "text": "hello"}
    await send_with_gating(message, "hello")
    # Utterance sent normally
    assert mock_server.send.call_count == 1
    assert mock_server.send.call_args[0][0]["type"] == "utterance"
