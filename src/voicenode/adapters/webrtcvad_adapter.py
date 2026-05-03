from voicenode.ports import AudioFrame, VADPort, VADState


class WebRTCVADAdapter(VADPort):
    def __init__(self, aggressiveness: int = 3):
        import webrtcvad

        self.vad = webrtcvad.Vad(aggressiveness)
        self.sample_rate = 16000

    def process_frame(self, frame: AudioFrame) -> VADState:
        is_speech = self.vad.is_speech(frame.data, self.sample_rate)
        return VADState.SPEECH if is_speech else VADState.SILENCE