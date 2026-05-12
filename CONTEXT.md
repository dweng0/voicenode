# Voice Node — Context

A Python client for distributed voice control. Runs on Raspberry Pi (or dev machine), captures audio, transcribes locally with Whisper, and sends text utterances to housekeeper via WebSocket.

## Glossary

### Voice Node
The device-side software (this project). Captures audio, detects speech boundaries via VAD, transcribes with Whisper, and communicates with housekeeper. Not to be confused with VoiceNodeHub (server-side component in housekeeper).

### VoiceNodeHub
Server-side WebSocket hub in housekeeper. Manages connections from multiple Voice Nodes. See `../housekeeper/docs/voice-node-protocol.md`.

### Utterance
A transcribed speech segment. Sent to housekeeper as JSON text, not raw audio. STT runs locally on the Voice Node.

### Speech Boundary
The moment VAD detects end of speech (silence duration threshold met). Triggers Whisper transcription.

### NodeIdentity
The Voice Node's identity: `id` (auto-generated UUID), `label` (user-facing name), `location` (room description for LLM context), `capabilities` (mic/speaker).

### DeviceIdentity
Stable identifier for audio input/output devices: `name` (device name), `index` (numeric index), `serial` (USB serial if available). Matching priority: serial > name > index. Survives device reconnection via name/serial rather than numeric index.

### TTS Audio
Binary PCM audio (22050 Hz, 16-bit signed LE, mono) sent from housekeeper to Voice Node for playback. Received as raw WebSocket binary frame.

### VAD (Voice Activity Detection)
webrtcvad-based detection of speech start/end. Determines when to transcribe. Uses aggressiveness mode and silence duration threshold.

### Stream Lifecycle
Messages sent by housekeeper when TTS streaming begins and ends: `tts_stream_start` (with streamToken) signals Pi to gate stop-word detection (suppress ambient listening, only match stop-words). `tts_stream_end` (with streamToken) signals Pi to restore normal listening. Defense-in-depth with server-side mode switching (see ADR 0011 in housekeeper). Full spec: `../housekeeper/docs/voice-node-protocol.md` (Server → Node messages).

## Architecture

Hexagonal architecture with domain core and adapters:

**Ports (Interfaces):**
- `AudioInputPort` — capture audio frames
- `AudioOutputPort` — play TTS audio
- `VADPort` — detect speech boundaries
- `TranscriberPort` — speech-to-text
- `ServerPort` — WebSocket connection, messaging
- `ConfigPort` — load/save config values

**Adapters:**
- `SounddeviceAudioAdapter` — implements AudioInputPort + AudioOutputPort
- `WebRTCVADAdapter` — implements VADPort
- `FasterWhisperAdapter` — implements TranscriberPort
- `WebsocketsAdapter` — implements ServerPort
- `JsonConfigAdapter` — implements ConfigPort

**Domain Core:**
- `NodeIdentity`, `Utterance`, `AudioFrame`, `Connection`
- Events: `SpeechBoundaryDetected`, `UtteranceReady`, `TTSReceived`, `ConnectionLost`
- `VoiceNodeApplication` — orchestrates ports, drives flow

**Stop-word Detection Gate:**
During TTS playback (when `tts_stream_start` arrives), Pi must suppress ambient listening and only match stop-words (see CONTEXT glossary for "Stream Lifecycle"). This gates stop-word detection at the Pi level. The server also gates listening window mode server-side (ADR 0011) — defense-in-depth ensures no ambient utterances leak through if either layer fails.

## Stream Lifecycle Implementation (Pi-side)

### State Machine

`StopWordDetector` implements a two-state gate for stop-word detection:

```
listening=False (normal) ←→ listening=True (stream gate)
    ↑                              ↓
    └─ ambient utterances checked  └─ only stop-words trigger signal
       for stop-word matches           (suppress ambient listening)
```

### Message Flow

1. **Server sends tts_stream_start** (with streamToken)
   - Pi calls `detector.on_tts_stream_start(stream_token)`
   - Transition: `listening=False → listening=True`
   - Effect: Gate activated — suppress ambient utterances, only send stop-word signals
   - Starts 30s timeout as fallback

