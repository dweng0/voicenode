"""Tests for CLI device override (--input, --output)."""
import tempfile
from pathlib import Path
import pytest
from unittest.mock import MagicMock, patch


def test_cli_input_override_valid_device(monkeypatch):
    """Test that --input with valid device name is accepted."""
    from voicenode.cli import parse_args
    from voicenode.adapters.json_config_adapter import JsonConfigAdapter

    config_path = "config.json"
    args = parse_args(["--input", "usb-mic", "--config", config_path])

    assert args.input == "usb-mic"
    assert args.config == config_path


def test_cli_input_override_device_lookup(monkeypatch):
    """Test that --input device name can be looked up in registry."""
    from voicenode.core import DeviceIdentity, DeviceRegistry

    mock_devices = [
        {"name": "default", "max_input_channels": 2, "max_output_channels": 2},
        {"name": "usb-mic", "max_input_channels": 1, "max_output_channels": 0},
    ]

    # Lookup device by name
    device_identity = DeviceIdentity(name="usb-mic", index=None, serial=None)
    registry = DeviceRegistry(mock_devices)
    device = registry.find(device_identity)

    assert device is not None
    assert device["name"] == "usb-mic"
