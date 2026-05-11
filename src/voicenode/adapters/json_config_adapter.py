import json
from pathlib import Path
import uuid

from voicenode.core import NodeConfig, ConfigPort, DeviceIdentity


class JsonConfigAdapter(ConfigPort):
    def __init__(self, config_path: str = "config.json"):
        self.config_path = Path(config_path)

    def exists(self) -> bool:
        return self.config_path.exists()

    def load(self) -> NodeConfig:
        with open(self.config_path) as f:
            data = json.load(f)

        devices_data = data["devices"]
        devices = {}

        for key in ["input", "output"]:
            if key in devices_data:
                device_data = devices_data[key]

                # Check for old numeric format
                if isinstance(device_data, int):
                    raise ValueError(
                        f"Device selection is now by name. Old config format: \"{key}\": {device_data}\n"
                        f"Run `voicenode --choose-input` to select your device."
                    )

                # Deserialize DeviceIdentity from dict
                if isinstance(device_data, dict):
                    devices[key] = DeviceIdentity(
                        name=device_data["name"],
                        index=device_data.get("index"),
                        serial=device_data.get("serial"),
                    )
                elif isinstance(device_data, DeviceIdentity):
                    devices[key] = device_data

        return NodeConfig(
            id=data["id"],
            label=data["label"],
            location=data["location"],
            server_url=data["server_url"],
            whisper_model=data["whisper_model"],
            devices=devices,
            vad=data["vad"],
            capabilities=data["capabilities"],
            stt_mode=data.get("stt_mode", "local"),
            server_http_url=data.get("server_http_url"),
        )

    def save(self, config: NodeConfig) -> None:
        # Serialize DeviceIdentity to dict
        devices_serialized = {}
        for key, device in config.devices.items():
            if isinstance(device, DeviceIdentity):
                devices_serialized[key] = {
                    "name": device.name,
                    "index": device.index,
                    "serial": device.serial,
                }
            else:
                devices_serialized[key] = device

        with open(self.config_path, "w") as f:
            json.dump({
                "id": config.id,
                "label": config.label,
                "location": config.location,
                "server_url": config.server_url,
                "whisper_model": config.whisper_model,
                "devices": devices_serialized,
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
            devices={
                "input": DeviceIdentity(name="default", index=0, serial=None),
                "output": DeviceIdentity(name="default", index=1, serial=None),
            },
            vad={
                "aggressiveness": 3,
                "silence_duration_ms": 800,
                "max_utterance_length_ms": 30000,
            },
            capabilities=["mic", "speaker"],
        )
        self.save(config)
        return config