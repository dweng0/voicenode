import asyncio
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, AsyncMock, patch, call


def make_config_adapter():
    from voicenode.adapters.json_config_adapter import JsonConfigAdapter
    with tempfile.TemporaryDirectory() as tmpdir:
        config_path = Path(tmpdir) / "config.json"
        adapter = JsonConfigAdapter(str(config_path))
        adapter.create_default()
        return adapter, tmpdir


def make_server(recv_messages=None):
    server = MagicMock()
    server.is_connected = MagicMock(return_value=True)
    server.connect = AsyncMock()
    server.send = AsyncMock()
    server.close = AsyncMock()
    if recv_messages is None:
        recv_messages = [{"type": "registered", "status": "new"}]
    server.receive = AsyncMock(side_effect=recv_messages + [asyncio.CancelledError()])
    return server


def _noop_audio_capture(self):
    """Stub that blocks until self.running goes False (no sounddevice needed)."""
    import time
    while self.running:
        time.sleep(0.01)


def test_run_async_registers_before_receive_loop():
    """run_async sends register then awaits registered ACK before entering receive loop."""
    import json

    with tempfile.TemporaryDirectory() as tmpdir:
        config_path = Path(tmpdir) / "config.json"
        from voicenode.adapters.json_config_adapter import JsonConfigAdapter
        config_adapter = JsonConfigAdapter(str(config_path))
        config_adapter.create_default()

        mock_webrtcvad = MagicMock()
        mock_vad = MagicMock()
        mock_vad.is_speech.return_value = False
        mock_webrtcvad.Vad.return_value = mock_vad

        server = make_server(recv_messages=[
            {"type": "registered", "status": "new"},
        ])
        mock_transcriber = MagicMock()
        mock_audio_output = MagicMock()
        mock_audio_output.play = MagicMock()

        mock_structlog = MagicMock()
        mock_structlog.get_logger.return_value = MagicMock()

        with patch.dict("sys.modules", {"webrtcvad": mock_webrtcvad, "structlog": mock_structlog}):
            from voicenode.core import VoiceNodeApplication

            app = VoiceNodeApplication(
                config_adapter=config_adapter,
                transcriber=mock_transcriber,
                server=server,
            )

            with patch.object(VoiceNodeApplication, "_run_audio_capture", _noop_audio_capture):
                async def run_with_timeout():
                    try:
                        await asyncio.wait_for(app.run_async(mock_audio_output), timeout=0.5)
                    except (asyncio.TimeoutError, asyncio.CancelledError):
                        pass

                asyncio.run(run_with_timeout())

        # register message sent
        send_calls = [c[0][0] for c in server.send.call_args_list]
        assert any(m.get("type") == "register" for m in send_calls)
        # registered ACK received (receive called at least once)
        assert server.receive.call_count >= 1


def test_receive_loop_plays_binary_tts_frames():
    """Binary frames from server are played via AudioOutputPort.play(data, output_device_id)."""
    tts_audio = b"\x00\x01\x02\x03" * 256

    with tempfile.TemporaryDirectory() as tmpdir:
        config_path = Path(tmpdir) / "config.json"
        from voicenode.adapters.json_config_adapter import JsonConfigAdapter
        config_adapter = JsonConfigAdapter(str(config_path))
        config_adapter.create_default()

        mock_webrtcvad = MagicMock()
        mock_webrtcvad.Vad.return_value = MagicMock()
        mock_structlog = MagicMock()
        mock_structlog.get_logger.return_value = MagicMock()

        server = make_server(recv_messages=[
            {"type": "registered", "status": "new"},
            tts_audio,
        ])
        mock_audio_output = MagicMock()

        with patch.dict("sys.modules", {"webrtcvad": mock_webrtcvad, "structlog": mock_structlog}):
            from voicenode.core import VoiceNodeApplication

            app = VoiceNodeApplication(
                config_adapter=config_adapter,
                transcriber=MagicMock(),
                server=server,
            )

            with patch.object(VoiceNodeApplication, "_run_audio_capture", _noop_audio_capture):
                async def run_with_timeout():
                    try:
                        await asyncio.wait_for(app.run_async(mock_audio_output), timeout=0.5)
                    except (asyncio.TimeoutError, asyncio.CancelledError):
                        pass

                asyncio.run(run_with_timeout())

        config = config_adapter.load()
        output_device = config.devices["output"]
        # Extract index from DeviceIdentity
        output_device_id = output_device.index if hasattr(output_device, 'index') else output_device
        mock_audio_output.play.assert_called_once_with(tts_audio, output_device_id)


