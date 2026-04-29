from __future__ import annotations

import argparse
import sys
from urllib.parse import parse_qs


DEFAULT_SERVER = "ws://127.0.0.1:8765"


def _create_app_config(
    *,
    human_name: str,
    bot_count: int,
    width: int,
    height: int,
    scale: int,
    server_url: str,
):
    from src.game.app import AppConfig

    bot_count = max(1, min(6, bot_count))
    width = max(840, width)
    height = max(472, height)
    scale = max(1, scale)
    return AppConfig(
        human_name=human_name,
        bot_count=bot_count,
        width=width,
        height=height,
        scale=scale,
        server_url=server_url,
    )


def _browser_config():
    from platform import window

    params = parse_qs(str(window.location.search)[1:])
    server_url = params.get("server", [DEFAULT_SERVER])[0]
    human_name = params.get("name", ["Jugador"])[0]
    bots = int(params.get("bots", ["2"])[0])
    width = int(params.get("width", ["960"])[0])
    height = int(params.get("height", ["540"])[0])
    scale = int(params.get("scale", ["1"])[0])
    return _create_app_config(
        human_name=human_name,
        bot_count=bots,
        width=width,
        height=height,
        scale=scale,
        server_url=server_url,
    )


def _desktop_config(argv: list[str] | None = None):
    parser = argparse.ArgumentParser(description="Cliente pygame para 7UP - Cartas.")
    parser.add_argument("--human", default="Mateo", help="Nombre del jugador humano.")
    parser.add_argument("--bots", type=int, default=2, help="Cantidad de bots a enfrentar (1-6).")
    parser.add_argument("--width", type=int, default=960, help="Ancho lógico del lienzo (px).")
    parser.add_argument("--height", type=int, default=540, help="Alto lógico del lienzo (px).")
    parser.add_argument("--scale", type=int, default=2, help="Factor de escala entero para pixel art.")
    parser.add_argument("--server", default=DEFAULT_SERVER, help="URL websocket del servidor online.")
    args = parser.parse_args(argv)
    return _create_app_config(
        human_name=args.human,
        bot_count=args.bots,
        width=args.width,
        height=args.height,
        scale=args.scale,
        server_url=args.server,
    )


def _ensure_pygame() -> None:
    try:
        import pygame  # noqa: F401  # trigger import to check availability
    except ImportError as exc:  # pragma: no cover - difícil de testear
        print("Necesitas instalar pygame-ce para ejecutar la versión gráfica.")
        print("Sugerencia: pip install pygame-ce")
        raise SystemExit(1) from exc


def main() -> None:
    _ensure_pygame()
    from src.game.app import GameApp
    from src.game.scenes.menu_scene import MenuScene

    app = GameApp(_desktop_config())
    app.run(MenuScene)


async def main_async() -> None:
    _ensure_pygame()
    from src.game.app import GameApp
    from src.game.scenes.menu_scene import MenuScene

    config = _browser_config() if sys.platform == "emscripten" else _desktop_config()
    app = GameApp(config)
    await app.run_async(MenuScene)


if __name__ == "__main__":
    main()
