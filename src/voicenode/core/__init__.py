from dataclasses import dataclass
from abc import ABC, abstractmethod
from typing import Optional, Callable
from concurrent.futures import ThreadPoolExecutor

from voicenode.ports import AudioFrame, VADState, VADEvent, TranscriberPort


@dataclass
class NodeConfig:
    id: str
    label: str
    location: str
    server_url: str
    whisper_model: str
    devices: dict
    vad: dict
    capabilities: list
    stt_mode: str = "local"
    server_http_url: Optional[str] = None


class ConfigPort(ABC):
    @abstractmethod
    def load(self) -> NodeConfig:
        """Load config from storage."""
        ...

    @abstractmethod
    def save(self, config: NodeConfig) -> None:
        """Save config to storage."""
        ...

    @abstractmethod
    def exists(self) -> bool:
        """Check if config file exists."""
        ...


class VADTracker:
    def __init__(
        self,
        aggressiveness: int = 3,
        silence_duration_ms: int = 800,
        frame_duration_ms: int = 100,
        max_utterance_length_ms: int = 30000,
    ):
        from voicenode.adapters.webrtcvad_adapter import WebRTCVADAdapter

        self.vad = WebRTCVADAdapter(aggressiveness)
        self.silence_duration_ms = silence_duration_ms
        self.frame_duration_ms = frame_duration_ms
        self.max_utterance_length_ms = max_utterance_length_ms
        
        self.current_state = VADState.SILENCE
        self.silence_frames = 0
        self.speech_start_time_ms: Optional[int] = None
        self.silence_start_time_ms: Optional[int] = None

    def process_frame(self, frame: AudioFrame) -> Optional[VADEvent]:
        vad_state = self.vad.process_frame(frame)
        
        if vad_state == VADState.SPEECH:
            self.silence_frames = 0
            self.silence_start_time_ms = None
            
            if self.current_state == VADState.SILENCE:
                self.current_state = VADState.SPEECH
                self.speech_start_time_ms = frame.timestamp_ms
                return VADEvent.SPEECH_START
            
            if self.speech_start_time_ms is not None:
                speech_duration = frame.timestamp_ms - self.speech_start_time_ms
                if speech_duration >= self.max_utterance_length_ms:
                    self.current_state = VADState.SILENCE
                    self.speech_start_time_ms = None
                    return VADEvent.MAX_UTTERANCE_LENGTH
        
        elif vad_state == VADState.SILENCE:
            if self.current_state == VADState.SPEECH:
                self.silence_frames += 1
                
                if self.silence_start_time_ms is None:
                    self.silence_start_time_ms = frame.timestamp_ms
                
                silence_duration = frame.timestamp_ms - self.silence_start_time_ms
                
                if silence_duration >= self.silence_duration_ms:
                    self.current_state = VADState.SILENCE
                    self.speech_start_time_ms = None
                    self.silence_start_time_ms = None
                    return VADEvent.SPEECH_BOUNDARY
        
        return None

    def set_state(self, state: VADState):
        self.current_state = state
        if state == VADState.SPEECH:
            self.speech_start_time_ms = 0

    def get_silence_duration_ms(self) -> int:
        return self.silence_frames * self.frame_duration_ms


class ConnectionManager:
    def __init__(self, initial_delay: float = 1.0, max_delay: float = 30.0):
        self.initial_delay = initial_delay
        self.max_delay = max_delay
        self.reconnect_count = 0

    def get_backoff_delay(self, attempt: int) -> float:
        delay = self.initial_delay * (2 ** attempt)
        return min(delay, self.max_delay)

    def increment_reconnect(self) -> None:
        self.reconnect_count += 1

    def reset_reconnect(self) -> None:
        self.reconnect_count = 0

    def log_connected(self) -> None:
        import structlog
        structlog.get_logger().info("Connected to server")

    def log_reconnecting(self, delay: float) -> None:
        import structlog
        structlog.get_logger().warning("Reconnecting in {delay}s", attempt=self.reconnect_count, delay=delay)

    def log_lost(self) -> None:
        import structlog
        structlog.get_logger().error("Connection lost")


