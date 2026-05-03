# Voice Node

Python client for distributed voice control. Runs on Raspberry Pi (or dev machine), captures audio, transcribes locally with Whisper, and sends text utterances to housekeeper via WebSocket.

## Setup

```bash
uv sync
```

## Usage

```bash
voicenode --list-devices
voicenode
```