"""Test routing of TTS binary chunks based on tts_stream_start isAecReference flag.

Server (housekeeper) fires two separate streams per response:
  1. AEC reference stream — tts_stream_start has isAecReference=true
  2. Playback stream — tts_stream_start without flag
Binary chunks between start/end belong to the current stream's mode.
"""
import asyncio
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _make_app(mock_server):
    import sys
    for mod in ("structlog", "webrtcvad"):
        if mod not in sys.modules:
            sys.modules[mod] = MagicMock()
    from voicenode.core import VoiceNodeApplication
    from voicenode.adapters.json_config_adapter import JsonConfigAdapter

    tmpdir = tempfile.mkdtemp()
    config_path = Path(tmpdir) / "config.json"
    config_adapter = JsonConfigAdapter(str(config_path))
    config_adapter.create_default()

    app = VoiceNodeApplication(
        config_adapter=config_adapter,
        transcriber=MagicMock(),
        server=mock_server,
    )
    return app


async def _drive_receive_loop(app, audio_output, messages):
    """Drive _receive_loop through a finite message list, then stop."""
    iterator = iter(messages)

    async def fake_receive():
        try:
            return next(iterator)
        except StopIteration:
            app.running = False
            await asyncio.sleep(0)
            raise asyncio.CancelledError()

    app.server.receive = fake_receive
    app.running = True
    try:
        await app._receive_loop(audio_output)
    except asyncio.CancelledError:
        pass


@pytest.mark.asyncio
async def test_aec_ref_stream_routes_binary_to_aec_engine():
    """Binary chunks during AEC-ref stream go to aec_engine.add_reference_chunk, not play."""
    mock_server = AsyncMock()
    mock_server.is_connected = MagicMock(return_value=True)
    app = _make_app(mock_server)
    app.aec_engine = MagicMock()

    audio_output = MagicMock()
    audio_output.list_devices.return_value = []

    messages = [
        {"type": "tts_stream_start", "streamToken": "t1", "isAecReference": True},
        b"REF_CHUNK_1",
        b"REF_CHUNK_2",
        {"type": "tts_stream_end", "streamToken": "t1"},
    ]
    await _drive_receive_loop(app, audio_output, messages)

    assert app.aec_engine.add_reference_chunk.call_count == 2
    audio_output.play.assert_not_called()


@pytest.mark.asyncio
async def test_playback_stream_routes_binary_to_audio_output():
    """Binary chunks during playback stream go to audio_output.play, not AEC."""
    mock_server = AsyncMock()
    mock_server.is_connected = MagicMock(return_value=True)
    app = _make_app(mock_server)
    app.aec_engine = MagicMock()

    audio_output = MagicMock()
    audio_output.list_devices.return_value = []

    messages = [
        {"type": "tts_stream_start", "streamToken": "t2"},  # no isAecReference
        b"PLAY_CHUNK_1",
        b"PLAY_CHUNK_2",
        {"type": "tts_stream_end", "streamToken": "t2"},
    ]
    await _drive_receive_loop(app, audio_output, messages)

    assert audio_output.play.call_count == 2
    app.aec_engine.add_reference_chunk.assert_not_called()


@pytest.mark.asyncio
async def test_aec_ref_stream_does_not_trigger_listening_gate():
    """AEC-ref tts_stream_start must NOT activate stop_word_detector gate."""
    mock_server = AsyncMock()
    mock_server.is_connected = MagicMock(return_value=True)
    app = _make_app(mock_server)
    app.stop_word_detector = MagicMock()
    app.stop_word_detector.is_listening = False

    audio_output = MagicMock()
    audio_output.list_devices.return_value = []

    messages = [
        {"type": "tts_stream_start", "streamToken": "t3", "isAecReference": True},
        {"type": "tts_stream_end", "streamToken": "t3"},
    ]
    await _drive_receive_loop(app, audio_output, messages)

    app.stop_word_detector.on_tts_stream_start.assert_not_called()


@pytest.mark.asyncio
async def test_playback_stream_triggers_listening_gate():
    """Playback tts_stream_start activates stop_word_detector gate."""
    mock_server = AsyncMock()
    mock_server.is_connected = MagicMock(return_value=True)
    app = _make_app(mock_server)
    app.stop_word_detector = MagicMock()
    app.stop_word_detector.is_listening = False

    audio_output = MagicMock()
    audio_output.list_devices.return_value = []

    messages = [
        {"type": "tts_stream_start", "streamToken": "t4"},
        {"type": "tts_stream_end", "streamToken": "t4"},
    ]
    await _drive_receive_loop(app, audio_output, messages)

    app.stop_word_detector.on_tts_stream_start.assert_called_once()


