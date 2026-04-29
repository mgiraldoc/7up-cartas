from __future__ import annotations

import argparse
import asyncio
import json
import random
import string
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

import websockets

from src.core.game_logic import BOT_NAME_POOL, CardGameState, GamePhase


def generate_room_code(existing: set[str]) -> str:
    alphabet = string.ascii_uppercase + string.digits
    while True:
        code = "".join(random.choice(alphabet) for _ in range(4))
        if code not in existing:
            return code


@dataclass
class Room:
    code: str
    host_name: str
    bot_count: int
    humans_needed: int = 2
    connections: Dict[str, websockets.ServerConnection] = field(default_factory=dict)
    state: Optional[CardGameState] = None
    trick_task: Optional[asyncio.Task[None]] = None

    def human_names(self) -> list[str]:
        return list(self.connections.keys())

    async def add_player(self, player_name: str, websocket: websockets.ServerConnection) -> None:
        self.connections[player_name] = websocket
        if self.state is None and len(self.connections) >= self.humans_needed:
            await self.start_game()
        else:
            await self.broadcast_lobby()

    async def remove_player(self, player_name: str) -> None:
        self.connections.pop(player_name, None)
        if self.trick_task and not self.trick_task.done():
            self.trick_task.cancel()
            self.trick_task = None

    async def start_game(self) -> None:
        human_names = self.human_names()
        available_bots = [name for name in BOT_NAME_POOL if name not in human_names]
        bot_count = max(0, min(self.bot_count, max(0, 7 - len(human_names)), len(available_bots)))
        bot_names = available_bots[:bot_count]
        self.state = CardGameState(human_names, bot_names)
        self.state.advance_automatic()
        await self.broadcast_state()
        await self.schedule_trick_resolution_if_needed()

    async def broadcast_json(self, payload: Dict[str, Any]) -> None:
        if not self.connections:
            return
        message = json.dumps(payload)
        stale: list[str] = []
        for player_name, websocket in self.connections.items():
            try:
                await websocket.send(message)
            except Exception:
                stale.append(player_name)
        for player_name in stale:
            await self.remove_player(player_name)

    async def broadcast_lobby(self) -> None:
        await self.broadcast_json(
            {
                "type": "lobby",
                "room_code": self.code,
                "players": self.human_names(),
                "humans_needed": self.humans_needed,
                "bot_count": self.bot_count,
                "status": "waiting",
            }
        )

    async def broadcast_state(self) -> None:
        if self.state is None:
            return
        for player_name, websocket in list(self.connections.items()):
            try:
                await websocket.send(
                    json.dumps(
                        {
                            "type": "state",
                            "room_code": self.code,
                            "state": self.state.to_snapshot(viewer_name=player_name),
                        }
                    )
                )
            except Exception:
                await self.remove_player(player_name)

    async def handle_action(self, player_name: str, payload: Dict[str, Any]) -> None:
        if self.state is None:
            return
        message_type = payload.get("type")
        changed = False
        if message_type == "set_prediction":
            changed = self.state.set_player_prediction(player_name, int(payload.get("value", 0)))
        elif message_type == "play_card":
            card = str(payload.get("card", "")).strip()
            changed = self.state.play_player_card(player_name, card)
        elif message_type == "continue_round":
            if self.state.current_phase == GamePhase.ROUND_END:
                self.state.proceed_after_round()
                changed = True

        if not changed:
            return

        self.state.advance_automatic()
        await self.broadcast_state()
        await self.schedule_trick_resolution_if_needed()

    async def schedule_trick_resolution_if_needed(self) -> None:
        if self.state is None or self.state.current_phase != GamePhase.TRICK_RESOLUTION:
            return
        if self.trick_task and not self.trick_task.done():
            return
        self.trick_task = asyncio.create_task(self._resolve_trick_after_delay())

    async def _resolve_trick_after_delay(self) -> None:
        try:
            await asyncio.sleep(1.0)
            if self.state is None or self.state.current_phase != GamePhase.TRICK_RESOLUTION:
                return
            self.state.advance_after_trick()
            self.state.advance_automatic()
            await self.broadcast_state()
            await self.schedule_trick_resolution_if_needed()
        finally:
            self.trick_task = None


class MultiplayerServer:
    def __init__(self) -> None:
        self.rooms: Dict[str, Room] = {}
        self.socket_rooms: Dict[int, tuple[str, str]] = {}

    async def handler(self, websocket: websockets.ServerConnection) -> None:
        try:
            async for raw_message in websocket:
                payload = json.loads(raw_message)
                if not isinstance(payload, dict):
                    continue
                socket_id = id(websocket)
                existing = self.socket_rooms.get(socket_id)
                if existing is None:
                    await self._handle_join(websocket, payload)
                else:
                    room_code, player_name = existing
                    room = self.rooms.get(room_code)
                    if room is None:
                        await websocket.send(json.dumps({"type": "error", "message": "La sala ya no existe."}))
                        continue
                    await room.handle_action(player_name, payload)
        finally:
            await self._cleanup_socket(websocket)

    async def _handle_join(self, websocket: websockets.ServerConnection, payload: Dict[str, Any]) -> None:
        message_type = payload.get("type")
        player_name = str(payload.get("player_name", "")).strip()[:24] or "Jugador"

        if message_type == "create_room":
            bot_count = int(payload.get("bot_count", 0))
            room_code = generate_room_code(set(self.rooms.keys()))
            room = Room(code=room_code, host_name=player_name, bot_count=bot_count)
            self.rooms[room_code] = room
            self.socket_rooms[id(websocket)] = (room_code, player_name)
            await room.add_player(player_name, websocket)
            return

        if message_type == "join_room":
            room_code = str(payload.get("room_code", "")).upper().strip()
            room = self.rooms.get(room_code)
            if room is None:
                await websocket.send(json.dumps({"type": "error", "message": "No existe una sala con ese código."}))
                return
            if len(room.connections) >= room.humans_needed and player_name not in room.connections:
                await websocket.send(json.dumps({"type": "error", "message": "La sala ya está llena."}))
                return
            if player_name in room.connections:
                await websocket.send(json.dumps({"type": "error", "message": "Ese nombre ya está en uso en la sala."}))
                return
            self.socket_rooms[id(websocket)] = (room_code, player_name)
            await room.add_player(player_name, websocket)
            return

        await websocket.send(json.dumps({"type": "error", "message": "Mensaje inicial inválido."}))

    async def _cleanup_socket(self, websocket: websockets.ServerConnection) -> None:
        socket_id = id(websocket)
        info = self.socket_rooms.pop(socket_id, None)
        if info is None:
            return
        room_code, player_name = info
        room = self.rooms.get(room_code)
        if room is None:
            return
        await room.remove_player(player_name)
        if not room.connections:
            self.rooms.pop(room_code, None)
        elif room.state is not None:
            await room.broadcast_json(
                {
                    "type": "error",
                    "message": f"{player_name} se desconectó. La sala se cerrará.",
                }
            )
            for other_name in list(room.connections.keys()):
                await room.remove_player(other_name)
            self.rooms.pop(room_code, None)
        else:
            await room.broadcast_lobby()


async def serve(host: str, port: int) -> None:
    server = MultiplayerServer()
    async with websockets.serve(server.handler, host, port):
        print(f"Servidor 7UP online escuchando en ws://{host}:{port}")
        await asyncio.Future()


def main() -> None:
    parser = argparse.ArgumentParser(description="Servidor multiplayer para 7UP - Cartas.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    asyncio.run(serve(args.host, args.port))


if __name__ == "__main__":
    main()
