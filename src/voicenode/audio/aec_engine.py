"""Acoustic Echo Cancellation engine using WebRTC AudioProcessingModule."""
from collections import deque
from typing import Optional
import logging

logger = logging.getLogger(__name__)


def _patch_webrtc_imp_shim() -> None:
    """Rewrite the upstream SWIG loader that uses the removed `imp` module on py3.12+."""
    import importlib
    import os
    import sys
    try:
        import webrtc_audio_processing.webrtc_audio_processing as _wap_mod  # noqa: F401
        return
    except ModuleNotFoundError as e:
        if "imp" not in str(e):
            raise
    try:
        import webrtc_audio_processing as _pkg
    except Exception:
        return
    path = os.path.join(os.path.dirname(_pkg.__file__), "webrtc_audio_processing.py")
    if not os.path.exists(path):
        return
    with open(path, "r") as f:
        src = f.read()
    if "import imp" not in src:
        return
    new_src = src.replace(
        "from sys import version_info",
        "from . import _webrtc_audio_processing  # patched: avoid removed `imp` module\n_orig_version_info = None",
        1,
    )
    marker_start = "if version_info >= (2,6,0):"
    if marker_start in new_src:
        idx = new_src.index(marker_start)
        end_marker = "del version_info"
        end_idx = new_src.index(end_marker, idx) + len(end_marker)
        new_src = new_src[:idx] + new_src[end_idx:]
    with open(path, "w") as f:
        f.write(new_src)
    importlib.invalidate_caches()
    for name in list(sys.modules):
        if name.startswith("webrtc_audio_processing"):
            del sys.modules[name]


try:
    _patch_webrtc_imp_shim()
    from webrtc_audio_processing import AP as _AudioProcessingModule
    HAS_WEBRTC = True
except Exception as _e:
    HAS_WEBRTC = False
    _AudioProcessingModule = None
    logger.warning(f"webrtc-audio-processing unavailable ({_e}); AEC passthrough only")


SAMPLE_RATE = 16000
FRAME_MS = 10
SAMPLES_PER_FRAME = SAMPLE_RATE * FRAME_MS // 1000  # 320
BYTES_PER_FRAME = SAMPLES_PER_FRAME * 2  # 16-bit mono


def resample_pcm_s16(audio: bytes, src_rate: int, dst_rate: int) -> bytes:
    """Resample 16-bit mono PCM via numpy linear interpolation.

    Adequate for AEC reference (quality not critical, alignment is). For
    high-fidelity playback prefer scipy.signal.resample_poly.
    """
    if src_rate == dst_rate or not audio:
        return audio
    import numpy as np
    a = np.frombuffer(audio, dtype=np.int16)
    if a.size == 0:
        return b""
    n_out = int(round(a.size * dst_rate / src_rate))
    if n_out <= 0:
        return b""
    x_old = np.arange(a.size, dtype=np.float64)
    x_new = np.linspace(0, a.size - 1, n_out, dtype=np.float64)
    out = np.interp(x_new, x_old, a.astype(np.float64))
    return np.clip(out, -32768, 32767).astype(np.int16).tobytes()


class AecEngine:
    """WebRTC AudioProcessingModule wrapper. Render (TTS) + capture (mic) -> cancelled mic.

    Frames must be 10ms @ 16kHz mono int16 internally; engine chunks larger blocks.
    """

    def __init__(self, sample_rate: int = SAMPLE_RATE, aec_level: int = 2, ns_level: int = 2):
        if sample_rate != SAMPLE_RATE:
            raise ValueError(f"AecEngine fixed at {SAMPLE_RATE}Hz; got {sample_rate}")
        self.sample_rate = sample_rate
        self._ref_queue: deque[bytes] = deque(maxlen=512)  # ~5s of 10ms frames
        self._ref_residual = b""  # post-resample, partial 10ms frame
        self._ref_byte_residual = b""  # pre-resample, odd trailing byte from chunked PCM
        if HAS_WEBRTC:
            self.ap = _AudioProcessingModule()
            self.ap.set_stream_format(SAMPLE_RATE, 1)
            self.ap.set_reverse_stream_format(SAMPLE_RATE, 1)
            self.ap.set_aec_level(aec_level)
            self.ap.set_ns_level(ns_level)
            try:
                # Delay (ms) between reference fed to APM and echo appearing in mic.
                # Accounts for sounddevice output buffer + acoustic propagation on Pi.
                # Tune: if echo persists try higher (150); if voice is clipped try lower (50).
                self.ap.set_system_delay(100)
            except Exception:
                pass
        else:
            self.ap = None

    def add_reference_chunk(
        self,
        audio: bytes,
        source_rate: int = SAMPLE_RATE,
        timestamp_ms: Optional[int] = None,
    ) -> None:
        """Buffer TTS speaker audio. Resample to APM rate, split to 10ms frames.

        Network-chunked PCM may not align to int16 sample boundaries; we carry
        any odd trailing byte forward to the next chunk before resampling.
        """
        if not audio:
            return
        # Align to int16 boundary before resampling.
        aligned = self._ref_byte_residual + audio
        if len(aligned) % 2 == 1:
            self._ref_byte_residual = aligned[-1:]
            aligned = aligned[:-1]
        else:
            self._ref_byte_residual = b""
        if not aligned:
            return
        if source_rate != SAMPLE_RATE:
            aligned = resample_pcm_s16(aligned, source_rate, SAMPLE_RATE)
        data = self._ref_residual + aligned
        n_frames = len(data) // BYTES_PER_FRAME
        for i in range(n_frames):
            self._ref_queue.append(data[i * BYTES_PER_FRAME : (i + 1) * BYTES_PER_FRAME])
        self._ref_residual = data[n_frames * BYTES_PER_FRAME :]

    def cancel_echo(self, mic_audio: bytes, timestamp_ms: Optional[int] = None) -> bytes:
        """Run AEC on mic audio. Interleaves one reference frame per mic frame.

        Mic audio must be a whole number of 10ms frames (640 bytes each).
        """
        if not HAS_WEBRTC or self.ap is None:
            return mic_audio
        if len(mic_audio) % BYTES_PER_FRAME != 0:
            logger.debug(
                f"mic audio length {len(mic_audio)} not multiple of {BYTES_PER_FRAME}; passthrough"
            )
            return mic_audio

        out = bytearray()
        n_frames = len(mic_audio) // BYTES_PER_FRAME
        for i in range(n_frames):
            # Interleave: one reference frame per mic frame so APM timing model stays coherent.
            if self._ref_queue:
                try:
                    self.ap.process_reverse_stream(self._ref_queue.popleft())
                except Exception as e:
                    logger.warning(f"process_reverse_stream failed: {e}")
            chunk = mic_audio[i * BYTES_PER_FRAME : (i + 1) * BYTES_PER_FRAME]
            try:
                out.extend(self.ap.process_stream(chunk))
            except Exception as e:
                logger.warning(f"process_stream failed: {e}; passthrough frame")
                out.extend(chunk)
        return bytes(out)

    def on_stream_end(self) -> None:
        """Clear pending reference buffer on TTS stream end."""
        self._ref_queue.clear()
        self._ref_residual = b""
        self._ref_byte_residual = b""
        logger.info("AEC reference buffer cleared (stream end)")
