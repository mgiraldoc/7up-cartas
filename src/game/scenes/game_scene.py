from __future__ import annotations

import random
from typing import Dict, List, Optional, Tuple

import pygame

from src.core.game_logic import (
    BOT_NAME_POOL,
    CardGameState,
    GamePhase,
    PlayerState,
)
from src.game.fonts import load_font, load_suit_surface

from .base import Scene


class GameScene(Scene):
    BG_COLOR = pygame.Color(7, 18, 12)
    PANEL_COLOR = pygame.Color(14, 32, 22)
    PANEL_ALT = pygame.Color(20, 45, 31)
    TEXT_COLOR = pygame.Color(229, 237, 228)
    TEXT_DIM = pygame.Color(144, 170, 149)
    ACCENT = pygame.Color(214, 185, 92)
    CARD_BG = pygame.Color(230, 230, 230)
    CARD_BG_SELECTED = pygame.Color(255, 235, 190)
    CARD_BORDER = pygame.Color(32, 36, 48)
    CARD_WIDTH = 56
    CARD_HEIGHT = 80
    HEADER_HEIGHT = 76
    INFO_HEIGHT = 34
    AI_PLAY_DELAY = 0.65
    TRICK_RESOLVE_DELAY = 1.25
    PLAYER_ROW_HEIGHT = 72
    SCOREBOARD_TOP_PADDING = 44

    def __init__(self, app) -> None:
        super().__init__(app)
        self.font = load_font(34)
        self.font_small = load_font(24)
        self.font_tiny = load_font(18)
        self.suit_surfaces = {
            "♦": load_suit_surface("diamante.png"),
            "♥": load_suit_surface("corazon.png"),
            "♠": load_suit_surface("pica.png"),
            "♣": load_suit_surface("trebol.png"),
        }
        self.suit_scale_cache: Dict[Tuple[str, int], pygame.Surface] = {}

        self.state: Optional[CardGameState] = None
        self.card_rects: Dict[str, pygame.Rect] = {}
        self.prediction_buttons: List[Tuple[int, pygame.Rect]] = []
        self.ai_timer: float = 0.0
        self.trick_timer: float = 0.0
        self.info_message: str = ""
        self.previous_phase: Optional[GamePhase] = None
        self.scoreboard_scroll: float = 0.0
        self.round_intro_active: bool = False
        self.game_over_menu_buttons: Dict[str, pygame.Rect] = {}
        self.is_online = False

    def on_enter(self) -> None:
        config = self.app.config
        self.is_online = (
            self.app.online_client is not None
            and self.app.online_state_snapshot is not None
            and config.online_mode != "local"
        )
        if self.is_online:
            self.state = CardGameState.from_snapshot(self.app.online_state_snapshot)
        else:
            available_names = [n for n in BOT_NAME_POOL if n.lower() != config.human_name.lower()]
            bot_names = random.sample(available_names, k=min(config.bot_count, len(available_names)))
            self.state = CardGameState(config.human_name, bot_names)
        self.previous_phase = self.state.current_phase
        self.info_message = "Selecciona tu predicción"
        self.scoreboard_scroll = 0.0
        self.round_intro_active = self._is_double_points_round()

    def handle_event(self, event: pygame.event.Event) -> None:
        if not self.state:
            return

        if self.round_intro_active:
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                self.round_intro_active = False
            elif event.type == pygame.KEYDOWN and event.key in (pygame.K_RETURN, pygame.K_SPACE):
                self.round_intro_active = False
            return

        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            mouse = pygame.Vector2(event.pos[0] / self.app.scale, event.pos[1] / self.app.scale)
            self._handle_click(mouse)

        if event.type == pygame.KEYDOWN:
            if event.key in (pygame.K_RETURN, pygame.K_SPACE):
                self._handle_primary_action()
            elif event.key == pygame.K_DOWN:
                self._scroll_scoreboard(40)
            elif event.key == pygame.K_UP:
                self._scroll_scoreboard(-40)
        elif event.type == pygame.MOUSEWHEEL:
            self._scroll_scoreboard(-event.y * 32)

    def _handle_click(self, mouse: pygame.Vector2) -> None:
        assert self.state is not None
        phase = self.state.current_phase
        if phase == GamePhase.HUMAN_PREDICTION:
            for value, rect in self.prediction_buttons:
                if rect.collidepoint(mouse):
                    if self.is_online and self.app.online_client is not None:
                        self.app.online_client.send({"type": "set_prediction", "value": value})
                    else:
                        self.state.set_human_prediction(value)
                    break
        elif phase == GamePhase.PLAY_TRICK:
            player = self.state.current_player
            if player.is_human:
                for card, rect in self.card_rects.items():
                    if rect.collidepoint(mouse):
                        if self.is_online and self.app.online_client is not None:
                            self.app.online_client.send({"type": "play_card", "card": card})
                            self.info_message = self._format_card_play_message(
                                self.state.get_human_player().name,
                                card,
                            )
                        elif self.state.play_human_card(card):
                            self.info_message = self._format_card_play_message(
                                self.state.get_human_player().name,
                                card,
                            )
                        break
        elif phase == GamePhase.ROUND_END:
            if self.is_online and self.app.online_client is not None:
                self.app.online_client.send({"type": "continue_round"})
            else:
                self.state.proceed_after_round()
        elif phase == GamePhase.GAME_OVER:
            for action, rect in self.game_over_menu_buttons.items():
                if rect.collidepoint(mouse):
                    if action == "menu":
                        from .menu_scene import MenuScene

                        if self.app.online_client is not None:
                            self.app.online_client.close()
                            self.app.online_client = None
                            self.app.online_state_snapshot = None
                        self.app.manager.set_scene(MenuScene)
                    elif action == "exit":
                        if self.app.online_client is not None:
                            self.app.online_client.close()
                        self.app.running = False
                    break

    def _handle_primary_action(self) -> None:
        if not self.state:
            return
        if self.state.current_phase == GamePhase.ROUND_END:
            if self.is_online and self.app.online_client is not None:
                self.app.online_client.send({"type": "continue_round"})
            else:
                self.state.proceed_after_round()
        elif self.state.current_phase == GamePhase.GAME_OVER:
            from .menu_scene import MenuScene

            if self.app.online_client is not None:
                self.app.online_client.close()
                self.app.online_client = None
                self.app.online_state_snapshot = None
            self.app.manager.set_scene(MenuScene)

    def update(self, dt: float) -> None:
        if not self.state:
            return

        if self.is_online and self.app.online_client is not None:
            for event in self.app.online_client.poll_events():
                event_type = event.get("type")
                if event_type == "state":
                    snapshot = event.get("state")
                    if isinstance(snapshot, dict):
                        self.app.online_state_snapshot = snapshot
                        self.state = CardGameState.from_snapshot(snapshot)
                elif event_type == "error":
                    self.info_message = str(event.get("message", "Error online"))
            if self.state.current_phase != self.previous_phase:
                self._on_phase_change(self.previous_phase, self.state.current_phase)
                self.previous_phase = self.state.current_phase
            if self.state.current_phase == GamePhase.GAME_OVER:
                self.info_message = "Partida terminada"
            return

        if self.state.current_phase != self.previous_phase:
            self._on_phase_change(self.previous_phase, self.state.current_phase)
            self.previous_phase = self.state.current_phase

        if self.state.current_phase == GamePhase.PLAY_TRICK:
            current = self.state.current_player
            if not current.is_human:
                self.ai_timer += dt
                if self.ai_timer >= self.AI_PLAY_DELAY:
                    self.ai_timer = 0.0
                    card = self.state.play_ai_card()
                    if card:
                        self.info_message = self._format_card_play_message(
                            current.name,
                            card,
                        )
        elif self.state.current_phase == GamePhase.TRICK_RESOLUTION:
            self.trick_timer += dt
            if self.trick_timer >= self.TRICK_RESOLVE_DELAY:
                self.trick_timer = 0.0
                self.state.advance_after_trick()
        elif self.state.current_phase == GamePhase.GAME_OVER:
            self.info_message = "Partida terminada"

    def _on_phase_change(self, previous: Optional[GamePhase], current: GamePhase) -> None:
        if (
            previous == GamePhase.ROUND_END
            and current in (GamePhase.AI_PREDICTIONS, GamePhase.HUMAN_PREDICTION)
            and self._is_double_points_round()
        ):
            self.round_intro_active = True
        if current == GamePhase.HUMAN_PREDICTION:
            self.info_message = "Selecciona tu predicción"
        elif current == GamePhase.AI_PREDICTIONS:
            self.info_message = "Esperando predicciones de la IA..."
        elif current == GamePhase.PLAY_TRICK:
            self.info_message = "Juega una carta" if self.state and self.state.current_player.is_human else "Turno de la IA"
        elif current == GamePhase.TRICK_RESOLUTION and self.state:
            winner = self.state.last_trick_winner or ""
            winning_card = self.state.current_trick_cards.get(winner, "")
            self.info_message = (
                f"{winner} gana la baza con {self._format_card_name(winning_card)}"
                if winning_card
                else f"{winner} gana la baza"
            )
        elif current == GamePhase.ROUND_END:
            self.info_message = "Ronda finalizada - presiona Espacio"

    def draw(self, surface: pygame.Surface) -> None:
        surface.fill(self.BG_COLOR)
        if not self.state:
            return

        self.card_rects.clear()
        self.prediction_buttons.clear()
        self.game_over_menu_buttons.clear()

        self._draw_header(surface)
        self._draw_scoreboard(surface)
        self._draw_trick(surface)
        self._draw_players(surface)
        self._draw_info(surface)

        if self.state.current_phase == GamePhase.HUMAN_PREDICTION:
            self._draw_prediction_panel(surface)

        if self.state.current_phase in (GamePhase.ROUND_END, GamePhase.GAME_OVER):
            self._draw_round_overlay(surface)
        elif self.round_intro_active:
            self._draw_round_intro_overlay(surface)

    def _draw_header(self, surface: pygame.Surface) -> None:
        pygame.draw.rect(surface, self.PANEL_COLOR, pygame.Rect(0, 0, surface.get_width(), self.HEADER_HEIGHT))
        round_no = self.state.round_index + 1
        total_rounds = self.state.total_round_count
        text = f"Ronda {round_no}/{total_rounds}  |  Cartas: {self.state.cards_per_player}"
        self._blit_text(surface, text, (18, 10), color=self.TEXT_COLOR, font=self.font_small)
        if self._is_double_points_round():
            self._blit_text(
                surface,
                "PUNTOS DOBLES",
                (18, 40),
                color=self.ACCENT,
                font=self.font_tiny,
            )

        trump_card = self.state.trump_card or ""
        trump_label_x = surface.get_width() - 190
        trump_label_y = 18
        self._blit_text(surface, "Triunfo:", (trump_label_x, trump_label_y), color=self.ACCENT, font=self.font_small)
        if trump_card:
            preview_x = surface.get_width() - 82
            preview_y = 8
            self._draw_card(surface, trump_card, (preview_x, preview_y), compact=True)

    def _draw_scoreboard(self, surface: pygame.Surface) -> None:
        panel = pygame.Rect(surface.get_width() - 274, 92, 248, 278)
        pygame.draw.rect(surface, self.PANEL_COLOR, panel, border_radius=6)
        pygame.draw.rect(surface, self.CARD_BORDER, panel, 1)
        self._blit_text(surface, "Marcador", (panel.x + 14, panel.y + 12), font=self.font_small)
        viewport = pygame.Rect(panel.x + 10, panel.y + self.SCOREBOARD_TOP_PADDING, panel.width - 20, panel.height - 70)
        pygame.draw.rect(surface, self.PANEL_ALT, viewport, border_radius=6)

        players_in_order = self._get_scoreboard_players()
        total_content_height = len(players_in_order) * self.PLAYER_ROW_HEIGHT
        max_scroll = max(0, total_content_height - viewport.height)
        self.scoreboard_scroll = max(0, min(self.scoreboard_scroll, max_scroll))

        previous_clip = surface.get_clip()
        surface.set_clip(viewport)
        y = viewport.y - int(self.scoreboard_scroll)
        for player in players_in_order:
            name_color = self.ACCENT if player.is_human else self.TEXT_COLOR
            self._blit_text(surface, player.name, (viewport.x + 8, y), font=self.font_small, color=name_color)
            self._blit_text(
                surface,
                f"Pred: {player.prediction if player.prediction is not None else '-'}",
                (viewport.x + 8, y + 24),
                font=self.font_tiny,
                color=self.TEXT_DIM,
            )
            self._blit_text(
                surface,
                f"Bazas: {player.tricks_won}  |  Pts: {player.score}",
                (viewport.x + 8, y + 44),
                font=self.font_tiny,
                color=self.TEXT_COLOR,
            )
            y += self.PLAYER_ROW_HEIGHT
        surface.set_clip(previous_clip)

        if max_scroll > 0:
            self._blit_text(
                surface,
                "Scroll: rueda o flechas",
                (panel.x + 14, panel.bottom - 20),
                font=self.font_tiny,
                color=self.TEXT_DIM,
            )

    def _draw_trick(self, surface: pygame.Surface) -> None:
        area = pygame.Rect(18, 92, surface.get_width() - 320, 278)
        pygame.draw.rect(surface, self.PANEL_ALT, area, border_radius=8)
        pygame.draw.rect(surface, self.CARD_BORDER, area, 1)
        self._blit_text(surface, "Mesa", (area.x + 16, area.y + 12), font=self.font_small, color=self.TEXT_COLOR)

        if not self.state.current_trick_cards:
            self._blit_text(surface, "Baza en curso", (area.x + 16, area.y + 46), font=self.font_small, color=self.TEXT_DIM)
            return

        played = [
            (name, self.state.current_trick_cards[name])
            for name in self.state.turn_order
            if name in self.state.current_trick_cards
        ]
        if not played:
            return
        count = len(played)
        usable_width = area.width - 48
        preview_width = min(int(self.CARD_WIDTH * 0.9), max(36, usable_width // max(count, 1) - 12))
        spacing = min(preview_width + 18, max(preview_width + 6, usable_width // max(count, 1)))
        total_width = count * preview_width + max(0, count - 1) * (spacing - preview_width)
        x = area.centerx - total_width // 2
        y = area.y + 104
        for name, card in played:
            card_scale = preview_width / self.CARD_WIDTH
            rect = self._draw_card(surface, card, (x, y), scale_override=card_scale)
            name_width = self.font_tiny.render(name, False, self.TEXT_COLOR).get_width()
            self._blit_text(
                surface,
                name,
                (rect.centerx - name_width // 2, rect.y - 24),
                font=self.font_tiny,
                color=self.TEXT_COLOR,
            )
            x += spacing

    def _draw_players(self, surface: pygame.Surface) -> None:
        human = self.state.get_human_player()

        bottom_panel = pygame.Rect(0, surface.get_height() - 150, surface.get_width(), 110)
        pygame.draw.rect(surface, self.PANEL_COLOR, bottom_panel)
        pygame.draw.rect(surface, self.CARD_BORDER, bottom_panel, 1)

        cards = human.hand
        base_x = 28
        base_y = bottom_panel.y + 20
        available_width = surface.get_width() - 56
        if len(cards) > 1:
            spacing = min(
                self.CARD_WIDTH + 12,
                max(32, (available_width - self.CARD_WIDTH) // (len(cards) - 1)),
            )
        else:
            spacing = self.CARD_WIDTH + 12
        for idx, card in enumerate(cards):
            card_pos = (base_x + idx * spacing, base_y)
            is_playable = self._is_card_playable(human, card)
            draw_pos = (card_pos[0], card_pos[1] - 12 if is_playable else card_pos[1])
            rect = self._draw_card(surface, card, draw_pos, selected=is_playable)
            self.card_rects[card] = rect

        hand_label = f"Tu mano ({len(cards)} cartas)"
        self._blit_text(surface, hand_label, (24, bottom_panel.y - 30), font=self.font_small, color=self.TEXT_COLOR)

    def _is_card_playable(self, player: PlayerState, card: str) -> bool:
        if self.state.current_phase != GamePhase.PLAY_TRICK:
            return False
        if self.state.current_player.name != player.name:
            return False
        lead = self.state.lead_suit
        if lead is None:
            return True
        hand = player.hand
        if any(c[-1] == lead for c in hand):
            return card[-1] == lead
        return True

    def _draw_prediction_panel(self, surface: pygame.Surface) -> None:
        max_pred = self.state.cards_per_player
        panel_width = max(280, 28 + (max_pred + 1) * 46)
        panel = pygame.Rect(
            max(12, int((self.app.logical_size.x - panel_width) // 2)),
            112,
            panel_width,
            118,
        )
        pygame.draw.rect(surface, self.PANEL_COLOR, panel, border_radius=4)
        pygame.draw.rect(surface, self.CARD_BORDER, panel, 1)
        self._blit_text(surface, "Selecciona tu predicción", (panel.x + 16, panel.y + 14), font=self.font_small)

        buttons: List[Tuple[int, pygame.Rect]] = []
        start_x = panel.x + 14
        start_y = panel.y + 58
        for value in range(0, max_pred + 1):
            rect = pygame.Rect(start_x + (value * 46), start_y, 40, 40)
            pygame.draw.rect(surface, self.CARD_BG, rect, border_radius=4)
            pygame.draw.rect(surface, self.CARD_BORDER, rect, 1)
            self._blit_text(surface, str(value), (rect.x + 12, rect.y + 10), font=self.font_small, color=self.BG_COLOR)
            buttons.append((value, rect))
        self.prediction_buttons = buttons

    def _draw_round_overlay(self, surface: pygame.Surface) -> None:
        overlay = pygame.Surface(surface.get_size(), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 160))
        surface.blit(overlay, (0, 0))

        panel = pygame.Rect(54, 44, surface.get_width() - 108, surface.get_height() - 108)
        pygame.draw.rect(surface, self.PANEL_COLOR, panel, border_radius=8)
        pygame.draw.rect(surface, self.CARD_BORDER, panel, 2)

        title = "Fin de la partida" if self.state.current_phase == GamePhase.GAME_OVER else "Fin de la ronda"
        self._blit_text(surface, title, (panel.x + 18, panel.y + 16), font=self.font, color=self.ACCENT)

        y = panel.y + 70
        latest_summary = self.state.round_stats[-1] if self.state.round_stats else {}
        for player in self._get_scoreboard_players():
            round_delta = latest_summary.get(player.name, {}).get("pts", 0)
            delta_text = f"+{round_delta}" if round_delta > 0 else str(round_delta)
            text = (
                f"{player.name}: total {player.score} pts | ronda {delta_text} pts"
                f" | Bazas {player.tricks_won} | Pred {player.prediction or 0}"
            )
            self._blit_text(surface, text, (panel.x + 18, y), font=self.font_small)
            y += 30

        if self.state.current_phase == GamePhase.GAME_OVER:
            menu_button = pygame.Rect(panel.x + 18, panel.bottom - 62, 220, 38)
            exit_button = pygame.Rect(panel.x + 254, panel.bottom - 62, 220, 38)
            pygame.draw.rect(surface, self.PANEL_ALT, menu_button, border_radius=8)
            pygame.draw.rect(surface, self.ACCENT, menu_button, 2, border_radius=8)
            pygame.draw.rect(surface, self.PANEL_ALT, exit_button, border_radius=8)
            pygame.draw.rect(surface, self.ACCENT, exit_button, 2, border_radius=8)
            self._blit_text(surface, "Menú principal", (menu_button.x + 22, menu_button.y + 9), font=self.font_tiny, color=self.TEXT_COLOR)
            self._blit_text(surface, "Salir del juego", (exit_button.x + 28, exit_button.y + 9), font=self.font_tiny, color=self.TEXT_COLOR)
            self.game_over_menu_buttons = {
                "menu": menu_button,
                "exit": exit_button,
            }
        else:
            prompt = "Click o Espacio para continuar"
            self._blit_text(surface, prompt, (panel.x + 18, panel.bottom - 28), font=self.font_small, color=self.TEXT_DIM)

    def _draw_round_intro_overlay(self, surface: pygame.Surface) -> None:
        overlay = pygame.Surface(surface.get_size(), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 150))
        surface.blit(overlay, (0, 0))

        panel = pygame.Rect(surface.get_width() // 2 - 220, surface.get_height() // 2 - 80, 440, 160)
        pygame.draw.rect(surface, self.PANEL_COLOR, panel, border_radius=10)
        pygame.draw.rect(surface, self.ACCENT, panel, 2, border_radius=10)
        self._blit_text(surface, "RONDA DE PUNTOS DOBLES", (panel.x + 28, panel.y + 28), font=self.font_small, color=self.ACCENT)
        self._blit_text(surface, "Todas las puntuaciones valen el doble.", (panel.x + 28, panel.y + 68), font=self.font_tiny, color=self.TEXT_COLOR)
        self._blit_text(surface, "Click o Enter para continuar", (panel.x + 28, panel.y + 106), font=self.font_tiny, color=self.TEXT_DIM)

    def _draw_info(self, surface: pygame.Surface) -> None:
        info_panel = pygame.Rect(0, surface.get_height() - self.INFO_HEIGHT, surface.get_width(), self.INFO_HEIGHT)
        pygame.draw.rect(surface, self.PANEL_ALT, info_panel)
        msg = self.info_message or ""
        self._blit_text(surface, msg, (14, info_panel.y + 7), font=self.font_small, color=self.TEXT_COLOR)

    def _scroll_scoreboard(self, amount: float) -> None:
        self.scoreboard_scroll = max(0, self.scoreboard_scroll + amount)

    def _draw_card(
        self,
        surface: pygame.Surface,
        card: str,
        position: Tuple[int, int],
        *,
        selected: bool = False,
        small: bool = False,
        compact: bool = False,
        scale_override: Optional[float] = None,
    ) -> pygame.Rect:
        scale = scale_override if scale_override is not None else 1.0
        if scale_override is None:
            if small:
                scale = 0.7
            elif compact:
                scale = 0.86
        width = int(self.CARD_WIDTH * scale)
        height = int(self.CARD_HEIGHT * scale)
        rect = pygame.Rect(position[0], position[1], width, height)
        bg_color = self.CARD_BG_SELECTED if selected else self.CARD_BG
        border_radius = 8 if not small else 6
        pygame.draw.rect(surface, bg_color, rect, border_radius=border_radius)
        pygame.draw.rect(surface, self.CARD_BORDER, rect, 1, border_radius=border_radius)

        rank = card[:-1]
        suit = card[-1]
        text_color = pygame.Color(200, 60, 70) if suit in ("♥", "♦") else pygame.Color(32, 32, 40)
        font = self.font_small if scale >= 0.95 else self.font_tiny
        self._blit_text(surface, rank, (rect.x + 6, rect.y + 6), font=font, color=text_color)

        suit_size = 28 if scale >= 0.95 else max(16, int(26 * scale))
        suit_x = rect.centerx - suit_size // 2
        suit_y = rect.y + rect.height // 2 - suit_size // 2 + (6 if scale >= 0.95 else 4)
        self._draw_suit(surface, suit, (suit_x, suit_y), suit_size)
        return rect

    def _draw_suit(self, surface: pygame.Surface, suit: str, position: Tuple[int, int], size: int) -> None:
        suit_surface = self._get_scaled_suit_surface(suit, size)
        if suit_surface is None:
            return
        surface.blit(suit_surface, position)

    def _get_scaled_suit_surface(self, suit: str, size: int) -> Optional[pygame.Surface]:
        key = (suit, size)
        cached = self.suit_scale_cache.get(key)
        if cached is not None:
            return cached

        base_surface = self.suit_surfaces.get(suit)
        if base_surface is None:
            return None

        scaled = pygame.transform.smoothscale(base_surface, (size, size))
        self.suit_scale_cache[key] = scaled
        return scaled

    def _format_card_name(self, card: str) -> str:
        if not card:
            return ""
        rank = card[:-1]
        suit = card[-1]
        rank_name = {
            "J": "J",
            "Q": "Q",
            "K": "K",
            "A": "A",
        }.get(rank, rank)
        suit_name = {
            "♣": "trébol",
            "♦": "diamante",
            "♥": "corazón",
            "♠": "pica",
        }.get(suit, suit)
        return f"{rank_name} de {suit_name}"

    def _format_card_play_message(self, player_name: str, card: str) -> str:
        return f"{player_name} jugó {self._format_card_name(card)}"

    def _is_double_points_round(self) -> bool:
        if not self.state:
            return False
        round_no = self.state.round_index + 1
        return round_no > self.state.total_round_count - 3

    def _get_scoreboard_players(self) -> List[PlayerState]:
        if not self.state:
            return []
        round_order = self.state.round_order or [player.name for player in self.state.players]
        round_order_index = {name: index for index, name in enumerate(round_order)}
        return sorted(
            self.state.players,
            key=lambda player: (
                -player.score,
                -player.tricks_won,
                player.prediction if player.prediction is not None else 99,
                round_order_index.get(player.name, 999),
            ),
        )

    def _blit_text(
        self,
        surface: pygame.Surface,
        text: str,
        position: Tuple[int, int],
        *,
        font: Optional[pygame.font.Font] = None,
        color: Optional[pygame.Color] = None,
    ) -> None:
        font = font or self.font
        color = color or self.TEXT_COLOR
        rendered = font.render(text, False, color)
        surface.blit(rendered, (int(position[0]), int(position[1])))