def test_receive_loop_delegates_config_update():
    """config_update messages are forwarded to ConfigUpdateHandler."""
    config_update_msg = {"type": "config_update", "label": "Kitchen Node"}

    with tempfile.TemporaryDirectory() as tmpdir:
        config_path = Path(tmpdir) / "config.json"
        from voicenode.adapters.json_config_adapter import JsonConfigAdapter
        config_adapter = JsonConfigAdapter(str(config_path))
        config_adapter.create_default()

        mock_webrtcvad = MagicMock()
        mock_webrtcvad.Vad.return_value = MagicMock()
        mock_structlog = MagicMock()
        mock_structlog.get_logger.return_value = MagicMock()

        server = make_server(recv_messages=[
            {"type": "registered", "status": "new"},
            config_update_msg,
        ])

        mock_handler = MagicMock()
        mock_handler.handle_config_update = AsyncMock()

        with patch.dict("sys.modules", {"webrtcvad": mock_webrtcvad, "structlog": mock_structlog}):
            from voicenode.core import VoiceNodeApplication, ConfigUpdateHandler

            app = VoiceNodeApplication(
                config_adapter=config_adapter,
                transcriber=MagicMock(),
                server=server,
            )

            with patch.object(VoiceNodeApplication, "_run_audio_capture", _noop_audio_capture), \
                 patch("voicenode.core.ConfigUpdateHandler", return_value=mock_handler):
                async def run_with_timeout():
                    try:
                        await asyncio.wait_for(app.run_async(MagicMock()), timeout=0.5)
                    except (asyncio.TimeoutError, asyncio.CancelledError):
                        pass

                asyncio.run(run_with_timeout())

        mock_handler.handle_config_update.assert_called_once_with(config_update_msg)


def test_receive_loop_logs_error_does_not_crash():
    """error messages are logged; receive loop continues running (no exception raised)."""
    error_msg = {"type": "error", "code": "REGISTRATION_REQUIRED", "message": "send register first"}

    with tempfile.TemporaryDirectory() as tmpdir:
        config_path = Path(tmpdir) / "config.json"
        from voicenode.adapters.json_config_adapter import JsonConfigAdapter
        config_adapter = JsonConfigAdapter(str(config_path))
        config_adapter.create_default()

        mock_webrtcvad = MagicMock()
        mock_webrtcvad.Vad.return_value = MagicMock()
        mock_logger = MagicMock()
        mock_structlog = MagicMock()
        mock_structlog.get_logger.return_value = mock_logger

        server = make_server(recv_messages=[
            {"type": "registered", "status": "new"},
            error_msg,
        ])

        with patch.dict("sys.modules", {"webrtcvad": mock_webrtcvad, "structlog": mock_structlog}):
            from voicenode.core import VoiceNodeApplication

            app = VoiceNodeApplication(
                config_adapter=config_adapter,
                transcriber=MagicMock(),
                server=server,
            )

            with patch.object(VoiceNodeApplication, "_run_audio_capture", _noop_audio_capture):
                async def run_with_timeout():
                    try:
                        await asyncio.wait_for(app.run_async(MagicMock()), timeout=0.5)
                    except (asyncio.TimeoutError, asyncio.CancelledError):
                        pass

                asyncio.run(run_with_timeout())

        mock_logger.error.assert_called_once_with(
            "Server error",
            code="REGISTRATION_REQUIRED",
            message="send register first",
        )


