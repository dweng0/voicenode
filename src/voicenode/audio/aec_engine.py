"""Acoustic Echo Cancellation engine using WebRTC AEC."""
from typing import Optional
import logging

try:
    from webrtc_audio_processing import WebRtcAec
    HAS_WEBRTC = True
except ImportError:
    HAS_WEBRTC = False
    WebRtcAec = None

logger = logging.getLogger(__name__)


class AecEngine:
    """WebRTC-based acoustic echo cancellation with timestamp-synchronized reference buffer."""

    def __init__(self, sample_rate: int = 16000, reference_ttl_ms: int = 5000):
        """Initialize AEC engine.

        Args:
            sample_rate: Audio sample rate (default 16000 Hz)
            reference_ttl_ms: Reference buffer TTL in milliseconds (default 5000ms)
        """
        self.sample_rate = sample_rate
        self.reference_ttl_ms = reference_ttl_ms
        self.aec = WebRtcAec() if HAS_WEBRTC else None
        self._reference_buffer: dict[int, bytes] = {}  # timestamp_ms -> audio
        self._server_time_offset_ms: int = 0  # Server clock offset relative to Pi

        if not HAS_WEBRTC:
            logger.warning("webrtc-audio-processing not installed; AEC disabled (passthrough only)")

    def add_reference_chunk(self, timestamp_ms: int, audio: bytes) -> None:
        """Buffer reference audio chunk.

        Args:
            timestamp_ms: Server-provided timestamp
            audio: PCM audio bytes
        """
        self._reference_buffer[timestamp_ms] = audio
        self._cleanup_old_frames()
        logger.debug(f"Reference buffer size: {len(self._reference_buffer)} frames")

    def cancel_echo(self, mic_audio: bytes, timestamp_ms: int) -> bytes:
        """Apply echo cancellation to mic input.

        Args:
            mic_audio: Microphone PCM audio
            timestamp_ms: Approximate timestamp for reference lookup

        Returns:
            Residual audio (echo-cancelled)
        """
        # Find reference within ±100ms tolerance
        ref_audio = self._get_reference_at_timestamp(timestamp_ms)

        if ref_audio is None:
            logger.debug(f"No reference audio found at {timestamp_ms}ms")
            return mic_audio  # Return mic as-is if no reference

        if self.aec is None:
            logger.debug(f"AEC disabled; returning mic audio as-is at {timestamp_ms}ms")
            return mic_audio

        # Apply WebRTC AEC
        residual = self.aec.process_frame(mic_audio, ref_audio)

        # Log echo level (approximate)
        echo_level_db = self._estimate_echo_level(residual)
        logger.debug(f"Echo residual: {echo_level_db}dB at timestamp {timestamp_ms}ms")

        return residual

    def on_stream_end(self) -> None:
        """Clear reference buffer on TTS stream end."""
        self._reference_buffer.clear()
        logger.info("Reference buffer cleared (stream end)")

    def _get_reference_at_timestamp(self, target_timestamp_ms: int) -> Optional[bytes]:
        """Find reference audio within ±100ms of target timestamp."""
        for ts, audio in self._reference_buffer.items():
            if abs(ts - target_timestamp_ms) <= 100:
                return audio
        return None

    def _cleanup_old_frames(self) -> None:
        """Remove reference frames older than TTL."""
        if not self._reference_buffer:
            return

        # Find most recent timestamp
        max_ts = max(self._reference_buffer.keys())
        cutoff_ts = max_ts - self.reference_ttl_ms

        # Remove old frames
        to_remove = [ts for ts in self._reference_buffer.keys() if ts < cutoff_ts]
        for ts in to_remove:
            del self._reference_buffer[ts]

    def _estimate_echo_level(self, residual: bytes) -> float:
        """Rough estimate of residual echo level in dB."""
        # Simple RMS-based estimate (not precise, for logging only)
        if not residual:
            return float("-inf")

        # Convert bytes to 16-bit samples and compute RMS
        import struct
        try:
            samples = struct.unpack(f"<{len(residual)//2}h", residual)
            rms = sum(s*s for s in samples) / len(samples)
            rms = (rms ** 0.5)
            if rms > 0:
                return 20 * (rms / 32768) ** 0.5
            return float("-inf")
        except:
            return 0  # Fallback
