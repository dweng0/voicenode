"""Protocol message handler for AEC reference routing."""
import logging
from typing import Optional, Any

logger = logging.getLogger(__name__)


class ProtocolMessageHandler:
    """Routes tts_stream messages to AEC or playback based on isAecReference flag."""

    def __init__(self, aec_engine: Any, audio_output: Any):
        """Initialize handler.

        Args:
            aec_engine: AEC engine instance (handles add_reference_chunk)
            audio_output: Audio output adapter (handles play)
        """
        self.aec_engine = aec_engine
        self.audio_output = audio_output
        self._last_timestamp: Optional[int] = None

    def handle_tts_stream(self, message: dict) -> None:
        """Route tts_stream message to AEC or playback.

        Args:
            message: tts_stream message dict with audio, timestamp, optional isAecReference
        """
        is_aec_ref = message.get("isAecReference", False)
        timestamp = message.get("timestamp")
        audio = message.get("audio")
        stream_token = message.get("streamToken")

        if not audio:
            logger.warning("tts_stream message missing audio data")
            return

        # Check for out-of-order messages
        if timestamp is not None and self._last_timestamp is not None:
            if timestamp < self._last_timestamp:
                logger.warning(
                    f"Out-of-order tts_stream message: {timestamp}ms < {self._last_timestamp}ms"
                )

        if is_aec_ref:
            logger.info(f"AEC reference chunk at timestamp {timestamp}ms")
            self.aec_engine.add_reference_chunk(timestamp_ms=timestamp, audio=audio)
        else:
            logger.info(f"Playback chunk at timestamp {timestamp}ms")
            self.audio_output.play(audio, stream_token=stream_token)

        self._last_timestamp = timestamp
