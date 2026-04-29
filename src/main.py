from __future__ import annotations

import argparse
import sys


def main() -> None:
    parser = argparse.ArgumentParser(description="Cliente pygame para 7UP - Cartas.")
    parser.add_argument("--human", default="Mateo", help="Nombre del jugador humano.")
    parser.add_argument("--bots", type=int, default=2, help="Cantidad de bots a enfrentar (1-6).")
    parser.add_argument("--width", type=int, default=960, help="Ancho lógico del lienzo (px).")
    parser.add_argument("--height", type=int, default=540, help="Alto lógico del lienzo (px).")
    parser.add_argument("--scale", type=int, default=2, help="Factor de escala entero para pixel art.")
    parser.add_argument("--server", default="ws://127.0.0.1:8765", help="URL websocket del servidor online.")
    args = parser.parse_args()

    try:
        import pygame  # noqa: F401  # trigger import to check availability
    except ImportError as exc:  # pragma: no cover - difícil de testear
        print("Necesitas instalar pygame-ce para ejecutar la versión gráfica.")
        print("Sugerencia: pip install pygame-ce")
        raise SystemExit(1) from exc

    from src.game.app import AppConfig, GameApp
    from src.game.scenes.menu_scene import MenuScene

    bot_count = max(1, min(6, args.bots))
    width = max(840, args.width)
    height = max(472, args.height)
    scale = max(1, args.scale)
    config = AppConfig(
        human_name=args.human,
        bot_count=bot_count,
        width=width,
        height=height,
        scale=scale,
        server_url=args.server,
    )
    app = GameApp(config)
    app.run(MenuScene)


if __name__ == "__main__":
    main()
