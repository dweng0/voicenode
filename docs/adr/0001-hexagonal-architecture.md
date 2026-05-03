# ADR-0001: Hexagonal Architecture with Ports and Adapters

## Status

Accepted

## Context

Voice Node needs to run on multiple platforms:
- Raspberry Pi Zero 2W (production edge devices)
- Developer machines (local testing)

It integrates multiple external systems:
- Audio hardware (USB/Bluetooth mics and speakers)
- Speech recognition (Whisper)
- Network communication (WebSocket to housekeeper)
- Platform-specific configuration storage

We need an architecture that:
- Isolates domain logic from infrastructure concerns
- Allows swapping implementations (e.g., different audio backends, mock services for testing)
- Makes the core flow easy to understand and test
- Avoids over-engineering for a small codebase

## Decision

Use hexagonal architecture (ports and adapters) with:

**Ports (interfaces)** define what the core needs:
- `AudioInputPort` — capture audio frames
- `AudioOutputPort` — play TTS audio
- `VADPort` — detect speech boundaries
- `TranscriberPort` — speech-to-text conversion
- `ServerPort` — WebSocket connection and messaging
- `ConfigPort` — load and persist configuration

**Adapters** implement ports for specific technologies:
- `SounddeviceAudioAdapter` — real audio hardware via sounddevice
- `WebRTCVADAdapter` — VAD via webrtcvad
- `FasterWhisperAdapter` — transcription via faster-whisper
- `WebsocketsAdapter` — WebSocket client via websockets library
- `JsonConfigAdapter` — file-based JSON configuration

**Domain core** contains:
- Domain types: `NodeIdentity`, `Utterance`, `AudioFrame`, `Connection`
- Domain events: `SpeechBoundaryDetected`, `UtteranceReady`, `TTSReceived`
- Domain errors: `AudioCaptureError`, `ConnectionError`, `TranscriptionError`
- Application service: `VoiceNodeApplication` orchestrates the flow

## Consequences

**Benefits:**
- Core logic is testable in isolation with mock adapters
- Easy to swap implementations (e.g., different Whisper backends, test doubles)
- Clear separation between "what" (ports) and "how" (adapters)
- Domain types document the problem space

**Trade-offs:**
- More files and interfaces than a simple script
- Slight overhead for a single-developer project
- Requires discipline to keep adapters thin

**Mitigations:**
- Keep ports minimal — only what the core actually needs
- Adapters should be thin wrappers around external libraries
- Don't over-abstract; create ports only when we have >1 implementation or testing need