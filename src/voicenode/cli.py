import argparse
import time
import numpy as np

import voicenode
from voicenode.adapters import SounddeviceAudioAdapter
from voicenode.adapters.json_config_adapter import JsonConfigAdapter


import re

_IPV4_RE = re.compile(r"^(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})$")


def validate_ipv4(ip: str) -> bool:
    m = _IPV4_RE.match(ip)
    if not m:
        return False
    return all(0 <= int(o) <= 255 for o in m.groups())


def build_server_url(ip: str) -> str:
    return f"ws://{ip}:3001"


def get_audio_adapter():
    return SounddeviceAudioAdapter()


def get_config_adapter(config_path: str = "config.json"):
    return JsonConfigAdapter(config_path)


def calculate_rms(audio_data: bytes) -> float:
    samples = np.frombuffer(audio_data, dtype=np.int16)
    return np.sqrt(np.mean(samples.astype(np.float32) ** 2))


def run_log(lines: int = 20):
    from voicenode.logging_config import get_log_path
    
    log_path = get_log_path()
    
    if not log_path.exists():
        print("No logs found. Run voicenode first.")
        return
    
    with open(log_path, "r") as f:
        for line in f:
            pass
        
        f.seek(0)
        all_lines = f.readlines()
        
    for line in all_lines[-lines:]:
        print(line.rstrip())
    
    try:
        with open(log_path, "r") as f:
            f.seek(0, 2)
            while True:
                line = f.readline()
                if line:
                    print(line.rstrip())
                else:
                    time.sleep(0.1)
    except KeyboardInterrupt:
        print("\nStopping...")


def run_monitor(device_id: int, audio_adapter, vad_tracker=None, transcriber=None, stop_after=None):
    from voicenode.ports import VADState, VADEvent, AudioFrame
    from voicenode.core import VADTracker
    
    if vad_tracker is None:
        vad_tracker = VADTracker()
    
    if transcriber is None:
        from voicenode.adapters.whisper_cpp_adapter import WhisperCppAdapter
        transcriber = WhisperCppAdapter("base.en")
    
    frame_count = 0
    buffered_frames: list[AudioFrame] = []
    
    try:
        for frame in audio_adapter.capture_frames(device_id=device_id, duration_ms=100):
            rms = calculate_rms(frame.data)
            event = vad_tracker.process_frame(frame)
            
            if vad_tracker.current_state == VADState.SPEECH:
                buffered_frames.append(frame)
            
            status = "speech" if vad_tracker.current_state == VADState.SPEECH else "silence"
            print(f"Level: {rms:.0f} | VAD: {status}")
            
            if event == VADEvent.SPEECH_BOUNDARY:
                text = transcriber.transcribe(buffered_frames)
                if text:
                    print(f"Transcribed: {text}")
                buffered_frames = []
            
            frame_count += 1
            if stop_after is not None and frame_count >= stop_after:
                break
    except KeyboardInterrupt:
        print("Stopping...")


def parse_args(argv=None):
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(prog="voicenode", description="Voice node client")
    subparsers = parser.add_subparsers(dest="command")

    monitor_parser = subparsers.add_parser("monitor", help="Monitor audio device")
    monitor_parser.add_argument("device_id", type=int, help="Audio device ID to monitor")

    log_parser = subparsers.add_parser("log", help="Tail log file")
    log_parser.add_argument("-n", "--lines", type=int, default=20, help="Number of lines to show initially")

    parser.add_argument("--version", action="store_true", help="Show version")
    parser.add_argument("--list-devices", action="store_true", help="List audio devices")
    parser.add_argument("--input", type=str, metavar="NAME", help="Set input device by name")
    parser.add_argument("--output", type=str, metavar="NAME", help="Set output device by name")
    parser.add_argument("--choose-input", action="store_true", help="Interactive menu to select input device")
    parser.add_argument("--choose-output", action="store_true", help="Interactive menu to select output device")
    parser.add_argument("--server", type=str, metavar="IP", help="Set housekeeper IP address (e.g. 192.168.1.112)")
    parser.add_argument("--config", type=str, metavar="PATH", default="config.json", help="Config file path")

    return parser.parse_args(argv)


