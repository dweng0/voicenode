import tempfile
from pathlib import Path
from voicenode.core import DeviceIdentity


def test_config_creation_with_defaults():
    """Test that first run creates config.json with UUID and defaults."""
    from voicenode.adapters.json_config_adapter import JsonConfigAdapter

    with tempfile.TemporaryDirectory() as tmpdir:
        config_path = Path(tmpdir) / "config.json"
        adapter = JsonConfigAdapter(str(config_path))

        assert not adapter.exists()

        config = adapter.create_default()

        assert adapter.exists()
        assert config.id is not None
        assert len(config.id) == 36  # UUID format
        assert config.label == "Voice Node"
        assert config.location == "unknown"
        assert config.server_url == "ws://localhost:3001"
        assert config.whisper_model == "base.en"
        assert isinstance(config.devices["input"], DeviceIdentity)
        assert isinstance(config.devices["output"], DeviceIdentity)
        assert config.capabilities == ["mic", "speaker"]

        loaded_config = adapter.load()
        assert loaded_config.id == config.id
        assert loaded_config.label == config.label


def test_config_update_input_device():
    """Test that config can be updated with new input device."""
    from voicenode.adapters.json_config_adapter import JsonConfigAdapter

    with tempfile.TemporaryDirectory() as tmpdir:
        config_path = Path(tmpdir) / "config.json"
        adapter = JsonConfigAdapter(str(config_path))

        adapter.create_default()
        config = adapter.load()
        config.devices["input"] = DeviceIdentity(name="usb-mic", index=5, serial="ABC123")
        adapter.save(config)

        loaded_config = adapter.load()
        assert loaded_config.devices["input"].name == "usb-mic"
        assert loaded_config.devices["input"].index == 5
        assert loaded_config.devices["input"].serial == "ABC123"


def test_config_update_output_device():
    """Test that config can be updated with new output device."""
    from voicenode.adapters.json_config_adapter import JsonConfigAdapter

    with tempfile.TemporaryDirectory() as tmpdir:
        config_path = Path(tmpdir) / "config.json"
        adapter = JsonConfigAdapter(str(config_path))

        adapter.create_default()
        config = adapter.load()
        config.devices["output"] = DeviceIdentity(name="speaker", index=3, serial=None)
        adapter.save(config)

        loaded_config = adapter.load()
        assert loaded_config.devices["output"].name == "speaker"
        assert loaded_config.devices["output"].index == 3