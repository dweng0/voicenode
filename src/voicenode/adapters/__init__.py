from typing import Iterator
import threading

from voicenode.adapters.webrtcvad_adapter import WebRTCVADAdapter as WebRTCVADAdapter
from voicenode.ports import AudioDevice, AudioFrame, AudioPort, AudioOutputPort


class SounddeviceAudioAdapter(AudioPort, AudioOutputPort):
    def __init__(self):
        self.current_stream = None
        self.playback_thread = None
        self.stop_flag = threading.Event()

    def list_devices(self) -> list[AudioDevice]:
        import sounddevice as sd

        devices = []
        device_list = sd.query_devices()
        default_input = sd.default.device[0]
        default_output = sd.default.device[1]

        for idx, dev in enumerate(device_list):
            devices.append(
                AudioDevice(
                    id=idx,
                    name=dev["name"],
                    channels=max(dev["max_input_channels"], dev["max_output_channels"]),
                    is_input=dev["max_input_channels"] > 0,
                    is_output=dev["max_output_channels"] > 0,
                    is_default=(idx == default_input or idx == default_output),
                )
            )
        return devices

    def capture_frames(self, device_id: int, duration_ms: int = 100) -> Iterator[AudioFrame]:
        import sounddevice as sd
        import time

        sample_rate = 16000
        channels = 1
        frames_per_buffer = int(sample_rate * duration_ms / 1000)

        stream = sd.InputStream(
            device=device_id,
            samplerate=sample_rate,
            channels=channels,
            dtype="int16",
            blocksize=frames_per_buffer,
        )
        with stream:
            start_time = time.time()
            while True:
                data, overflowed = stream.read(frames_per_buffer)
                timestamp_ms = int((time.time() - start_time) * 1000)
                yield AudioFrame(data=data.tobytes(), timestamp_ms=timestamp_ms)

    def play(self, audio: bytes, device_id: int) -> None:
        self.stop_playback()
        
        self.stop_flag.clear()
        
        def _play_internal():
            import sounddevice as sd
            import numpy as np
            import structlog

            try:
                audio_array = np.frombuffer(audio, dtype=np.int16)
                
                sample_rate = 24000
                
                self.current_stream = sd.OutputStream(
                    device=device_id,
                    samplerate=sample_rate,
                    channels=1,
                    dtype="int16",
                )
                
                self.current_stream.start()
                
                chunk_size = 1024
                offset = 0
                while offset < len(audio_array) and not self.stop_flag.is_set():
                    chunk = audio_array[offset:offset + chunk_size]
                    self.current_stream.write(chunk)
                    offset += chunk_size
                
                if not self.stop_flag.is_set():
                    self.current_stream.stop()
                
                self.current_stream.close()
                self.current_stream = None
            except Exception as e:
                structlog.get_logger().error("Playback error", error=str(e))
        
        self.playback_thread = threading.Thread(target=_play_internal, daemon=True)
        self.playback_thread.start()

    def stop_playback(self) -> None:
        self.stop_flag.set()
        
        if self.current_stream is not None:
            try:
                self.current_stream.stop()
                self.current_stream.close()
            except Exception:
                pass
            self.current_stream = None
        
        if self.playback_thread is not None and self.playback_thread.is_alive():
            self.playback_thread.join(timeout=0.5)
        
        self.playback_thread = None