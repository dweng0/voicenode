import subprocess
from unittest.mock import patch, MagicMock


def test_version_flag():
    result = subprocess.run(
        ["voicenode", "--version"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "0.1.0" in result.stdout


def test_help_flag():
    result = subprocess.run(
        ["voicenode", "--help"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "usage: voicenode" in result.stdout.lower() or "usage:" in result.stdout.lower()


def test_list_devices_mocked():
    """Test list_devices at adapter level with mocked sounddevice."""
    mock_sd = MagicMock()
    mock_sd.query_devices.return_value = [
        {"name": "Built-in Microphone", "max_input_channels": 2, "max_output_channels": 0},
        {"name": "Built-in Speaker", "max_input_channels": 0, "max_output_channels": 2},
    ]
    mock_sd.default.device = (0, 1)

    with patch.dict("sys.modules", {"sounddevice": mock_sd}):
        from voicenode.adapters import SounddeviceAudioAdapter

        adapter = SounddeviceAudioAdapter()
        devices = adapter.list_devices()

        assert len(devices) == 2
        assert devices[0].name == "Built-in Microphone"
        assert devices[0].is_input is True
        assert devices[0].is_output is False
        assert devices[1].name == "Built-in Speaker"
        assert devices[1].is_input is False
        assert devices[1].is_output is True