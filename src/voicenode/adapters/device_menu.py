"""Interactive device selection menu."""
from voicenode.core import DeviceIdentity


def format_device_list(devices_list: list) -> str:
    """Format devices for menu display with index, name, and capabilities."""
    lines = []
    for i, device in enumerate(devices_list):
        name = device.get("name", "unknown")
        input_ch = device.get("max_input_channels", 0)
        output_ch = device.get("max_output_channels", 0)

        capabilities = []
        if input_ch > 0:
            capabilities.append(f"input({input_ch})")
        if output_ch > 0:
            capabilities.append(f"output({output_ch})")
        cap_str = ", ".join(capabilities) if capabilities else "none"

        lines.append(f"[{i}] {name} - {cap_str}")

    return "\n".join(lines)


def select_and_save_device(config_adapter, device_index: int, device_type: str) -> None:
    """
    Select device by index and save to config.

    Args:
        config_adapter: JsonConfigAdapter instance
        device_index: Index of device to select
        device_type: "input" or "output"
    """
    import sounddevice as sd
    from voicenode.core import DeviceRegistry

    devices_list = sd.query_devices()
    registry = DeviceRegistry(devices_list)

    # Get device at index
    device = devices_list[device_index]

    # Create DeviceIdentity
    device_identity = DeviceIdentity(
        name=device.get("name"),
        index=device_index,
        serial=device.get("serial"),
    )

    # Save to config
    config = config_adapter.load()
    config.devices[device_type] = device_identity
    config_adapter.save(config)


def check_and_prompt_missing_devices(config_adapter):
    """
    Check if configured devices exist. If missing, prompt user to select new device.
    Returns True if devices are OK, False if user cancelled or error.
    """
    import sounddevice as sd
    from voicenode.core import DeviceRegistry

    config = config_adapter.load()
    devices_list = sd.query_devices()

    # If no devices available (e.g., in test environment), skip check
    if not devices_list:
        return True

    registry = DeviceRegistry(devices_list)

    missing_devices = []

    # Check input device
    if "input" in config.devices:
        device = registry.find(config.devices["input"])
        if device is None:
            missing_devices.append("input")

    # Check output device
    if "output" in config.devices:
        device = registry.find(config.devices["output"])
        if device is None:
            missing_devices.append("output")

    if not missing_devices:
        return True  # All devices OK

    # Devices are missing, prompt user
    for device_type in missing_devices:
        print(f"\n⚠️  Your {device_type} device is not available.")
        print("\n=== Select {0} Device ===".format(device_type.capitalize()))
        print(format_device_list(devices_list))
        print()

        try:
            device_index = int(input(f"Enter device number: "))
            if device_index < 0 or device_index >= len(devices_list):
                print(f"Error: Device {device_index} not found")
                return False

            select_and_save_device(
                config_adapter=config_adapter,
                device_index=device_index,
                device_type=device_type
            )
            print(f"Saved {device_type} device: {devices_list[device_index]['name']}")
        except (ValueError, EOFError):
            print("Error: Invalid device number or no input available")
            return False

    return True