def main():
    args = parse_args()

    if args.version:
        print(f"voicenode {voicenode.__version__}")
        return

    if args.command == "log":
        run_log(args.lines)
        return

    if args.command == "monitor":
        audio_adapter = get_audio_adapter()
        run_monitor(args.device_id, audio_adapter)
        return

    if args.list_devices:
        adapter = get_audio_adapter()
        devices = adapter.list_devices()
        for dev in devices:
            flags = []
            if dev.is_input:
                flags.append("input")
            if dev.is_output:
                flags.append("output")
            if dev.is_default:
                flags.append("default")
            flag_str = ", ".join(flags)
            print(f"[{dev.id}] {dev.name} ({flag_str})")
        return

    config_adapter = get_config_adapter(args.config)

    if not config_adapter.exists():
        config_adapter.create_default()

    # Handle --choose-input and --choose-output (interactive menu)
    if args.choose_input or args.choose_output:
        from voicenode.adapters.device_menu import format_device_list, select_and_save_device
        import sounddevice as sd

        devices_list = sd.query_devices()

        if args.choose_input:
            device_type = "input"
            print("\n=== Select Input Device ===")
        else:
            device_type = "output"
            print("\n=== Select Output Device ===")

        print(format_device_list(devices_list))
        print()

        try:
            device_index = int(input(f"Enter device number: "))
            if device_index < 0 or device_index >= len(devices_list):
                print(f"Error: Device {device_index} not found")
                return

            select_and_save_device(
                config_adapter=config_adapter,
                device_index=device_index,
                device_type=device_type
            )
            print(f"Saved {device_type} device: {devices_list[device_index]['name']}")
        except ValueError:
            print("Error: Invalid device number")
            return

        return

    # Handle --input and --output device name overrides (one-time, don't save)
    if args.input is not None or args.output is not None:
        import sounddevice as sd
        from voicenode.core import DeviceRegistry, DeviceIdentity

        config = config_adapter.load()
        devices_list = sd.query_devices()
        registry = DeviceRegistry(devices_list)

        if args.input is not None:
            device = registry.find(DeviceIdentity(name=args.input, index=None, serial=None))
            if device is None:
                print(f"Error: Device '{args.input}' not found. Run `voicenode --choose-input` to select a device.")
                return
            device_index = devices_list.index(device) if device in devices_list else None
            config.devices["input"] = DeviceIdentity(
                name=args.input,
                index=device_index,
                serial=device.get("serial")
            )

        if args.output is not None:
            device = registry.find(DeviceIdentity(name=args.output, index=None, serial=None))
            if device is None:
                print(f"Error: Device '{args.output}' not found. Run `voicenode --choose-output` to select a device.")
                return
            device_index = devices_list.index(device) if device in devices_list else None
            config.devices["output"] = DeviceIdentity(
                name=args.output,
                index=device_index,
                serial=device.get("serial")
            )
    else:
        config = config_adapter.load()

    if args.server is not None:
        if not validate_ipv4(args.server):
            print(f"Error: '{args.server}' is not a valid IPv4 address")
            return
        url = build_server_url(args.server)
        config = config_adapter.load()
        config.server_url = url
        config_adapter.save(config)
        print(f"Config updated: server={url}")

    # Check for missing devices and prompt if needed
    from voicenode.adapters.device_menu import check_and_prompt_missing_devices
    if not check_and_prompt_missing_devices(config_adapter):
        return

    import asyncio
    from voicenode.core import VoiceNodeApplication
    from voicenode.adapters import SounddeviceAudioAdapter
    from voicenode.adapters.websockets_adapter import WebsocketsAdapter
    from voicenode.logging_config import setup_logging

    setup_logging()

    audio_output = SounddeviceAudioAdapter()
    server = WebsocketsAdapter(config_adapter.load().server_url)

    app = VoiceNodeApplication(config_adapter=config_adapter, server=server)
    print(f"Starting voice node (id={app.config.id})")
    print(f"Input device: {app.config.devices['input']} | Output device: {app.config.devices['output']}")
    print("Listening for speech...")
    asyncio.run(app.run_async(audio_output))


if __name__ == "__main__":
    main()