2. **Pi detects utterance during stream** (from transcriber)
   - Checks detector state via `is_listening`
   - If `is_listening=True` (stream gate active):
     - Suppress utterance (don't send to server)
     - Check if text matches stop-word
     - If match: send `stop_word` signal; if not: silent discard
   - If `is_listening=False`: send utterance normally
   - Prevents ambient speech from interrupting TTS playback

3. **Server sends tts_stream_end** (with matching streamToken)
   - Pi calls `detector.on_tts_stream_end(stream_token)`
   - Validates token matches original stream start (warns if mismatch)
   - Transition: `listening=True → listening=False`
   - Cancels timeout (stream ended normally)
   - Effect: Normal listening resumes (all utterances sent to server)

### Edge Cases

All edge cases are handled gracefully (idempotent, no crashes):

- **Out-of-order** (stream_end before stream_start): ignored, state remains correct
- **Double-start** (stream_start twice without end): second call is no-op, no double-gating
- **Double-end** (stream_end twice): second call is no-op, warns but doesn't crash
- **Token mismatch** (end token ≠ start token): warns but still transitions correctly
- **Timeout** (no stream_end within 30s): auto-restore `listening=False` (fallback for network issues)
- **Disconnect during stream** (connection lost mid-stream): `on_disconnect()` implicit end, state cleaned for reconnect

### Integration Points

- `VoiceNodeApplication._receive_loop()` → parses `tts_stream_start`/`tts_stream_end` messages, calls detector methods
- `VoiceNodeApplication._send_and_check_stop_word()` → calls `detector.check_utterance()` after sending utterance
- `detector.check_utterance()` → uses `StopWordMatcher` to check text, sends `stop_word` signal to server if match + listening

See `src/voicenode/core/stop_word_detector.py` for implementation and docstrings.

Full protocol spec: `../housekeeper/docs/voice-node-protocol.md` (Server → Node messages, tts_stream_* format).

## Protocol Summary

**Node → Server:**
- `register` — identity, capabilities, available devices, active devices
- `utterance` — transcribed text
- `config_updated` — acknowledgment of remote config change

**Server → Node:**
- `registered` — confirmation with status (new/reconnected)
- `config_update` — remote change to label, location, active devices
- `tts_stream_start` — TTS stream beginning (with streamToken); Pi gates stop-word detection
- `tts_stream_end` — TTS stream ending (with streamToken); Pi restores normal listening
- `tts` — binary PCM audio
- `error` — rejection with code and message

Full protocol: `../housekeeper/docs/voice-node-protocol.md`

## Device Discovery Flow

1. Node starts, enumerates audio devices via sounddevice
2. Auto-selects default input/output devices
3. Sends `register` with device list and active selections
4. Works immediately
5. Dashboard can send `config_update` to change active devices
6. CLI `--input`/`--output` as local fallback

## Config Structure

`config.json`:
```json
{
  "id": "auto-generated-uuid",
  "label": "Voice Node",
  "location": "unknown",
  "server_url": "ws://localhost:3001",
  "whisper_model": "base.en",
  "devices": {
    "input": 0,
    "output": 1
  },
  "vad": {
    "aggressiveness": 3,
    "silence_duration_ms": 800,
    "max_utterance_length_ms": 30000
  },
  "capabilities": ["mic", "speaker"]
}
```

## CLI Surface

```
voicenode                          # Start the node
voicenode --list-devices           # List audio devices
voicenode --input <id>             # Set input, save config, start
voicenode --output <id>            # Set output, save config, start
voicenode --config <path>          # Custom config path
voicenode --help                   # Show help
voicenode --version                # Show version
voicenode log                      # Tail log file
voicenode monitor <device-id>      # Live audio/VAD/transcription monitor
```

## Key Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| STT engine | faster-whisper | 4x faster on CPU, better for Pi |
| VAD | webrtcvad | Frame-accurate speech boundary detection |
| Audio capture | sounddevice | Cross-platform, works with USB/Bluetooth |
| WebSocket lib | websockets (async) | Integrates with async audio pipeline |
| Config format | JSON file | Simple, human-editable |
| Node ID | Auto-generated UUID | Stable across reconnects, user provides label |
| Logging | structlog | Structured JSON for Pi, console for dev |
| Audio format | 16kHz mono capture | Native format for VAD and Whisper, no resampling |
| Wake word detection | Server-side | Node sends raw transcripts, housekeeper detects "housekeeper" |

## Dependencies

- `sounddevice` — audio capture/playback
- `webrtcvad` — voice activity detection
- `faster-whisper` — speech-to-text
- `websockets` — WebSocket client
- `structlog` — structured logging
- `uv` — package manager