def test_reconnect_loop_retries_on_disconnect():
    """On WebSocket disconnect, run_async reconnects using ConnectionManager backoff."""
    import websockets.exceptions

    with tempfile.TemporaryDirectory() as tmpdir:
        config_path = Path(tmpdir) / "config.json"
        from voicenode.adapters.json_config_adapter import JsonConfigAdapter
        config_adapter = JsonConfigAdapter(str(config_path))
        config_adapter.create_default()

        mock_webrtcvad = MagicMock()
        mock_webrtcvad.Vad.return_value = MagicMock()
        mock_structlog = MagicMock()
        mock_structlog.get_logger.return_value = MagicMock()

        connect_call_count = 0

        async def connect_side_effect():
            nonlocal connect_call_count
            connect_call_count += 1

        recv_calls = 0

        async def receive_side_effect():
            nonlocal recv_calls
            recv_calls += 1
            if recv_calls == 1:
                return {"type": "registered", "status": "new"}
            if recv_calls == 2:
                raise websockets.exceptions.ConnectionClosed(None, None)
            # second connection: registered ack then cancel
            if recv_calls == 3:
                return {"type": "registered", "status": "reconnected"}
            raise asyncio.CancelledError()

        server = MagicMock()
        server.is_connected = MagicMock(return_value=True)
        server.connect = AsyncMock(side_effect=connect_side_effect)
        server.send = AsyncMock()
        server.close = AsyncMock()
        server.receive = AsyncMock(side_effect=receive_side_effect)

        with patch.dict("sys.modules", {"webrtcvad": mock_webrtcvad, "structlog": mock_structlog}):
            from voicenode.core import VoiceNodeApplication

            app = VoiceNodeApplication(
                config_adapter=config_adapter,
                transcriber=MagicMock(),
                server=server,
            )

            with patch.object(VoiceNodeApplication, "_run_audio_capture", _noop_audio_capture), \
                 patch("asyncio.sleep", new_callable=AsyncMock):
                async def run_with_timeout():
                    try:
                        await asyncio.wait_for(app.run_async(MagicMock()), timeout=1.0)
                    except (asyncio.TimeoutError, asyncio.CancelledError):
                        pass

                asyncio.run(run_with_timeout())

        # connected twice: initial + reconnect
        assert connect_call_count == 2


def test_pending_utterances_flushed_after_reconnect():
    """Utterances queued during disconnect are sent after reconnect + registration."""
    import websockets.exceptions

    with tempfile.TemporaryDirectory() as tmpdir:
        config_path = Path(tmpdir) / "config.json"
        from voicenode.adapters.json_config_adapter import JsonConfigAdapter
        config_adapter = JsonConfigAdapter(str(config_path))
        config_adapter.create_default()

        mock_webrtcvad = MagicMock()
        mock_webrtcvad.Vad.return_value = MagicMock()
        mock_structlog = MagicMock()
        mock_structlog.get_logger.return_value = MagicMock()

        recv_calls = 0

        async def receive_side_effect():
            nonlocal recv_calls
            recv_calls += 1
            if recv_calls == 1:
                return {"type": "registered", "status": "new"}
            if recv_calls == 2:
                raise websockets.exceptions.ConnectionClosed(None, None)
            if recv_calls == 3:
                return {"type": "registered", "status": "reconnected"}
            raise asyncio.CancelledError()

        server = MagicMock()
        server.is_connected = MagicMock(return_value=True)
        server.connect = AsyncMock()
        server.send = AsyncMock()
        server.close = AsyncMock()
        server.receive = AsyncMock(side_effect=receive_side_effect)

        with patch.dict("sys.modules", {"webrtcvad": mock_webrtcvad, "structlog": mock_structlog}):
            from voicenode.core import VoiceNodeApplication

            app = VoiceNodeApplication(
                config_adapter=config_adapter,
                transcriber=MagicMock(),
                server=server,
            )
            app.pending_utterances = ["hello world", "goodbye"]

            with patch.object(VoiceNodeApplication, "_run_audio_capture", _noop_audio_capture), \
                 patch("asyncio.sleep", new_callable=AsyncMock):
                async def run_with_timeout():
                    try:
                        await asyncio.wait_for(app.run_async(MagicMock()), timeout=1.0)
                    except (asyncio.TimeoutError, asyncio.CancelledError):
                        pass

                asyncio.run(run_with_timeout())

        sent_messages = [c[0][0] for c in server.send.call_args_list]
        utterance_texts = [m["text"] for m in sent_messages if m.get("type") == "utterance"]
        assert "hello world" in utterance_texts
        assert "goodbye" in utterance_texts


