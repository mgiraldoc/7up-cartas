from __future__ import annotations

from pathlib import Path

import pygame


FONT_PATH = (
    Path(__file__).resolve().parents[2]
    / "assets"
    / "fonts"
    / "LowresPixel-Regular.otf"
)

SUIT_ASSET_DIR = (
    Path(__file__).resolve().parents[2]
    / "assets"
    / "suits"
)


def load_font(size: int) -> pygame.font.Font:
    if FONT_PATH.exists():
        return pygame.font.Font(str(FONT_PATH), size)
    return pygame.font.Font(None, size)


def load_suit_surface(filename: str) -> pygame.Surface | None:
    path = SUIT_ASSET_DIR / filename
    if not path.exists():
        return None
    return pygame.image.load(str(path)).convert_alpha()
