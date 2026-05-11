"""Tests for missing device auto-prompt."""
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest


def test_missing_input_device_detected(monkeypatch):
    """Test that missing input device is detected."""
    from voicenode.adapters.json_config_adapter import JsonConfigAdapter
    from voicenode.core import DeviceIdentity, DeviceRegistry

    # Create config with non-existent device
    with tempfile.TemporaryDirectory() as tmpdir:
        config_path = Path(tmpdir) / "config.json"
        adapter = JsonConfigAdapter(str(config_path))
        adapter.create_default()

        config = adapter.load()
        # Set input to non-existent device
        config.devices["input"] = DeviceIdentity(name="missing-device", index=99, serial=None)
        adapter.save(config)

        # Load and check if device is missing
        config = adapter.load()
        devices_list = [
            {"name": "default", "max_input_channels": 2},
            {"name": "other", "max_input_channels": 1},
        ]
        registry = DeviceRegistry(devices_list)
        device = registry.find(config.devices["input"])

        assert device is None  # Device not found


def test_check_devices_exist():
    """Test checking if devices exist in registry."""
    from voicenode.adapters.json_config_adapter import JsonConfigAdapter
    from voicenode.core import DeviceIdentity, DeviceRegistry

    devices_list = [
        {"name": "default", "max_input_channels": 2, "max_output_channels": 2},
        {"name": "usb-mic", "max_input_channels": 1, "max_output_channels": 0},
    ]

    registry = DeviceRegistry(devices_list)

    # Check existing device
    device_ok = DeviceIdentity(name="default", index=0, serial=None)
    assert registry.find(device_ok) is not None

    # Check missing device
    device_missing = DeviceIdentity(name="missing", index=None, serial=None)
    assert registry.find(device_missing) is None