class ConfigUpdateHandler:
    def __init__(
        self,
        config_adapter,
        server=None,
        audio_adapter=None,
        on_device_change: Optional[Callable] = None
    ):
        self.config_adapter = config_adapter
        self.server = server
        self.audio_adapter = audio_adapter
        self.on_device_change = on_device_change

    async def handle_config_update(self, message: dict) -> None:
        import structlog
        
        logger = structlog.get_logger()
        
        try:
            config = self.config_adapter.load()
            
            if "devices" in message:
                if self.audio_adapter:
                    devices = self.audio_adapter.list_devices()
                    valid_ids = [d.id for d in devices]
                    
                    new_devices = message["devices"]
                    if "input" in new_devices and new_devices["input"] not in valid_ids:
                        raise ValueError(f"Invalid input device ID: {new_devices['input']}")
                    if "output" in new_devices and new_devices["output"] not in valid_ids:
                        raise ValueError(f"Invalid output device ID: {new_devices['output']}")
                
                old_devices = config.devices
                config.devices = message["devices"]
                self.config_adapter.save(config)
                
                if self.on_device_change and old_devices != config.devices:
                    self.on_device_change()
            
            if "label" in message:
                config.label = message["label"]
            
            if "location" in message:
                config.location = message["location"]
            
            if "label" in message or "location" in message:
                self.config_adapter.save(config)
            
            if self.server:
                await self.server.send({
                    "type": "config_updated",
                    "success": True
                })
            
            logger.info("Config updated", message=message)
        except Exception as e:
            logger.warning("Config update failed", error=str(e), message=message)
            
            if self.server:
                await self.server.send({
                    "type": "config_updated",
                    "success": False,
                    "error": str(e)
                })


