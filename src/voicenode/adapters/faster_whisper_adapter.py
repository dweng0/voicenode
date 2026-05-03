import numpy as np
from voicenode.ports import AudioFrame, TranscriberPort


class FasterWhisperAdapter(TranscriberPort):
    def __init__(self, model_size: str = "base.en"):
        from faster_whisper import WhisperModel

        self.model = WhisperModel(model_size, device="cpu", compute_type="int8")

    def transcribe(self, frames: list[AudioFrame]) -> str:
        audio_data = b"".join(frame.data for frame in frames)
        audio_array = np.frombuffer(audio_data, dtype=np.int16).astype(np.float32) / 32768.0

        segments, _ = self.model.transcribe(audio_array, language="en")
        text = "".join(segment.text for segment in segments).strip()
        return text