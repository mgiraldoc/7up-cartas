from __future__ import annotations

import argparse
import asyncio
import json
import random
import string
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

import websockets

from src.core.game_logic import (
    AI_PLAY_DELAY,
    BOT_NAME_POOL,
    PREDICTION_REVEAL_DELAY,
    TRICK_RESOLVE_DELAY,
    TRICK_WINNER_REVEAL_DELAY,
    CardGameState,
    GamePhase,
)


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
    minimum_humans: int = 2
    connections: Dict[str, websockets.ServerConnection] = field(default_factory=dict)
    state: Optional[CardGameState] = None
    trick_task: Optional[asyncio.Task[None]] = None
    bot_task: Optional[asyncio.Task[None]] = None
    prediction_task: Optional[asyncio.Task[None]] = None
    round_task: Optional[asyncio.Task[None]] = None
    round_deadline: Optional[float] = None
    round_ready_names: set[str] = field(default_factory=set)
    chat_history: list[Dict[str, str]] = field(default_factory=list)
    chat_last_sent: Dict[str, float] = field(default_factory=dict)

    def human_names(self) -> list[str]:
        return list(self.connections.keys())

    async def add_player(self, player_name: str, websocket: websockets.ServerConnection) -> None:
        self.connections[player_name] = websocket
        self.bot_count = min(self.bot_count, max(0, 7 - len(self.connections)))
        await self.broadcast_lobby()

    async def remove_player(self, player_name: str) -> None:
        self.connections.pop(player_name, None)
        if self.state is None and self.host_name == player_name and self.connections:
            self.host_name = next(iter(self.connections))
        if self.trick_task and not self.trick_task.done():
            self.trick_task.cancel()
            self.trick_task = None
        if self.bot_task and not self.bot_task.done():
            self.bot_task.cancel()
            self.bot_task = None
        if self.prediction_task and not self.prediction_task.done():
            self.prediction_task.cancel()
            self.prediction_task = None

    async def start_game(self) -> None:
        human_names = self.human_names()
        human_names_lower = {name.lower() for name in human_names}
        available_bots = [name for name in BOT_NAME_POOL if name.lower() not in human_names_lower]
        bot_count = max(0, min(self.bot_count, max(0, 7 - len(human_names)), len(available_bots)))
        bot_names = random.sample(available_bots, k=bot_count)
        self.state = CardGameState(human_names, bot_names, defer_ai_predictions=True)
        await self.broadcast_state()
        await self.schedule_ai_prediction_if_needed()
        await self.schedule_bot_turn_if_needed()
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
                "host_name": self.host_name,
                "minimum_humans": self.minimum_humans,
                "max_humans": 7,
                "bot_count": self.bot_count,
                "status": "waiting",
            }
        )

    async def broadcast_state(self, *, prediction_reveal: Optional[Dict[str, Any]] = None) -> None:
        if self.state is None:
            return
        loop = asyncio.get_running_loop()
        seconds_remaining = (
            max(0, int(self.round_deadline - loop.time() + 0.999))
            if self.round_deadline is not None and self.state.current_phase == GamePhase.ROUND_END
            else None
        )
        for player_name, websocket in list(self.connections.items()):
            try:
                await websocket.send(
                    json.dumps(
                        {
                            "type": "state",
                            "room_code": self.code,
                            "state": self.state.to_snapshot(viewer_name=player_name),
                            "round_seconds_remaining": seconds_remaining,
                            "round_ready_names": sorted(self.round_ready_names),
                            "round_human_names": self.human_names(),
                            "ai_prediction_reveal": prediction_reveal,
                        }
                    )
                )
            except Exception:
                await self.remove_player(player_name)

    async def handle_action(self, player_name: str, payload: Dict[str, Any]) -> None:
        if payload.get("type") == "start_game":
            if player_name == self.host_name and self.state is None and len(self.connections) >= self.minimum_humans:
                await self.start_game()
            return
        if payload.get("type") == "set_bot_count":
            if player_name == self.host_name and self.state is None:
                requested = int(payload.get("bot_count", 0))
                self.bot_count = max(0, min(7 - len(self.connections), requested))
                await self.broadcast_lobby()
            return
        if self.state is None:
            return
        message_type = payload.get("type")
        if message_type == "chat":
            if player_name not in self.connections:
                return
            raw_message = str(payload.get("message", ""))
            message = " ".join("".join(char for char in raw_message if char.isprintable()).split())[:240]
            if not message:
                return
            now = asyncio.get_running_loop().time()
            last_sent = self.chat_last_sent.get(player_name)
            if last_sent is not None and now - last_sent < 0.35:
                return
            self.chat_last_sent[player_name] = now
            chat_message = {"sender": player_name, "message": message}
            self.chat_history.append(chat_message)
            if len(self.chat_history) > 200:
                self.chat_history = self.chat_history[-200:]
            await self.broadcast_json({"type": "chat", **chat_message})
            return
        if message_type == "continue_round" and self.state.current_phase == GamePhase.ROUND_END:
            if player_name not in self.connections:
                return
            self.round_ready_names.add(player_name)
            if set(self.connections).issubset(self.round_ready_names):
                self._clear_round_wait()
                self.state.proceed_after_round()
                self.state.advance_automatic(play_ai_cards=False, play_ai_predictions=False)
                await self.broadcast_state()
                await self.schedule_ai_prediction_if_needed()
                await self.schedule_bot_turn_if_needed()
                return
            await self.broadcast_state()
            return

        changed = False
        if message_type == "set_prediction":
            changed = self.state.set_player_prediction(player_name, int(payload.get("value", 0)))
        elif message_type == "play_card":
            card = str(payload.get("card", "")).strip()
            changed = self.state.play_player_card(player_name, card)

        if not changed:
            return

        self.state.advance_automatic(play_ai_cards=False, play_ai_predictions=False)
        await self.broadcast_state()
        await self.schedule_ai_prediction_if_needed()
        await self.schedule_bot_turn_if_needed()
        await self.schedule_trick_resolution_if_needed()

    async def schedule_ai_prediction_if_needed(self) -> None:
        if self.state is None or self.state.current_phase != GamePhase.AI_PREDICTIONS:
            return
        if self.prediction_task and not self.prediction_task.done():
            return
        self.prediction_task = asyncio.create_task(self._play_ai_predictions_with_delay())

    async def _play_ai_predictions_with_delay(self) -> None:
        try:
            while self.state is not None and self.state.current_phase == GamePhase.AI_PREDICTIONS:
                await asyncio.sleep(PREDICTION_REVEAL_DELAY)
                if self.state is None or self.state.current_phase != GamePhase.AI_PREDICTIONS:
                    return
                reveal = self.state.advance_one_ai_prediction()
                if reveal is None:
                    continue
                player_name, value = reveal
                await self.broadcast_state(
                    prediction_reveal={"name": player_name, "value": value}
                )
                if self.state.current_phase == GamePhase.PLAY_TRICK:
                    # Keep the final prediction banner visible before the
                    # first bot card begins its own turn delay.
                    await asyncio.sleep(PREDICTION_REVEAL_DELAY)
                    await self.schedule_bot_turn_if_needed()
                    return
        finally:
            self.prediction_task = None

    async def schedule_round_timeout_if_needed(self) -> None:
        if self.state is None or self.state.current_phase != GamePhase.ROUND_END:
            return
        if self.round_task and not self.round_task.done():
            return
        loop = asyncio.get_running_loop()
        self.round_deadline = loop.time() + 15.0
        self.round_task = asyncio.create_task(self._advance_after_round_timeout())

    async def _advance_after_round_timeout(self) -> None:
        try:
            await asyncio.sleep(15.0)
            if self.state is None or self.state.current_phase != GamePhase.ROUND_END:
                return
            self.round_task = None
            self.round_deadline = None
            self.round_ready_names.clear()
            self.state.proceed_after_round()
            self.state.advance_automatic(play_ai_cards=False, play_ai_predictions=False)
            await self.broadcast_state()
            await self.schedule_ai_prediction_if_needed()
            await self.schedule_bot_turn_if_needed()
        finally:
            if self.round_task is asyncio.current_task():
                self.round_task = None

    def _clear_round_wait(self) -> None:
        task = self.round_task
        self.round_task = None
        self.round_deadline = None
        self.round_ready_names.clear()
        if task and task is not asyncio.current_task() and not task.done():
            task.cancel()

    async def schedule_bot_turn_if_needed(self) -> None:
        if self.state is None or self.state.current_phase != GamePhase.PLAY_TRICK:
            return
        if self.state.current_player.is_human:
            return
        if self.bot_task and not self.bot_task.done():
            return
        self.bot_task = asyncio.create_task(self._play_bot_turns_with_delay())

    async def _play_bot_turns_with_delay(self) -> None:
        try:
            while self.state is not None and self.state.current_phase == GamePhase.PLAY_TRICK:
                if self.state.current_player.is_human:
                    return
                await asyncio.sleep(AI_PLAY_DELAY)
                if self.state is None or self.state.current_phase != GamePhase.PLAY_TRICK:
                    return
                if self.state.current_player.is_human:
                    return
                self.state.play_ai_card()
                await self.broadcast_state()
                if self.state.current_phase == GamePhase.TRICK_RESOLUTION:
                    await self.schedule_trick_resolution_if_needed()
                    return
        finally:
            self.bot_task = None

    async def schedule_trick_resolution_if_needed(self) -> None:
        if self.state is None or self.state.current_phase != GamePhase.TRICK_RESOLUTION:
            return
        if self.trick_task and not self.trick_task.done():
            return
        self.trick_task = asyncio.create_task(self._resolve_trick_after_delay())

    async def _resolve_trick_after_delay(self) -> None:
        try:
            # Match the local client: reveal the winner after 0.8s, then keep
            # the result visible for another 3s.
            await asyncio.sleep(TRICK_WINNER_REVEAL_DELAY + TRICK_RESOLVE_DELAY)
            if self.state is None or self.state.current_phase != GamePhase.TRICK_RESOLUTION:
                return
            self.state.advance_after_trick()
            self.state.advance_automatic(play_ai_cards=False, play_ai_predictions=False)
            await self.schedule_round_timeout_if_needed()
            await self.broadcast_state()
            await self.schedule_ai_prediction_if_needed()
            await self.schedule_bot_turn_if_needed()
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
            # Bots are chosen in the lobby after humans have joined.
            bot_count = 0
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
            if room.state is not None:
                await websocket.send(json.dumps({"type": "error", "message": "La partida ya comenzó."}))
                return
            if len(room.connections) >= 7 and player_name not in room.connections:
                await websocket.send(json.dumps({"type": "error", "message": "La sala ya está llena."}))
                return
            if player_name in room.connections:
                await websocket.send(json.dumps({"type": "error", "message": "Ese nombre ya está en uso en la sala. Elige otro distinto."}))
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
