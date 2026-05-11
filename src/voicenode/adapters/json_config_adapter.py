import json
from pathlib import Path
import uuid

from voicenode.core import NodeConfig, ConfigPort


class JsonConfigAdapter(ConfigPort):
    def __init__(self, config_path: str = "config.json"):
        self.config_path = Path(config_path)

    def exists(self) -> bool:
        return self.config_path.exists()

    def load(self) -> NodeConfig:
        with open(self.config_path) as f:
            data = json.load(f)
        return NodeConfig(
            id=data["id"],
            label=data["label"],
            location=data["location"],
            server_url=data["server_url"],
            whisper_model=data["whisper_model"],
            devices=data["devices"],
            vad=data["vad"],
            capabilities=data["capabilities"],
            stt_mode=data.get("stt_mode", "local"),
            server_http_url=data.get("server_http_url"),
        )

    def save(self, config: NodeConfig) -> None:
        with open(self.config_path, "w") as f:
            json.dump({
                "id": config.id,
                "label": config.label,
                "location": config.location,
                "server_url": config.server_url,
                "whisper_model": config.whisper_model,
                "devices": config.devices,
                "vad": config.vad,
                "capabilities": config.capabilities,
                "stt_mode": config.stt_mode,
                "server_http_url": config.server_http_url,
            }, f, indent=2)

    def create_default(self) -> NodeConfig:
        config = NodeConfig(
            id=str(uuid.uuid4()),
            label="Voice Node",
            location="unknown",
            server_url="ws://localhost:3001",
            whisper_model="base.en",
            devices={"input": 0, "output": 1},
            vad={
                "aggressiveness": 3,
                "silence_duration_ms": 800,
                "max_utterance_length_ms": 30000,
            },
            capabilities=["mic", "speaker"],
        )
        self.save(config)
        return config