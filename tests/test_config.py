import tempfile
from pathlib import Path


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
        assert config.devices == {"input": 0, "output": 1}
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
        config.devices["input"] = 5
        adapter.save(config)

        loaded_config = adapter.load()
        assert loaded_config.devices["input"] == 5


def test_config_update_output_device():
    """Test that config can be updated with new output device."""
    from voicenode.adapters.json_config_adapter import JsonConfigAdapter

    with tempfile.TemporaryDirectory() as tmpdir:
        config_path = Path(tmpdir) / "config.json"
        adapter = JsonConfigAdapter(str(config_path))

        adapter.create_default()
        config = adapter.load()
        config.devices["output"] = 3
        adapter.save(config)

        loaded_config = adapter.load()
        assert loaded_config.devices["output"] == 3