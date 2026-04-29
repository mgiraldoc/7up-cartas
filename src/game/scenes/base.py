from __future__ import annotations

import pygame


class Scene:
    def __init__(self, app: "GameApp") -> None:
        self.app = app

    def on_enter(self) -> None:
        """Called when the scene becomes active."""

    def on_exit(self) -> None:
        """Called when the scene is popped."""

    def handle_event(self, event: pygame.event.Event) -> None:
        """Handle a single pygame event."""

    def update(self, dt: float) -> None:
        """Update scene logic with delta time in seconds."""

    def draw(self, surface: pygame.Surface) -> None:
        """Draw the scene into the provided surface."""
