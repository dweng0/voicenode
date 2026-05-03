from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Iterator


@dataclass
class AudioDevice:
    id: int
    name: str
    channels: int
    is_input: bool
    is_output: bool
    is_default: bool = False


@dataclass
class AudioFrame:
    data: bytes
    timestamp_ms: int


class VADState(Enum):
    SILENCE = "silence"
    SPEECH = "speech"


class VADEvent(Enum):
    SPEECH_START = "speech_start"
    SPEECH_BOUNDARY = "speech_boundary"
    MAX_UTTERANCE_LENGTH = "max_utterance_length"


class AudioPort(ABC):
    @abstractmethod
    def list_devices(self) -> list[AudioDevice]:
        """List available audio devices."""
        ...

    @abstractmethod
    def capture_frames(self, device_id: int, duration_ms: int = 100) -> Iterator[AudioFrame]:
        """Capture audio frames from device."""
        ...


class AudioOutputPort(ABC):
    @abstractmethod
    def play(self, audio: bytes, device_id: int) -> None:
        """Play PCM audio on output device."""
        ...

    @abstractmethod
    def stop_playback(self) -> None:
        """Stop current playback."""
        ...


class VADPort(ABC):
    @abstractmethod
    def process_frame(self, frame: AudioFrame) -> VADState:
        """Process audio frame and return VAD state."""
        ...


class TranscriberPort(ABC):
    @abstractmethod
    def transcribe(self, frames: list[AudioFrame]) -> str:
        """Transcribe audio frames to text."""
        ...


class ServerPort(ABC):
    @abstractmethod
    async def connect(self) -> None:
        """Connect to server."""
        ...

    @abstractmethod
    async def send(self, message: dict) -> None:
        """Send message to server."""
        ...

    @abstractmethod
    async def receive(self) -> dict:
        """Receive message from server."""
        ...

    @abstractmethod
    async def close(self) -> None:
        """Close connection."""
        ...

    @abstractmethod
    def is_connected(self) -> bool:
        """Check if connected to server."""
        ...