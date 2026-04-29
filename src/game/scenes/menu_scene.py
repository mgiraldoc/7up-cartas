from __future__ import annotations

from typing import Dict, List, Tuple

import pygame

from src.game.fonts import load_font

from .base import Scene
from .game_scene import GameScene


class MenuScene(Scene):
    BG_COLOR = pygame.Color(7, 18, 12)
    PANEL_COLOR = pygame.Color(14, 32, 22)
    PANEL_ALT = pygame.Color(20, 45, 31)
    TEXT_COLOR = pygame.Color(229, 237, 228)
    TEXT_DIM = pygame.Color(144, 170, 149)
    ACCENT = pygame.Color(214, 185, 92)
    BUTTON_COLOR = pygame.Color(228, 235, 224)
    BUTTON_SELECTED = pygame.Color(214, 185, 92)
    BUTTON_TEXT = pygame.Color(18, 36, 24)
    BORDER_COLOR = pygame.Color(4, 11, 8)

    MODE_LOCAL = "local"
    MODE_HOST = "online_host"
    MODE_JOIN = "online_join"

    def __init__(self, app) -> None:
        super().__init__(app)
        self.font = load_font(40)
        self.font_small = load_font(24)
        self.font_tiny = load_font(18)
        self.mode_buttons: Dict[str, pygame.Rect] = {}
        self.bot_buttons: List[Tuple[int, pygame.Rect]] = []
        self.start_button = pygame.Rect(0, 0, 0, 0)
        self.room_code_box = pygame.Rect(0, 0, 0, 0)
        self.name_box = pygame.Rect(0, 0, 0, 0)
        self.selected_bot_count = max(0, min(5, self.app.config.bot_count))
        self.selected_mode = self.app.config.online_mode if self.app.config.online_mode != "local" else self.MODE_LOCAL
        self.room_code_input = self.app.config.room_code.upper().strip()[:4]
        self.name_input = self.app.config.human_name.strip() or "Jugador"
        self.name_active = False
        self.feedback = ""

    def on_enter(self) -> None:
        if self.app.online_client is not None:
            self.app.online_client.close()
            self.app.online_client = None
        self.app.online_state_snapshot = None
        self.selected_bot_count = max(0, min(5, self.app.config.bot_count))
        self.room_code_input = self.app.config.room_code.upper().strip()[:4]
        self.name_input = self.app.config.human_name.strip() or "Jugador"
        self.name_active = False
        self.feedback = ""

    def handle_event(self, event: pygame.event.Event) -> None:
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            mouse = pygame.Vector2(event.pos[0] / self.app.scale, event.pos[1] / self.app.scale)
            self._handle_click(mouse)
        elif event.type == pygame.KEYDOWN:
            if self.name_active:
                if event.key == pygame.K_BACKSPACE:
                    self.name_input = self.name_input[:-1]
                elif event.key in (pygame.K_RETURN, pygame.K_TAB):
                    self.name_active = False
                else:
                    if event.unicode and (event.unicode.isalnum() or event.unicode in " _-") and len(self.name_input) < 18:
                        self.name_input += event.unicode
                return
            if event.key in (pygame.K_TAB,):
                self._cycle_mode()
            elif self.selected_mode in (self.MODE_LOCAL, self.MODE_HOST):
                if event.key in (pygame.K_LEFT, pygame.K_a):
                    self.selected_bot_count = max(0, self.selected_bot_count - 1)
                elif event.key in (pygame.K_RIGHT, pygame.K_d):
                    self.selected_bot_count = min(5, self.selected_bot_count + 1)
                elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
                    self._start_game()
            elif self.selected_mode == self.MODE_JOIN:
                if event.key == pygame.K_BACKSPACE:
                    self.room_code_input = self.room_code_input[:-1]
                elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
                    self._start_game()
                else:
                    if event.unicode and event.unicode.isalnum() and len(self.room_code_input) < 4:
                        self.room_code_input += event.unicode.upper()

    def _handle_click(self, mouse: pygame.Vector2) -> None:
        for mode, rect in self.mode_buttons.items():
            if rect.collidepoint(mouse):
                self.selected_mode = mode
                self.feedback = ""
                self.name_active = False
                return
        if self.name_box.collidepoint(mouse):
            self.name_active = True
            self.feedback = ""
            return
        self.name_active = False
        for bot_count, rect in self.bot_buttons:
            if rect.collidepoint(mouse):
                self.selected_bot_count = bot_count
                return
        if self.start_button.collidepoint(mouse):
            self._start_game()

    def _cycle_mode(self) -> None:
        order = [self.MODE_LOCAL, self.MODE_HOST, self.MODE_JOIN]
        index = order.index(self.selected_mode)
        self.selected_mode = order[(index + 1) % len(order)]
        self.feedback = ""

    def _start_game(self) -> None:
        self.app.config.bot_count = self.selected_bot_count
        self.app.config.online_mode = self.selected_mode
        self.app.config.room_code = self.room_code_input
        self.app.config.human_name = self.name_input.strip() or "Jugador"

        if self.selected_mode == self.MODE_LOCAL:
            if self.selected_bot_count < 1:
                self.feedback = "El modo local necesita al menos 1 bot."
                return
            self.app.manager.set_scene(GameScene)
            return

        if self.selected_mode == self.MODE_HOST:
            from .online_lobby_scene import OnlineLobbyScene

            self.app.manager.set_scene(OnlineLobbyScene)
            return

        if len(self.room_code_input) != 4:
            self.feedback = "Escribe un código de 4 caracteres."
            return
        from .online_lobby_scene import OnlineLobbyScene

        self.app.manager.set_scene(OnlineLobbyScene)

    def draw(self, surface: pygame.Surface) -> None:
        surface.fill(self.BG_COLOR)
        self.bot_buttons.clear()
        self.mode_buttons.clear()

        panel_width = min(660, surface.get_width() - 88)
        panel_height = min(380, surface.get_height() - 72)
        panel = pygame.Rect(
            (surface.get_width() - panel_width) // 2,
            (surface.get_height() - panel_height) // 2,
            panel_width,
            panel_height,
        )

        pygame.draw.rect(surface, self.PANEL_COLOR, panel, border_radius=10)
        pygame.draw.rect(surface, self.BORDER_COLOR, panel, 2, border_radius=10)

        self._blit_text(surface, "7UP - Cartas", (panel.x + 28, panel.y + 26), self.font, self.ACCENT)
        self._blit_text(surface, "Tu nombre", (panel.x + 28, panel.y + 76), self.font_tiny, self.TEXT_DIM)
        self.name_box = pygame.Rect(panel.x + 128, panel.y + 68, 220, 34)
        pygame.draw.rect(surface, self.PANEL_ALT if self.name_active else self.BUTTON_COLOR, self.name_box, border_radius=8)
        pygame.draw.rect(surface, self.ACCENT if self.name_active else self.BORDER_COLOR, self.name_box, 2, border_radius=8)
        name_text = self.name_input or "Jugador"
        if self.name_active and pygame.time.get_ticks() // 500 % 2 == 0:
            name_text += "_"
        self._blit_text(surface, name_text, (self.name_box.x + 12, self.name_box.y + 7), self.font_tiny, self.BUTTON_TEXT)
        self._blit_text(surface, f"Servidor: {self.app.config.server_url}", (panel.x + 28, panel.y + 102), self.font_tiny, self.TEXT_DIM)

        mode_y = panel.y + 142
        mode_specs = [
            (self.MODE_LOCAL, "Local"),
            (self.MODE_HOST, "Crear sala"),
            (self.MODE_JOIN, "Unirse"),
        ]
        x = panel.x + 28
        for mode, label in mode_specs:
            rect = pygame.Rect(x, mode_y, 180, 42)
            selected = mode == self.selected_mode
            pygame.draw.rect(surface, self.BUTTON_SELECTED if selected else self.BUTTON_COLOR, rect, border_radius=8)
            pygame.draw.rect(surface, self.BORDER_COLOR, rect, 2, border_radius=8)
            self._blit_text(surface, label, (rect.x + 22, rect.y + 10), self.font_tiny, self.BUTTON_TEXT)
            self.mode_buttons[mode] = rect
            x += 194

        if self.selected_mode in (self.MODE_LOCAL, self.MODE_HOST):
            label = "Bots" if self.selected_mode == self.MODE_LOCAL else "Bots extra"
            self._blit_text(surface, f"{label}: {self.selected_bot_count}", (panel.x + 28, panel.y + 212), self.font_small, self.TEXT_COLOR)
            start_x = panel.x + 28
            start_y = panel.y + 256
            for index, bot_count in enumerate(range(0, 6)):
                rect = pygame.Rect(start_x + index * 62, start_y, 52, 44)
                selected = bot_count == self.selected_bot_count
                pygame.draw.rect(surface, self.BUTTON_SELECTED if selected else self.BUTTON_COLOR, rect, border_radius=8)
                pygame.draw.rect(surface, self.BORDER_COLOR, rect, 2, border_radius=8)
                self._blit_text(surface, str(bot_count), (rect.x + 18, rect.y + 10), self.font_small, self.BUTTON_TEXT)
                self.bot_buttons.append((bot_count, rect))
        else:
            self._blit_text(surface, "Código de sala", (panel.x + 28, panel.y + 212), self.font_small, self.TEXT_COLOR)
            self.room_code_box = pygame.Rect(panel.x + 28, panel.y + 252, 240, 52)
            pygame.draw.rect(surface, self.PANEL_ALT, self.room_code_box, border_radius=8)
            pygame.draw.rect(surface, self.ACCENT, self.room_code_box, 2, border_radius=8)
            room_text = self.room_code_input or "----"
            self._blit_text(surface, room_text, (self.room_code_box.x + 18, self.room_code_box.y + 14), self.font_small, self.TEXT_COLOR)
            self._blit_text(surface, "Escribe 4 caracteres y presiona Enter", (panel.x + 288, panel.y + 268), self.font_tiny, self.TEXT_DIM)

        self.start_button = pygame.Rect(panel.x + 28, panel.bottom - 72, panel.width - 56, 46)
        pygame.draw.rect(surface, self.PANEL_ALT, self.start_button, border_radius=8)
        pygame.draw.rect(surface, self.ACCENT, self.start_button, 2, border_radius=8)
        start_label = {
            self.MODE_LOCAL: "Jugar local",
            self.MODE_HOST: "Crear sala online",
            self.MODE_JOIN: "Entrar a la sala",
        }[self.selected_mode]
        start_width = self.font_small.render(start_label, False, self.TEXT_COLOR).get_width()
        self._blit_text(
            surface,
            start_label,
            (self.start_button.centerx - start_width // 2, self.start_button.y + 12),
            self.font_small,
            self.TEXT_COLOR,
        )

        helper = "Click en tu nombre para editarlo. Tab cambia modo. Enter confirma."
        self._blit_text(surface, helper, (panel.x + 28, panel.bottom - 22), self.font_tiny, self.TEXT_DIM)
        if self.feedback:
            self._blit_text(surface, self.feedback, (panel.x + 28, panel.bottom - 104), self.font_tiny, pygame.Color(220, 110, 110))

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
