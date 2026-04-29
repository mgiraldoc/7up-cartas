from __future__ import annotations

from typing import Dict, Tuple

import pygame

from src.core.game_logic import CardGameState
from src.game.fonts import load_font
from src.game.online import OnlineClient

from .base import Scene
from .game_scene import GameScene
from .menu_scene import MenuScene


class OnlineLobbyScene(Scene):
    BG_COLOR = pygame.Color(7, 18, 12)
    PANEL_COLOR = pygame.Color(14, 32, 22)
    PANEL_ALT = pygame.Color(20, 45, 31)
    TEXT_COLOR = pygame.Color(229, 237, 228)
    TEXT_DIM = pygame.Color(144, 170, 149)
    ACCENT = pygame.Color(214, 185, 92)
    BORDER_COLOR = pygame.Color(4, 11, 8)

    def __init__(self, app) -> None:
        super().__init__(app)
        self.font = load_font(36)
        self.font_small = load_font(22)
        self.font_tiny = load_font(18)
        self.status = "Conectando con el servidor..."
        self.room_code = app.config.room_code
        self.players: list[str] = []
        self.error_message = ""
        self.back_button = pygame.Rect(0, 0, 0, 0)

    def on_enter(self) -> None:
        if self.app.online_client is not None:
            self.app.online_client.close()
            self.app.online_client = None
        self.app.online_state_snapshot = None
        client = OnlineClient(
            self.app.config.server_url,
            self.app.config.human_name,
            self.app.config.online_mode,
            room_code=self.app.config.room_code,
            bot_count=self.app.config.bot_count,
        )
        self.app.online_client = client
        client.start()

    def on_exit(self) -> None:
        if self.app.manager.current is not self and self.error_message:
            if self.app.online_client is not None:
                self.app.online_client.close()
                self.app.online_client = None

    def handle_event(self, event: pygame.event.Event) -> None:
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            mouse = pygame.Vector2(event.pos[0] / self.app.scale, event.pos[1] / self.app.scale)
            if self.back_button.collidepoint(mouse):
                self._go_back()
        elif event.type == pygame.KEYDOWN and event.key in (pygame.K_ESCAPE, pygame.K_RETURN):
            if self.error_message:
                self._go_back()

    def update(self, dt: float) -> None:
        del dt
        client = self.app.online_client
        if client is None:
            self.error_message = "No se pudo crear la conexión online."
            return
        for event in client.poll_events():
            event_type = event.get("type")
            if event_type == "lobby":
                self.room_code = str(event.get("room_code", "")).upper()
                self.players = list(event.get("players", []))
                humans_needed = int(event.get("humans_needed", 2))
                self.status = f"Esperando jugadores ({len(self.players)}/{humans_needed})"
            elif event_type == "state":
                snapshot = event.get("state")
                if isinstance(snapshot, dict):
                    self.app.online_state_snapshot = snapshot
                    self.app.manager.set_scene(GameScene)
                    return
            elif event_type == "error":
                self.error_message = str(event.get("message", "Error de conexión."))
                self.status = "No se pudo continuar."

    def draw(self, surface: pygame.Surface) -> None:
        surface.fill(self.BG_COLOR)
        panel = pygame.Rect(120, 88, surface.get_width() - 240, surface.get_height() - 176)
        pygame.draw.rect(surface, self.PANEL_COLOR, panel, border_radius=12)
        pygame.draw.rect(surface, self.BORDER_COLOR, panel, 2, border_radius=12)

        title = "Crear sala online" if self.app.config.online_mode == "online_host" else "Unirse a sala"
        self._blit_text(surface, title, (panel.x + 24, panel.y + 24), self.font, self.ACCENT)
        self._blit_text(surface, self.status, (panel.x + 24, panel.y + 84), self.font_small, self.TEXT_COLOR)
        self._blit_text(surface, f"Servidor: {self.app.config.server_url}", (panel.x + 24, panel.y + 118), self.font_tiny, self.TEXT_DIM)

        room_label = f"Código de sala: {self.room_code or '----'}"
        self._blit_text(surface, room_label, (panel.x + 24, panel.y + 152), self.font_small, self.ACCENT)

        y = panel.y + 196
        if self.players:
            self._blit_text(surface, "Jugadores conectados:", (panel.x + 24, y), self.font_small, self.TEXT_COLOR)
            y += 36
            for player_name in self.players:
                self._blit_text(surface, f"- {player_name}", (panel.x + 36, y), self.font_small, self.TEXT_DIM)
                y += 28

        if self.error_message:
            self._blit_text(surface, self.error_message, (panel.x + 24, panel.bottom - 84), self.font_tiny, pygame.Color(220, 110, 110))
            self.back_button = pygame.Rect(panel.x + 24, panel.bottom - 56, 180, 34)
            pygame.draw.rect(surface, self.PANEL_ALT, self.back_button, border_radius=8)
            pygame.draw.rect(surface, self.ACCENT, self.back_button, 2, border_radius=8)
            self._blit_text(surface, "Volver al menú", (self.back_button.x + 18, self.back_button.y + 8), self.font_tiny, self.TEXT_COLOR)
        else:
            self.back_button = pygame.Rect(0, 0, 0, 0)

    def _go_back(self) -> None:
        if self.app.online_client is not None:
            self.app.online_client.close()
            self.app.online_client = None
        self.app.online_state_snapshot = None
        self.app.manager.set_scene(MenuScene)

    def _blit_text(
        self,
        surface: pygame.Surface,
        text: str,
        position: Tuple[int, int],
        font: pygame.font.Font,
        color: pygame.Color,
    ) -> None:
        rendered = font.render(text, False, color)
        surface.blit(rendered, (int(position[0]), int(position[1])))
