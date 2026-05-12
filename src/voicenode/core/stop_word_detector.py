"""Stop-word detector state machine for TTS stream interruption."""
import asyncio
import logging
from typing import Optional
from voicenode.core.stop_word_matcher import StopWordMatcher

logger = logging.getLogger(__name__)


class StopWordDetector:
    """Detect stop-words during TTS playback and send signals to server.

    State machine with two modes:
    - listening=False (normal): ambient utterances checked for stop-words
    - listening=True (stream gate): only stop-word matches trigger signal

    Transitions triggered by server messages:
    - on_tts_stream_start() → listening=True (TTS playing, gate detection)
    - on_tts_stream_end() → listening=False (TTS done, resume normal)

    Auto-restore after 30s timeout if stream_end never arrives (fallback
    for network issues). Handles out-of-order messages, double-calls, token
    mismatches, and disconnect recovery gracefully.
    """

    TIMEOUT_SECONDS = 30

    def __init__(self, server=None):
        self.server = server
        self.is_listening = False
        self.matcher = StopWordMatcher()
        self._timeout_task: Optional[asyncio.Task] = None
        self._current_stream_token: Optional[str] = None

    def on_tts_stream_start(self, stream_token: Optional[str] = None) -> None:
        """Signal start of TTS stream — enter listening (stop-word only) mode.

        When housekeeper sends tts_stream_start, Pi gates detection:
        - is_listening=True: only stop-word matches trigger server signal
        - Prevents ambient speech from interrupting TTS playback
        - Stores streamToken for validation on stream_end
        - Starts 30s timeout as fallback if stream_end never arrives

        Handles edge cases: double-start (already listening) is idempotent.

        Args:
            stream_token: Optional unique token from housekeeper (for validation)
        """
        if self.is_listening:
            logger.warning(f"Double stream start: already listening. Previous: {self._current_stream_token}, new: {stream_token}")
        self.is_listening = True
        self._current_stream_token = stream_token
        logger.info(f"Stream start: {stream_token} — listening mode: gate (stop-word only)")
        self._start_timeout()

    def on_tts_stream_end(self, stream_token: Optional[str] = None) -> None:
        """Signal end of TTS stream — exit listening (stop-word only) mode.

        When housekeeper sends tts_stream_end, Pi exits gating:
        - is_listening=False: resume normal listening
        - Cancels 30s timeout (stream ended before timeout)
        - Validates streamToken matches stream_start token (warns if mismatch)

        Handles edge cases: out-of-order (end before start), double-end
        (already not listening), and token mismatches are all idempotent.

        Args:
            stream_token: Optional token from housekeeper (should match start)
        """
        if stream_token and self._current_stream_token and stream_token != self._current_stream_token:
            logger.warning(f"Stream token mismatch: expected {self._current_stream_token}, got {stream_token}")
        if not self.is_listening:
            logger.warning(f"Double stream end: not currently listening. Token: {stream_token}")
        logger.info(f"Stream end: {stream_token} — listening mode: restore (normal)")
        self.is_listening = False
        self._current_stream_token = None
        self._cancel_timeout()

    def on_timeout(self) -> None:
        """Auto-restore after 30s if stream_end never arrives.

        Fallback mechanism for network failures or hung connections:
        - If tts_stream_end doesn't arrive within TIMEOUT_SECONDS, assume
          the stream ended abnormally
        - Restores listening to normal mode (is_listening=False)
        - Prevents Pi from being stuck in stop-word-only mode forever

        Called internally by the timeout task when timer expires.
        """
        logger.info(f"Stream timeout (auto-restore listening after {self.TIMEOUT_SECONDS}s)")
        self.is_listening = False
        self._timeout_task = None

    def on_disconnect(self) -> None:
        """Disconnect detected — implicit stream end and recovery.

        When WebSocket connection is lost during active stream:
        - Treats as implicit stream_end (not waiting for server message)
        - Clears listening state (is_listening=False)
        - Cancels timeout (no need to wait for timeout if disconnected)
        - On reconnect, Pi is ready to receive new tts_stream_start

        Called by VoiceNodeApplication when _receive_loop exits due to
        connection loss. Enables clean state for reconnection sequence.
        """
        if self.is_listening:
            logger.info(f"Stream disconnect (implicit end): {self._current_stream_token}")
        self.is_listening = False
        self._current_stream_token = None
        self._cancel_timeout()

    def _start_timeout(self) -> None:
        """Start 30-second timeout to auto-stop listening."""
        self._cancel_timeout()
        self._timeout_task = asyncio.create_task(self._timeout_coroutine())

    def _cancel_timeout(self) -> None:
        """Cancel active timeout."""
        if self._timeout_task and not self._timeout_task.done():
            self._timeout_task.cancel()
        self._timeout_task = None

    async def _timeout_coroutine(self) -> None:
        """Wait for timeout duration, then stop listening."""
        try:
            await asyncio.sleep(self.TIMEOUT_SECONDS)
            self.on_timeout()
        except asyncio.CancelledError:
            pass

    async def check_utterance(self, text: str) -> None:
        """Check utterance for stop-word. Send signal if match and listening."""
        if not self.is_listening:
            return

        keyword = self.matcher.match(text)
        if keyword and self.server:
            await self.server.send({
                "type": "stop_word",
                "keyword": keyword
            })
