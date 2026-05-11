import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest


def test_build_server_url_constructs_ws_url():
    from voicenode.cli import build_server_url

    assert build_server_url("192.168.1.112") == "ws://192.168.1.112:3001"


def test_validate_ipv4_accepts_valid_ip():
    from voicenode.cli import validate_ipv4

    assert validate_ipv4("192.168.1.112") is True


def test_validate_ipv4_rejects_hostname():
    from voicenode.cli import validate_ipv4

    assert validate_ipv4("myhousekeeper.local") is False


def test_validate_ipv4_rejects_partial_ip():
    from voicenode.cli import validate_ipv4

    assert validate_ipv4("192.168.1") is False


def test_validate_ipv4_rejects_url_with_scheme():
    from voicenode.cli import validate_ipv4

    assert validate_ipv4("http://192.168.1.112") is False


def test_server_flag_saves_server_url_to_config():
    with tempfile.TemporaryDirectory() as tmpdir:
        config_path = Path(tmpdir) / "config.json"

        from voicenode.adapters.json_config_adapter import JsonConfigAdapter
        adapter = JsonConfigAdapter(str(config_path))
        adapter.create_default()

        mock_structlog = MagicMock()
        mock_structlog.get_logger.return_value = MagicMock()
        mock_sd = MagicMock()
        mock_sd.query_devices.return_value = [
            {"name": "default", "max_input_channels": 2, "max_output_channels": 2}
        ]

        with patch("sys.argv", ["voicenode", "--server", "192.168.1.112", "--config", str(config_path)]):
            with patch("asyncio.run"):
                with patch.dict("sys.modules", {"structlog": mock_structlog, "sounddevice": mock_sd}):
                    with patch("voicenode.core.VoiceNodeApplication") as mock_app_cls:
                        mock_app_cls.return_value.config = adapter.load()
                        with patch("voicenode.adapters.SounddeviceAudioAdapter"):
                            with patch("voicenode.adapters.websockets_adapter.WebsocketsAdapter"):
                                with patch("voicenode.logging_config.setup_logging"):
                                    from voicenode.cli import main
                                    main()

        config = adapter.load()
        assert config.server_url == "ws://192.168.1.112:3001"


def test_server_flag_invalid_ip_exits_without_saving(capsys):
    with tempfile.TemporaryDirectory() as tmpdir:
        config_path = Path(tmpdir) / "config.json"

        from voicenode.adapters.json_config_adapter import JsonConfigAdapter
        adapter = JsonConfigAdapter(str(config_path))
        adapter.create_default()

        with patch("sys.argv", ["voicenode", "--server", "not-an-ip", "--config", str(config_path)]):
            from voicenode.cli import main
            main()

        config = adapter.load()
        assert config.server_url == "ws://localhost:3001"
        captured = capsys.readouterr()
        assert "Error" in captured.out
        assert "not-an-ip" in captured.out
