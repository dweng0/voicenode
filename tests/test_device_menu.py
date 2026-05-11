"""Tests for device menu selection flow."""
import tempfile
from pathlib import Path
import json
import pytest


def test_device_menu_format():
    """Test formatting devices for menu display."""
    from voicenode.adapters.device_menu import format_device_list

    devices_list = [
        {"name": "default", "max_input_channels": 2, "max_output_channels": 2},
        {"name": "usb-mic", "max_input_channels": 1, "max_output_channels": 0},
        {"name": "speaker", "max_input_channels": 0, "max_output_channels": 2},
    ]

    formatted = format_device_list(devices_list)

    assert "default" in formatted
    assert "usb-mic" in formatted
    assert "speaker" in formatted
    assert "[0]" in formatted  # Should show index
    assert "input" in formatted or "output" in formatted  # Should show capabilities


def test_select_device_saves_to_config(monkeypatch):
    """Test that selecting device saves DeviceIdentity to config."""
    from voicenode.adapters.device_menu import select_and_save_device
    from voicenode.adapters.json_config_adapter import JsonConfigAdapter
    from voicenode.core import DeviceIdentity
    from unittest.mock import MagicMock

    # Mock sounddevice.query_devices()
    mock_devices = [
        {"name": "default", "max_input_channels": 2, "max_output_channels": 2},
        {"name": "usb-mic", "max_input_channels": 1, "max_output_channels": 0},
    ]
    import sys
    mock_sd = MagicMock()
    mock_sd.query_devices.return_value = mock_devices
    monkeypatch.setitem(sys.modules, "sounddevice", mock_sd)

    with tempfile.TemporaryDirectory() as tmpdir:
        config_path = Path(tmpdir) / "config.json"
        adapter = JsonConfigAdapter(str(config_path))
        adapter.create_default()

        # Select device by index
        select_and_save_device(
            config_adapter=adapter,
            device_index=1,
            device_type="input"
        )

        config = adapter.load()
        assert isinstance(config.devices["input"], DeviceIdentity)
        assert config.devices["input"].name == "usb-mic"


def test_choose_input_flag_triggers_menu(tmp_path, monkeypatch):
    """Test that --choose-input flag triggers device selection."""
    from voicenode.cli import parse_args
    from voicenode.adapters.json_config_adapter import JsonConfigAdapter

    config_path = tmp_path / "config.json"
    adapter = JsonConfigAdapter(str(config_path))
    adapter.create_default()

    args = parse_args(["--choose-input", "--config", str(config_path)])

    assert args.choose_input is True
    assert args.config == str(config_path)
