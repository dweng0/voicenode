"""Tests for DeviceRegistry device lookup."""
import pytest


def test_device_registry_find_by_name():
    """Test finding device by name."""
    from voicenode.core import DeviceRegistry, DeviceIdentity

    # Simulate sounddevice.query_devices() output
    devices_list = [
        {"name": "default", "max_input_channels": 2, "max_output_channels": 2},
        {"name": "usb-mic", "max_input_channels": 1, "max_output_channels": 0},
        {"name": "speaker", "max_input_channels": 0, "max_output_channels": 2},
    ]

    registry = DeviceRegistry(devices_list)

    # Find by name
    device = registry.find(DeviceIdentity(name="usb-mic", index=None, serial=None))

    assert device is not None
    assert device["name"] == "usb-mic"


def test_device_registry_find_by_index():
    """Test finding device by index."""
    from voicenode.core import DeviceRegistry, DeviceIdentity

    devices_list = [
        {"name": "default", "max_input_channels": 2, "max_output_channels": 2},
        {"name": "usb-mic", "max_input_channels": 1, "max_output_channels": 0},
    ]

    registry = DeviceRegistry(devices_list)

    # Find by index only (name mismatch, but index matches)
    device = registry.find(DeviceIdentity(name="wrong-name", index=1, serial=None))

    assert device is not None
    assert device["name"] == "usb-mic"


def test_device_registry_find_missing():
    """Test finding non-existent device returns None."""
    from voicenode.core import DeviceRegistry, DeviceIdentity

    devices_list = [
        {"name": "default", "max_input_channels": 2, "max_output_channels": 2},
    ]

    registry = DeviceRegistry(devices_list)

    device = registry.find(DeviceIdentity(name="missing", index=None, serial=None))

    assert device is None


def test_device_registry_find_priority():
    """Test matching priority: serial > name > index."""
    from voicenode.core import DeviceRegistry, DeviceIdentity

    devices_list = [
        {"name": "device-a", "max_input_channels": 2, "max_output_channels": 0, "serial": "ABC123"},
        {"name": "device-b", "max_input_channels": 2, "max_output_channels": 0, "serial": "DEF456"},
    ]

    registry = DeviceRegistry(devices_list)

    # Serial should match first, even if name and index don't match
    device = registry.find(DeviceIdentity(name="wrong-name", index=99, serial="DEF456"))

    assert device is not None
    assert device["serial"] == "DEF456"
    assert device["name"] == "device-b"
