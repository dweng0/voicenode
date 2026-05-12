from typing import Iterator
import threading

from voicenode.adapters.webrtcvad_adapter import WebRTCVADAdapter as WebRTCVADAdapter
from voicenode.ports import AudioDevice, AudioFrame, AudioPort, AudioOutputPort


class SounddeviceAudioAdapter(AudioPort, AudioOutputPort):
    def __init__(self, on_playback_complete=None):
        self.current_stream = None
        self.playback_thread = None
        self.stop_flag = threading.Event()
        self.audio_buffer = bytearray()
        self.buffer_lock = threading.Lock()
        self.playback_started = False
        self.playback_timer = None
        self.last_chunk_time = None
        self.on_playback_complete = on_playback_complete
        self.current_stream_token = None

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

    def play(self, audio: bytes, device_id: int, stream_token: str = None, sample_rate: int = 24000) -> None:
        import time

        with self.buffer_lock:
            self.audio_buffer.extend(audio)
            self.last_chunk_time = time.time()

            if not self.playback_started:
                self.playback_started = True
                self.current_stream_token = stream_token
                self.current_sample_rate = sample_rate
                if self.playback_timer is not None:
                    self.playback_timer.cancel()

                def _start_playback():
                    self.stop_flag.clear()
                    playback_thread = threading.Thread(
                        target=self._playback_loop,
                        args=(device_id, sample_rate),
                        daemon=False
                    )
                    playback_thread.start()
                    self.playback_thread = playback_thread

                self.playback_timer = threading.Timer(0.02, _start_playback)
                self.playback_timer.start()

    def _playback_loop(self, device_id: int, sample_rate: int = 24000) -> None:
        import sounddevice as sd
        import numpy as np
        import structlog
        import time

        try:
            stream = sd.OutputStream(
                device=device_id,
                samplerate=sample_rate,
                channels=1,
                dtype="int16",
            )

            stream.start()

            chunk_size = 4096
            while not self.stop_flag.is_set():
                with self.buffer_lock:
                    if len(self.audio_buffer) == 0:
                        if time.time() - self.last_chunk_time > 0.5:
                            break
                        buffer_data = None
                    else:
                        buffer_data = bytes(self.audio_buffer[:chunk_size])
                        del self.audio_buffer[:chunk_size]

                if buffer_data:
                    audio_array = np.frombuffer(buffer_data, dtype=np.int16)
                    stream.write(audio_array)
                else:
                    time.sleep(0.01)

            stream.stop()
            stream.close()
        except Exception as e:
            structlog.get_logger().error("Playback error", error=str(e))
        finally:
            token = self.current_stream_token
            with self.buffer_lock:
                self.playback_started = False
                self.audio_buffer.clear()
                self.current_stream_token = None
            if token and self.on_playback_complete:
                self.on_playback_complete(token)

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