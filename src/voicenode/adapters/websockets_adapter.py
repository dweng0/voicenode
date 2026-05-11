import json
from voicenode.ports import ServerPort
from voicenode.core import NodeConfig


class WebsocketsAdapter(ServerPort):
    def __init__(self, url: str):
        self.url = url
        self.ws = None

    async def connect(self) -> None:
        from websockets.client import connect
        
        self.ws = await connect(self.url, max_size=None)

    async def send(self, message: dict) -> None:
        if self.ws is None:
            raise RuntimeError("Not connected")
        
        await self.ws.send(json.dumps(message))

    async def receive(self):
        if self.ws is None:
            raise RuntimeError("Not connected")

        data = await self.ws.recv()
        if isinstance(data, bytes):
            return data
        return json.loads(data)

    async def receive_binary(self) -> bytes:
        if self.ws is None:
            raise RuntimeError("Not connected")
        
        data = await self.ws.recv()
        if isinstance(data, bytes):
            return data
        raise RuntimeError("Expected binary frame")

    async def close(self) -> None:
        if self.ws is not None:
            await self.ws.close()
            self.ws = None

    def is_connected(self) -> bool:
        return self.ws is not None

    async def register(self, config: NodeConfig) -> None:
        message = {
            "type": "register",
            "id": config.id,
            "label": config.label,
            "location": config.location,
            "capabilities": config.capabilities,
        }
        await self.send(message)

    async def send_utterance(self, text: str) -> None:
        await self.send({"type": "utterance", "text": text})