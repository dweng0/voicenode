import httpx
from voicenode.ports import AudioFrame, TranscriberPort


class TranscriberError(Exception):
    pass


class HttpTranscriberAdapter(TranscriberPort):
    def __init__(self, server_http_url: str, node_id: str, timeout: float = 30.0):
        self.server_http_url = server_http_url
        self.node_id = node_id
        self.timeout = timeout

    def transcribe(self, frames: list[AudioFrame]) -> str:
        audio_data = b"".join(frame.data for frame in frames)
        
        url = f"{self.server_http_url}/api/voice/transcribe"
        headers = {
            "Content-Type": "application/octet-stream",
            "X-Node-Id": self.node_id,
        }
        
        try:
            response = httpx.post(url, content=audio_data, headers=headers, timeout=self.timeout)
            
            if response.status_code >= 400:
                raise TranscriberError(f"Transcription failed: HTTP {response.status_code}")
            
            data = response.json()
            return data.get("transcript", "")
        except httpx.ConnectError as e:
            raise TranscriberError(f"Failed to connect to transcription server: {e}")
        except httpx.TimeoutException as e:
            raise TranscriberError(f"Transcription request timed out: {e}")
        except Exception as e:
            raise TranscriberError(f"Transcription error: {e}")