from __future__ import annotations

import asyncio
import sys
from dataclasses import dataclass
from typing import Optional, Type

import pygame

from .scenes.base import Scene


@dataclass
class AppConfig:
    human_name: str = "Mateo"
    bot_count: int = 2
    width: int = 800
    height: int = 450
    scale: int = 1
    server_url: str = "ws://127.0.0.1:8765"
    online_mode: str = "local"
    room_code: str = ""


class SceneManager:
    def __init__(self, app: "GameApp") -> None:
        self.app = app
        self.current: Optional[Scene] = None

    def set_scene(self, scene_cls: Type[Scene]) -> Scene:
        if self.current:
            self.current.on_exit()
        scene = scene_cls(self.app)
        self.current = scene
        scene.on_enter()
        return scene


class GameApp:
    def __init__(self, config: Optional[AppConfig] = None) -> None:
        pygame.init()
        pygame.display.set_caption("7UP - Cartas")
        self.config = config or AppConfig()
        self.logical_size = pygame.Vector2(self.config.width, self.config.height)
        self.scale = max(1, self.config.scale)
        self.screen = pygame.display.set_mode(
            (int(self.logical_size.x) * self.scale, int(self.logical_size.y) * self.scale)
        )
        self.surface = pygame.Surface(self.logical_size, flags=pygame.SRCALPHA).convert_alpha()
        self.clock = pygame.time.Clock()
        self.manager = SceneManager(self)
        self.running = True
        self.online_client = None
        self.online_state_snapshot = None

    def run(self, initial_scene: Type[Scene]) -> None:
        self.manager.set_scene(initial_scene)
        while self.running:
            self.tick()

        pygame.quit()
        sys.exit(0)

    async def run_async(self, initial_scene: Type[Scene]) -> None:
        self.manager.set_scene(initial_scene)
        while self.running:
            self.tick()
            await asyncio.sleep(0)

    def tick(self) -> None:
        dt = self.clock.tick(60) / 1000.0
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
            elif event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                self.running = False
            else:
                if self.manager.current:
                    self.manager.current.handle_event(event)

        if not self.running:
            return

        if self.manager.current:
            self.manager.current.update(dt)
            self.manager.current.draw(self.surface)

        scaled = pygame.transform.scale(
            self.surface, (int(self.logical_size.x) * self.scale, int(self.logical_size.y) * self.scale)
        )
        self.screen.blit(scaled, (0, 0))
        pygame.display.flip()