def test_cli_main_calls_run_async_with_audio_output():
    """cli.main() wires WebsocketsAdapter + SounddeviceAudioAdapter and calls asyncio.run(app.run_async(audio_output))."""
    import asyncio as real_asyncio

    with tempfile.TemporaryDirectory() as tmpdir:
        config_path = Path(tmpdir) / "config.json"
        from voicenode.adapters.json_config_adapter import JsonConfigAdapter
        config_adapter = JsonConfigAdapter(str(config_path))
        config_adapter.create_default()

        mock_webrtcvad = MagicMock()
        mock_webrtcvad.Vad.return_value = MagicMock()
        mock_structlog = MagicMock()
        mock_structlog.get_logger.return_value = MagicMock()
        mock_sd = MagicMock()
        mock_sd.query_devices.return_value = []
        mock_sd.default.device = (0, 1)

        run_async_called_with = []

        async def fake_run_async(self, audio_output):
            run_async_called_with.append(audio_output)

        mock_pywhispercpp = MagicMock()
        mock_pywhispercpp.Model.return_value = MagicMock()

        with patch.dict("sys.modules", {
            "webrtcvad": mock_webrtcvad,
            "structlog": mock_structlog,
            "sounddevice": mock_sd,
            "pywhispercpp": mock_pywhispercpp,
            "pywhispercpp.model": mock_pywhispercpp,
        }), patch("sys.argv", ["voicenode", "--config", str(config_path)]), \
           patch("voicenode.core.VoiceNodeApplication.run_async", fake_run_async), \
           patch("voicenode.logging_config.setup_logging"):
            from voicenode.cli import main
            from voicenode.ports import AudioOutputPort

            main()

        assert len(run_async_called_with) == 1
        assert isinstance(run_async_called_with[0], AudioOutputPort)


def test_run_offline_mode_still_works():
    """run() (no server) works without asyncio — local VAD/transcription testing preserved."""
    with tempfile.TemporaryDirectory() as tmpdir:
        config_path = Path(tmpdir) / "config.json"
        from voicenode.adapters.json_config_adapter import JsonConfigAdapter
        config_adapter = JsonConfigAdapter(str(config_path))
        config_adapter.create_default()

        mock_webrtcvad = MagicMock()
        mock_webrtcvad.Vad.return_value = MagicMock()
        mock_structlog = MagicMock()
        mock_structlog.get_logger.return_value = MagicMock()

        frames_processed = []

        with patch.dict("sys.modules", {"webrtcvad": mock_webrtcvad, "structlog": mock_structlog}):
            from voicenode.core import VoiceNodeApplication
            from voicenode.ports import AudioFrame

            app = VoiceNodeApplication(
                config_adapter=config_adapter,
                transcriber=MagicMock(),
                server=None,
            )

            original_process = app.process_frame

            def capturing_process(frame):
                frames_processed.append(frame)
                if len(frames_processed) >= 3:
                    app.running = False
                return original_process(frame)

            app.process_frame = capturing_process

            def fake_capture(self_adapter, device_id, duration_ms=100):
                for i in range(3):
                    yield AudioFrame(data=b"audio", timestamp_ms=i * 100)

            with patch("voicenode.adapters.SounddeviceAudioAdapter.capture_frames", fake_capture):
                app.run()

        assert len(frames_processed) == 3
        assert app.server is None
