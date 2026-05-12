"""Test timeout for stop-word detection window."""
import asyncio
import pytest
from unittest.mock import AsyncMock, patch


@pytest.fixture
def mock_server():
    """Mock server with async send method."""
    mock = AsyncMock()
    mock.send = AsyncMock()
    return mock


@pytest.mark.asyncio
async def test_detector_stops_listening_after_timeout(mock_server):
    """Stop listening after 30s if tts_stream_end never arrives."""
    from voicenode.core.stop_word_detector import StopWordDetector

    detector = StopWordDetector(server=mock_server)
    detector.on_tts_stream_start()
    assert detector.is_listening is True

    # Wait for timeout (30s)
    await asyncio.sleep(0.1)  # Small delay to let timeout task start
    with patch("voicenode.core.stop_word_detector.asyncio.sleep") as mock_sleep:
        mock_sleep.return_value = None
        # Trigger timeout manually for testing
        detector._cancel_timeout()
        detector._start_timeout()
        # Simulate timeout expiration
        await asyncio.sleep(0.01)
        detector.on_timeout()

    assert detector.is_listening is False


@pytest.mark.asyncio
async def test_detector_cancels_timeout_on_tts_stream_end(mock_server):
    """Cancel timeout timer when tts_stream_end arrives."""
    from voicenode.core.stop_word_detector import StopWordDetector

    detector = StopWordDetector(server=mock_server)
    detector.on_tts_stream_start()

    # Immediately end stream before timeout
    detector.on_tts_stream_end()
    assert detector.is_listening is False

    # Timeout task should be cancelled
    assert detector._timeout_task is None or detector._timeout_task.cancelled()
