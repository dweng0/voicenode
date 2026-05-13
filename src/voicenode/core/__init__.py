from dataclasses import dataclass
from abc import ABC, abstractmethod
from typing import Optional, Callable, Union
from concurrent.futures import ThreadPoolExecutor

from voicenode.ports import AudioFrame, VADState, VADEvent, TranscriberPort
from voicenode.core.stop_word_detector import StopWordDetector


@dataclass
class DeviceIdentity:
    """Stable device identifier: name (required), index and serial (optional, for matching)."""
    name: str
    index: Optional[int] = None
    serial: Optional[str] = None


class DeviceRegistry:
    """Registry of available audio devices with fuzzy matching."""

    def __init__(self, devices_list):
        """Initialize registry from sounddevice.query_devices() output."""
        self.devices = {}  # index -> device dict
        for i, device_dict in enumerate(devices_list):
            self.devices[i] = device_dict

    def find(self, device_identity: "DeviceIdentity") -> Optional[dict]:
        """
        Find device in registry by DeviceIdentity.
        Matching priority: serial > name > index.
        Returns device dict or None if not found.
        """
        # Priority 1: Match by serial number
        if device_identity.serial:
            for device in self.devices.values():
                if device.get("serial") == device_identity.serial:
                    return device

        # Priority 2: Match by name
        if device_identity.name:
            for device in self.devices.values():
                if device.get("name") == device_identity.name:
                    return device

        # Priority 3: Match by index
        if device_identity.index is not None:
            return self.devices.get(device_identity.index)

        return None


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

        self.stop_word_detector = StopWordDetector(server=server)

        # Initialize AEC engine
        from voicenode.audio.aec_engine import AecEngine
        self.aec_engine = AecEngine(sample_rate=16000)

        self.buffered_frames: list[AudioFrame] = []
        self.utterance_start_time_ms: Optional[int] = None
        self.executor = ThreadPoolExecutor(max_workers=1)
        self.pending_utterances: list[str] = []
        self.current_stream_token: Optional[str] = None
        self.current_stream_is_aec_ref: bool = False  # legacy (Option A); kept for tests
        self.current_stream_use_for_aec: bool = False
        self.current_stream_sample_rate: int = 24000
        self.pending_audio_frames: list[bytes] = []  # Queue for audio until stream_start

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
                    lambda: asyncio.ensure_future(self._send_and_check_stop_word(message, text))
                )
            except RuntimeError:
                asyncio.run(self._send_and_check_stop_word(message, text))
        else:
            self.pending_utterances.append(text)

    async def _send_and_check_stop_word(self, message: dict, text: str) -> None:
        """Send utterance (if not gated by TTS playback) and check for stop-words.

        During TTS playback (is_listening=True), suppress ambient utterances
        and only send stop_word signals. During normal listening, send all
        utterances.
        """
        # Only send utterance if not in gated mode (not during TTS playback)
        if not self.stop_word_detector.is_listening:
            await self.server.send(message)

        # Always check for stop-words (sends signal if match and listening)
        await self.stop_word_detector.check_utterance(text)

    def process_frame(self, frame: AudioFrame) -> Optional[VADEvent]:
        # Echo-cancel mic audio against buffered TTS reference.
        cancelled = self.aec_engine.cancel_echo(frame.data, timestamp_ms=frame.timestamp_ms)
        if cancelled is not frame.data:
            frame = AudioFrame(data=cancelled, timestamp_ms=frame.timestamp_ms)

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

    def _on_playback_complete(self, stream_token: str) -> None:
        """Callback when TTS playback finishes."""
        if self.server is None or not self.server.is_connected():
            return

        import asyncio
        try:
            loop = asyncio.get_running_loop()
            loop.call_soon_threadsafe(
                lambda: asyncio.ensure_future(
                    self.server.send({"type": "tts_stream_complete", "streamToken": stream_token})
                )
            )
        except RuntimeError:
            asyncio.run(self.server.send({"type": "tts_stream_complete", "streamToken": stream_token}))

    def stop(self):
        self.running = False
        self.executor.shutdown(wait=True)

    async def _receive_loop(self, audio_output) -> None:
        import structlog
        import traceback
        logger = structlog.get_logger()
        config_update_handler = ConfigUpdateHandler(
            config_adapter=self.config_adapter,
            server=self.server,
        )

        # Cache device list for name lookup
        devices = audio_output.list_devices()
        device_map = {d.id: d.name for d in devices}

        while self.running:
            msg = await self.server.receive()
            if isinstance(msg, bytes):
                # Legacy AEC-only stream (Option A): chunk goes to AEC, not speaker.
                if self.current_stream_is_aec_ref:
                    self.aec_engine.add_reference_chunk(
                        msg, source_rate=self.current_stream_sample_rate
                    )
                    continue

                # Tee: feed AEC reference if server flagged this stream for AEC.
                if self.current_stream_use_for_aec:
                    self.aec_engine.add_reference_chunk(
                        msg, source_rate=self.current_stream_sample_rate
                    )

                device_config = self.config.devices.get("output", 0)
                device_id = device_config.index if isinstance(device_config, DeviceIdentity) else device_config
                device_name = device_map.get(device_id, f"unknown (id={device_id})")
                size_bytes = len(msg)

                # Queue audio until stream_start gate activates. Prevents playback before
                # gating, which would cause mic echo to be captured as ambient utterance.
                if self.stop_word_detector.is_listening:
                    print(f"TTS received: {size_bytes} bytes, device {device_name}")
                    try:
                        audio_output.play(
                            msg,
                            device_id,
                            stream_token=self.current_stream_token,
                            sample_rate=self.current_stream_sample_rate,
                        )
                        print(f"TTS playback started on device {device_name}")
                    except Exception as e:
                        print(f"TTS playback error on device {device_name}: {e}")
                        traceback.print_exc()
                else:
                    print(f"TTS queued: {size_bytes} bytes (waiting for stream_start)")
                    self.pending_audio_frames.append(msg)
            elif isinstance(msg, dict):
                msg_type = msg.get("type")
                if msg_type == "config_update":
                    await config_update_handler.handle_config_update(msg)
                elif msg_type == "error":
                    logger.error("Server error", code=msg.get("code"), message=msg.get("message"))
                elif msg_type == "tts_stream_start":
                    stream_token = msg.get("streamToken")
                    is_aec_ref = bool(msg.get("isAecReference", False))
                    self.current_stream_token = stream_token
                    self.current_stream_is_aec_ref = is_aec_ref
                    self.current_stream_use_for_aec = bool(msg.get("useForAec", False))
                    self.current_stream_sample_rate = int(msg.get("sampleRate", 24000))

                    if is_aec_ref:
                        logger.info(f"AEC reference stream start: {stream_token}")
                        # Do NOT activate stop_word_detector gate — AEC stream is silent to user.
                        continue

                    self.stop_word_detector.on_tts_stream_start(stream_token=stream_token)
                    # Flush queued audio frames now that gate is active
                    while self.pending_audio_frames:
                        audio_data = self.pending_audio_frames.pop(0)
                        device_config = self.config.devices.get("output", 0)
                        device_id = device_config.index if isinstance(device_config, DeviceIdentity) else device_config
                        device_name = device_map.get(device_id, f"unknown (id={device_id})")
                        size_bytes = len(audio_data)
                        print(f"TTS queued flush: {size_bytes} bytes, device {device_name}")
                        if self.current_stream_use_for_aec:
                            self.aec_engine.add_reference_chunk(
                                audio_data, source_rate=self.current_stream_sample_rate
                            )
                        try:
                            audio_output.play(
                                audio_data,
                                device_id,
                                stream_token=self.current_stream_token,
                                sample_rate=self.current_stream_sample_rate,
                            )
                            print(f"TTS playback started (from queue)")
                        except Exception as e:
                            print(f"TTS playback error: {e}")
                            traceback.print_exc()
                elif msg_type == "tts_stream_end":
                    stream_token = msg.get("streamToken")
                    if self.current_stream_is_aec_ref:
                        self.aec_engine.on_stream_end()
                    else:
                        if self.current_stream_use_for_aec:
                            self.aec_engine.on_stream_end()
                        self.stop_word_detector.on_tts_stream_end(stream_token=stream_token)
                        if self.pending_audio_frames:
                            logger.warning(
                                f"Discarding {len(self.pending_audio_frames)} queued audio frames on stream end"
                            )
                            self.pending_audio_frames.clear()
                        # Flush VAD buffer accumulated during TTS playback. Echo from the
                        # speaker is detected as speech; without this flush the accumulated
                        # frames reach Whisper after the stop-word gate closes and the
                        # echo transcription reaches the classifier.
                        discarded = len(self.buffered_frames)
                        if discarded:
                            span_ms = self.buffered_frames[-1].timestamp_ms - self.buffered_frames[0].timestamp_ms
                            logger.info(f"Flushed {discarded} VAD frames ({span_ms}ms) accumulated during TTS playback")
                        self.buffered_frames = []
                        self.utterance_start_time_ms = None
                        self.vad_tracker.set_state(VADState.SILENCE)
                    self.current_stream_is_aec_ref = False
                    self.current_stream_use_for_aec = False
                    self.current_stream_token = None

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

    async def run_async(self, audio_output=None) -> None:
        import asyncio
        import threading

        if audio_output is None:
            from voicenode.adapters import SounddeviceAudioAdapter
            audio_output = SounddeviceAudioAdapter(on_playback_complete=self._on_playback_complete)

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
            except Exception as e:
                import traceback
                import structlog
                structlog.get_logger().error(
                    "Receive loop exception",
                    error=str(e),
                    error_type=type(e).__name__,
                    traceback=traceback.format_exc(),
                )
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
        device_config = self.config.devices["input"]
        # Extract index from DeviceIdentity or use directly if int
        device_id = device_config.index if isinstance(device_config, DeviceIdentity) else device_config
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
        audio_adapter = SounddeviceAudioAdapter(on_playback_complete=self._on_playback_complete)

        device_config = self.config.devices["input"]
        # Extract index from DeviceIdentity or use directly if int
        device_id = device_config.index if isinstance(device_config, DeviceIdentity) else device_config
        frame_gen = audio_adapter.capture_frames(device_id=device_id, duration_ms=30)

        try:
            for frame in frame_gen:
                if not self.running:
                    break
                self.process_frame(frame)
        except KeyboardInterrupt:
            print("Stopping...")