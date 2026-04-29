from __future__ import annotations

import asyncio
import json
import queue
import threading
from typing import Any, Dict, List, Optional

import websockets


class OnlineClient:
    def __init__(
        self,
        server_url: str,
        player_name: str,
        mode: str,
        *,
        room_code: str = "",
        bot_count: int = 0,
    ) -> None:
        self.server_url = server_url
        self.player_name = player_name
        self.mode = mode
        self.room_code = room_code.upper().strip()
        self.bot_count = bot_count
        self.connected = False
        self.closed = False
        self.error: Optional[str] = None
        self._incoming: "queue.Queue[Dict[str, Any]]" = queue.Queue()
        self._outgoing: "queue.Queue[Optional[Dict[str, Any]]]" = queue.Queue()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def start(self) -> None:
        self._thread.start()

    def send(self, payload: Dict[str, Any]) -> None:
        if self.closed:
            return
        self._outgoing.put(payload)

    def poll_events(self) -> List[Dict[str, Any]]:
        events: List[Dict[str, Any]] = []
        while True:
            try:
                events.append(self._incoming.get_nowait())
            except queue.Empty:
                break
        return events

    def close(self) -> None:
        if self.closed:
            return
        self.closed = True
        self._outgoing.put(None)

    def _run(self) -> None:
        asyncio.run(self._runner())

    async def _runner(self) -> None:
        try:
            async with websockets.connect(self.server_url) as websocket:
                self.connected = True
                initial_payload: Dict[str, Any]
                if self.mode == "online_host":
                    initial_payload = {
                        "type": "create_room",
                        "player_name": self.player_name,
                        "bot_count": self.bot_count,
                    }
                else:
                    initial_payload = {
                        "type": "join_room",
                        "player_name": self.player_name,
                        "room_code": self.room_code,
                    }
                await websocket.send(json.dumps(initial_payload))

                sender = asyncio.create_task(self._sender(websocket))
                receiver = asyncio.create_task(self._receiver(websocket))
                done, pending = await asyncio.wait(
                    {sender, receiver},
                    return_when=asyncio.FIRST_EXCEPTION,
                )
                for task in pending:
                    task.cancel()
                for task in done:
                    exc = task.exception()
                    if exc is not None:
                        raise exc
        except Exception as exc:  # pragma: no cover - network path
            self.error = str(exc)
            self._incoming.put({"type": "error", "message": self.error})
        finally:
            self.connected = False
            self.closed = True

    async def _sender(self, websocket: websockets.ClientConnection) -> None:
        while True:
            payload = await asyncio.to_thread(self._outgoing.get)
            if payload is None:
                await websocket.close()
                return
            await websocket.send(json.dumps(payload))

    async def _receiver(self, websocket: websockets.ClientConnection) -> None:
        async for message in websocket:
            payload = json.loads(message)
            if isinstance(payload, dict):
                self._incoming.put(payload)