class VoiceNodeApplication:
    def __init__(self, config_adapter, transcriber: Optional[TranscriberPort] = None, server=None):
        self.config_adapter = config_adapter
        self.config = config_adapter.load()
        self.running = False
        self.server = server
        
        self.vad_tracker = VADTracker(
            aggressiveness=self.config.vad["aggressiveness"],
            silence_duration_ms=self.config.vad["silence_duration_ms"],
            frame_duration_ms=30,
            max_utterance_length_ms=self.config.vad["max_utterance_length_ms"],
        )

        if transcriber is None:
            if self.config.stt_mode == "remote":
                if self.config.server_http_url is None:
                    raise ValueError("server_http_url required when stt_mode is 'remote'")
                from voicenode.adapters.http_transcriber_adapter import HttpTranscriberAdapter
                self.transcriber = HttpTranscriberAdapter(
                    server_http_url=self.config.server_http_url,
                    node_id=self.config.id
                )
            else:
                from voicenode.adapters.whisper_cpp_adapter import WhisperCppAdapter
                self.transcriber = WhisperCppAdapter(self.config.whisper_model)
        else:
            self.transcriber = transcriber

        self.buffered_frames: list[AudioFrame] = []
        self.utterance_start_time_ms: Optional[int] = None
        self.executor = ThreadPoolExecutor(max_workers=1)
        self.pending_utterances: list[str] = []

    def _format_timestamp(self, ms: int) -> str:
        total_seconds = ms // 1000
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        seconds = total_seconds % 60
        return f"[{hours:02d}:{minutes:02d}:{seconds:02d}]"

    def _transcribe_and_print(self, frames: list[AudioFrame], start_time_ms: int) -> None:
        text = self.transcriber.transcribe(frames)
        if text:
            timestamp = self._format_timestamp(start_time_ms)
            print(f"{timestamp} {text}")
            self._send_utterance(text)
        else:
            import structlog
            structlog.get_logger().warning("Empty transcription")

    def _send_utterance(self, text: str) -> None:
        if self.server is None:
            return
        
        message = {"type": "utterance", "text": text}
        
        if self.server.is_connected():
            import asyncio
            try:
                loop = asyncio.get_running_loop()
                loop.call_soon_threadsafe(
                    lambda: asyncio.ensure_future(self.server.send(message))
                )
            except RuntimeError:
                asyncio.run(self.server.send(message))
        else:
            self.pending_utterances.append(text)

    def process_frame(self, frame: AudioFrame) -> Optional[VADEvent]:
        event = self.vad_tracker.process_frame(frame)
        
        if self.vad_tracker.current_state == VADState.SPEECH:
            self.buffered_frames.append(frame)
            if self.utterance_start_time_ms is None:
                self.utterance_start_time_ms = frame.timestamp_ms
        
        if event == VADEvent.SPEECH_START:
            print("Speech detected")
        elif event == VADEvent.SPEECH_BOUNDARY:
            silence_ms = self.vad_tracker.get_silence_duration_ms()
            print(f"Speech boundary (silence: {silence_ms}ms)")
            frames_to_transcribe = self.buffered_frames.copy()
            start_time = self.utterance_start_time_ms or 0
            self.executor.submit(self._transcribe_and_print, frames_to_transcribe, start_time)
            self.buffered_frames = []
            self.utterance_start_time_ms = None
        elif event == VADEvent.MAX_UTTERANCE_LENGTH:
            print("Max utterance length reached")
            frames_to_transcribe = self.buffered_frames.copy()
            start_time = self.utterance_start_time_ms or 0
            self.executor.submit(self._transcribe_and_print, frames_to_transcribe, start_time)
            self.buffered_frames = []
            self.utterance_start_time_ms = None
        
        return event

    async def flush_pending_utterances(self) -> None:
        """Send all pending utterances to server."""
        if self.server is None:
            return
        
        while self.pending_utterances and self.server.is_connected():
            text = self.pending_utterances.pop(0)
            await self.server.send({"type": "utterance", "text": text})

    def stop(self):
        self.running = False
        self.executor.shutdown(wait=True)

    async def _receive_loop(self, audio_output) -> None:
        import structlog
        logger = structlog.get_logger()
        config_update_handler = ConfigUpdateHandler(
            config_adapter=self.config_adapter,
            server=self.server,
        )
        while self.running:
            msg = await self.server.receive()
            if isinstance(msg, bytes):
                device_id = self.config.devices.get("output", 0)
                audio_output.play(msg, device_id)
            elif isinstance(msg, dict):
                msg_type = msg.get("type")
                if msg_type == "config_update":
                    await config_update_handler.handle_config_update(msg)
                elif msg_type == "error":
                    logger.error("Server error", code=msg.get("code"), message=msg.get("message"))

    async def _connect_and_register(self) -> None:
        await self.server.connect()
        await self.server.send({
            "type": "register",
            "id": self.config.id,
            "label": self.config.label,
            "location": self.config.location,
            "capabilities": self.config.capabilities,
        })
        ack = await self.server.receive()
        while ack.get("type") != "registered":
            ack = await self.server.receive()
        await self.flush_pending_utterances()

    async def run_async(self, audio_output) -> None:
        import asyncio
        import threading

        self.running = True
        connection_manager = ConnectionManager()

        capture_thread = threading.Thread(target=self._run_audio_capture, daemon=True)
        capture_thread.start()

        attempt = 0
        while self.running:
            try:
                await self._connect_and_register()
                connection_manager.reset_reconnect()
                attempt = 0

                receive_task = asyncio.create_task(self._receive_loop(audio_output))
                try:
                    await receive_task
                except asyncio.CancelledError:
                    self.running = False
                    raise
            except asyncio.CancelledError:
                self.running = False
                raise
            except Exception:
                connection_manager.log_lost()
                connection_manager.increment_reconnect()
                delay = connection_manager.get_backoff_delay(attempt)
                connection_manager.log_reconnecting(delay)
                attempt += 1
                await asyncio.sleep(delay)

        capture_thread.join(timeout=2.0)

    def _run_audio_capture(self) -> None:
        from voicenode.adapters import SounddeviceAudioAdapter

        audio_adapter = SounddeviceAudioAdapter()
        device_id = self.config.devices["input"]
        frame_gen = audio_adapter.capture_frames(device_id=device_id, duration_ms=30)

        try:
            for frame in frame_gen:
                if not self.running:
                    break
                self.process_frame(frame)
        except KeyboardInterrupt:
            self.running = False

    def run(self):
        from voicenode.adapters import SounddeviceAudioAdapter

        self.running = True
        audio_adapter = SounddeviceAudioAdapter()

        device_id = self.config.devices["input"]
        frame_gen = audio_adapter.capture_frames(device_id=device_id, duration_ms=30)

        try:
            for frame in frame_gen:
                if not self.running:
                    break
                self.process_frame(frame)
        except KeyboardInterrupt:
            print("Stopping...")