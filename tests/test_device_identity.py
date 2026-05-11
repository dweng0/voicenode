import tempfile
from pathlib import Path
import json
import pytest


def test_device_identity_creation_and_save():
    """Test that DeviceIdentity can be created and saved to config."""
    from voicenode.core import DeviceIdentity
    from voicenode.adapters.json_config_adapter import JsonConfigAdapter

    # Create a DeviceIdentity
    device = DeviceIdentity(name="default", index=4, serial=None)

    assert device.name == "default"
    assert device.index == 4
    assert device.serial is None

    # Save to config and load back
    with tempfile.TemporaryDirectory() as tmpdir:
        config_path = Path(tmpdir) / "config.json"
        adapter = JsonConfigAdapter(str(config_path))

        config = adapter.create_default()
        config.devices["input"] = device
        adapter.save(config)

        loaded_config = adapter.load()
        loaded_device = loaded_config.devices["input"]

        assert isinstance(loaded_device, DeviceIdentity)
        assert loaded_device.name == "default"
        assert loaded_device.index == 4
        assert loaded_device.serial is None


def test_reject_old_numeric_device_format():
    """Test that old numeric device format is rejected with helpful error."""
    from voicenode.adapters.json_config_adapter import JsonConfigAdapter

    with tempfile.TemporaryDirectory() as tmpdir:
        config_path = Path(tmpdir) / "config.json"

        # Write old numeric format config manually
        old_config = {
            "id": "test-id",
            "label": "Voice Node",
            "location": "unknown",
            "server_url": "ws://localhost:3001",
            "whisper_model": "base.en",
            "devices": {"input": 5, "output": 1},
            "vad": {
                "aggressiveness": 3,
                "silence_duration_ms": 800,
                "max_utterance_length_ms": 30000,
            },
            "capabilities": ["mic", "speaker"],
        }

        with open(config_path, "w") as f:
            json.dump(old_config, f)

        adapter = JsonConfigAdapter(str(config_path))

        with pytest.raises(ValueError) as exc_info:
            adapter.load()

        assert "Device selection is now by name" in str(exc_info.value)
        assert "--choose-input" in str(exc_info.value)
