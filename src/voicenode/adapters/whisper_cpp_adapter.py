import numpy as np
from voicenode.ports import AudioFrame, TranscriberPort


class WhisperCppAdapter(TranscriberPort):
    def __init__(self, model: str = "base.en", n_threads: int = 4):
        from pywhispercpp.model import Model

        self.model = Model(model, n_threads=n_threads)

    def transcribe(self, frames: list[AudioFrame]) -> str:
        audio_data = b"".join(frame.data for frame in frames)
        audio_array = np.frombuffer(audio_data, dtype=np.int16).astype(np.float32) / 32768.0
        segments = self.model.transcribe(audio_array)
        return "".join(seg.text for seg in segments).strip()