@pytest.mark.asyncio
async def test_stream_end_clears_mode_next_start_defaults_to_playback():
    """After tts_stream_end the AEC mode is cleared; next start without flag = playback."""
    mock_server = AsyncMock()
    mock_server.is_connected = MagicMock(return_value=True)
    app = _make_app(mock_server)
    app.aec_engine = MagicMock()

    audio_output = MagicMock()
    audio_output.list_devices.return_value = []

    messages = [
        {"type": "tts_stream_start", "streamToken": "t5a", "isAecReference": True},
        b"REF",
        {"type": "tts_stream_end", "streamToken": "t5a"},
        {"type": "tts_stream_start", "streamToken": "t5b"},  # no flag = playback
        b"PLAY",
        {"type": "tts_stream_end", "streamToken": "t5b"},
    ]
    await _drive_receive_loop(app, audio_output, messages)

    assert app.aec_engine.add_reference_chunk.call_count == 1
    assert audio_output.play.call_count == 1
    app.aec_engine.on_stream_end.assert_called()


@pytest.mark.asyncio
async def test_use_for_aec_tees_chunk_to_both_aec_and_playback():
    """tts_stream_start useForAec=true: binary chunks go to BOTH AEC and audio_output."""
    mock_server = AsyncMock()
    mock_server.is_connected = MagicMock(return_value=True)
    app = _make_app(mock_server)
    app.aec_engine = MagicMock()

    audio_output = MagicMock()
    audio_output.list_devices.return_value = []

    messages = [
        {"type": "tts_stream_start", "streamToken": "t7", "useForAec": True, "sampleRate": 24000},
        b"AUDIO",
        {"type": "tts_stream_end", "streamToken": "t7"},
    ]
    await _drive_receive_loop(app, audio_output, messages)

    app.aec_engine.add_reference_chunk.assert_called_once_with(b"AUDIO", source_rate=24000)
    audio_output.play.assert_called_once()
    # play called with sample_rate=24000
    call_kwargs = audio_output.play.call_args.kwargs
    assert call_kwargs.get("sample_rate") == 24000


@pytest.mark.asyncio
async def test_use_for_aec_false_does_not_feed_aec():
    """tts_stream_start without useForAec: binary chunks only play, AEC not touched."""
    mock_server = AsyncMock()
    mock_server.is_connected = MagicMock(return_value=True)
    app = _make_app(mock_server)
    app.aec_engine = MagicMock()

    audio_output = MagicMock()
    audio_output.list_devices.return_value = []

    messages = [
        {"type": "tts_stream_start", "streamToken": "t8", "sampleRate": 24000},
        b"AUDIO",
        {"type": "tts_stream_end", "streamToken": "t8"},
    ]
    await _drive_receive_loop(app, audio_output, messages)

    app.aec_engine.add_reference_chunk.assert_not_called()
    audio_output.play.assert_called_once()


@pytest.mark.asyncio
async def test_sample_rate_defaults_to_24000_when_unspecified():
    """Missing sampleRate in tts_stream_start defaults to 24000."""
    mock_server = AsyncMock()
    mock_server.is_connected = MagicMock(return_value=True)
    app = _make_app(mock_server)

    audio_output = MagicMock()
    audio_output.list_devices.return_value = []

    messages = [
        {"type": "tts_stream_start", "streamToken": "t9"},
        b"AUDIO",
        {"type": "tts_stream_end", "streamToken": "t9"},
    ]
    await _drive_receive_loop(app, audio_output, messages)

    call_kwargs = audio_output.play.call_args.kwargs
    assert call_kwargs.get("sample_rate") == 24000


@pytest.mark.asyncio
async def test_aec_ref_stream_end_clears_aec_buffer_not_stop_word_detector():
    """tts_stream_end of AEC-ref stream calls aec_engine.on_stream_end, not detector.on_tts_stream_end."""
    mock_server = AsyncMock()
    mock_server.is_connected = MagicMock(return_value=True)
    app = _make_app(mock_server)
    app.aec_engine = MagicMock()
    app.stop_word_detector = MagicMock()
    app.stop_word_detector.is_listening = False

    audio_output = MagicMock()
    audio_output.list_devices.return_value = []

    messages = [
        {"type": "tts_stream_start", "streamToken": "t6", "isAecReference": True},
        {"type": "tts_stream_end", "streamToken": "t6"},
    ]
    await _drive_receive_loop(app, audio_output, messages)

    app.aec_engine.on_stream_end.assert_called_once()
    app.stop_word_detector.on_tts_stream_end.assert_not_called()
