import argparse
import random
import sys
import time
import unittest

from src.core.game_logic import (
    BOT_NAME_POOL,
    RANKS,
    RANK_VALUE,
    SUIT_MAP,
    ai_play_card,
    ai_predict_hand,
    calculate_score,
    can_follow_suit,
    deal_cards,
    determine_trick_winner,
    normalize_card,
    compute_round_sequence,
)

# --- Colores ANSI ---
RESET = "\033[0m"
BOLD = "\033[1m"
TITLE_COLOR = "\033[36m"
RED = "\033[31m"
TRIUMPH_COLOR = "\033[33m"
TRICK_WIN_COLOR = "\033[36m"
SUIT_COLORS = {
    "♠": "",
    "♣": "",
    "♥": RED,
    "♦": RED,
}

# Mapeo inicial<->símbolo
PLAYER_COLORS: dict[str, str] = {}
PLAYER_COLOR_CYCLE = [
    "\033[35m",
    "\033[32m",
    "\033[34m",
    "\033[90m",
    "\033[95m",
    "\033[92m",
    "\033[96m",
    "\033[91m",
]


def color_card(card: str) -> str:
    """Aplica color al símbolo de la pinta de la carta."""
    rank, suit = card[:-1], card[-1]
    return f"{SUIT_COLORS.get(suit, '')}{rank}{suit}{RESET}"


def print_cards(cards: list[str]) -> None:
    """Dibuja una lista de cartas en ASCII art, coloreando el palo."""
    lines = [""] * 5
    for card in cards:
        rank, suit = card[:-1], card[-1]
        r = rank.ljust(2)
        colored_suit = f"{SUIT_COLORS.get(suit, '')}{suit}{RESET}"
        art = [
            "┌─────┐",
            f"│{r}   │",
            f"│  {colored_suit}  │",
            f"│   {r}│",
            "└─────┘",
        ]
        for i in range(5):
            lines[i] += art[i] + "  "
    for row in lines:
        print(row)


def color_player(name: str) -> str:
    """Devuelve el nombre del jugador en negrita y color asignado."""
    return f"{BOLD}{PLAYER_COLORS.get(name, '')}{name}{RESET}"


def assign_player_colors(players: list[str]) -> None:
    for idx, player in enumerate(players):
        PLAYER_COLORS[player] = PLAYER_COLOR_CYCLE[idx % len(PLAYER_COLOR_CYCLE)]


def print_stats_table(round_stats: list[dict[str, dict[str, int]]], players: list[str], round_labels: list[int]) -> None:
    if not round_stats:
        return

    header1 = ["Cartas"]
    for p in players:
        header1 += [p, "", ""]
    header2 = [""] + ["Pred", "Hechas", "Pts"] * len(players)

    col_width = 9

    def fmt(text: str) -> str:
        return text.center(col_width)

    separator = "-" * ((col_width + 3) * len(header1) - 3)
    print("\n" + " | ".join(fmt(x) for x in header1))
    print(separator)
    print(" | ".join(fmt(x) for x in header2))
    print(separator)
    totals = {p: {"pred": 0, "made": 0, "pts": 0} for p in players}
    for idx, stats in enumerate(round_stats, start=1):
        label = round_labels[idx - 1] if idx - 1 < len(round_labels) else idx
        row = [str(label)]
        for p in players:
            data = stats.get(p, {"pred": 0, "made": 0, "pts": 0})
            totals[p]["pred"] += data["pred"]
            totals[p]["made"] += data["made"]
            totals[p]["pts"] += data["pts"]
            row += [str(data["pred"]), str(data["made"]), str(data["pts"])]
        print(" | ".join(fmt(x) for x in row))
    print(separator)
    total_row = ["Total"]
    for p in players:
        total_row += [
            str(totals[p]["pred"]),
            str(totals[p]["made"]),
            str(totals[p]["pts"]),
        ]
    print(" | ".join(fmt(x) for x in total_row))
    print()


def ask_int(prompt: str, minimum: int, maximum: int | None = None) -> int:
    while True:
        raw = input(prompt)
        if not raw.strip():
            print("  Ingresa un número.")
            continue
        if not raw.strip().isdigit():
            print("  Debe ser un número.")
            continue
        value = int(raw.strip())
        if value < minimum:
            print(f"  El mínimo es {minimum}.")
            continue
        if maximum is not None and value > maximum:
            print(f"  El máximo es {maximum}.")
            continue
        return value


def ask_prediction(player: str, max_tricks: int) -> int:
    return ask_int(f"{color_player(player)} predice cuántas bazas? ", 0, max_tricks)


def human_choose_card(hand: list[str], lead_suit: str | None) -> str:
    while True:
        raw = input("Elige una carta (ej. 10P, JH, q♦): ")
        card = normalize_card(raw)
        if card not in hand:
            print("  Esa carta no está en tu mano.")
            continue
        if not can_follow_suit(hand, card, lead_suit):
            print("  Debes seguir la pinta inicial.")
            continue
        return card


def play_round(
    round_no: int,
    cards_per_player: int,
    players: list[str],
    human: str,
    scores: dict[str, int],
    round_stats: list[dict[str, dict[str, int]]],
    total_round_count: int,
    round_labels: list[int],
) -> None:
    hands, trump_card = deal_cards(players, cards_per_player)
    trump_suit = trump_card[-1]
    print(f"\n{TITLE_COLOR}{BOLD}Ronda de {cards_per_player} carta(s){RESET}")
    print(f"Triunfo: {color_card(trump_card)}")

    start_index = (round_no - 1) % len(players)
    round_order = players[start_index:] + players[:start_index]

    predictions: dict[str, int] = {}
    for player in round_order:
        if player == human:
            print(f"\nTus cartas para predecir:")
            print_cards(hands[player])
            pred = ask_prediction(player, cards_per_player)
        else:
            pred = min(cards_per_player, max(0, ai_predict_hand(hands[player], trump_suit)))
            time.sleep(0.3)
            print(f"{color_player(player)} predice {pred} baza(s).")
        predictions[player] = pred

    input("\nPresiona Enter para comenzar las bazas...")

    order = round_order[:]
    results = {p: 0 for p in players}
    lead_index = 0

    for trick_no in range(1, cards_per_player + 1):
        print(f"\n{BOLD}Baza {trick_no}{RESET}")
        trick_cards: dict[str, str] = {}
        lead_suit: str | None = None

        for i in range(len(players)):
            player = order[(lead_index + i) % len(players)]
            current_hand = hands[player]
            if player == human:
                print(f"\n{color_player(player)}, tu mano:")
                print_cards(current_hand)
                card = human_choose_card(current_hand, lead_suit)
                print(f"\nHas jugado:")
                print_cards([card])
            else:
                card = ai_play_card(current_hand, trick_cards, lead_suit, trump_suit)
                print(f"\n{color_player(player)} juega:")
                print_cards([card])
                time.sleep(0.4)

            current_hand.remove(card)
            trick_cards[player] = card
            if lead_suit is None:
                lead_suit = card[-1]

        winner = determine_trick_winner(trick_cards, lead_suit, trump_suit)
        win_card = trick_cards[winner]
        results[winner] += 1
        lead_index = order.index(winner)
        print(
            f"{TRICK_WIN_COLOR}{color_player(winner)} gana la baza con {color_card(win_card)}{RESET}"
        )
        print(
            "Marcador de bazas: "
            + "  ".join(f"{color_player(p)}: {results[p]}" for p in order)
        )
        input("Presiona Enter para continuar...")

    round_summary: dict[str, dict[str, int]] = {}
    for player in players:
        pts = calculate_score(predictions[player], results[player], round_no, total_round_count)
        scores[player] += pts
        round_summary[player] = {"pred": predictions[player], "made": results[player], "pts": pts}
        color = TRIUMPH_COLOR if pts >= 0 else RED
        print(
            f"{color_player(player)} logró {results[player]} baza(s) (predijo {predictions[player]}). "
            f"Puntos de la ronda: {color}{pts}{RESET}  | Total: {scores[player]}"
        )

    round_stats.append(round_summary)
    round_labels.append(cards_per_player)
    print_stats_table(round_stats, players, round_labels)


def play_game() -> None:
    print(f"{TITLE_COLOR}{BOLD}¡Bienvenido a 7UP - Cartas!{RESET}")
    num_players = ask_int("¿Cuántos jugadores en total? (2-7) ", 2, 7)
    human = input("Escribe tu nombre: ").strip() or "Tú"

    bot_count = max(0, num_players - 1)
    available_names = [name for name in BOT_NAME_POOL if name.lower() != human.lower()]
    if bot_count > len(available_names):
        raise ValueError("No hay suficientes nombres para los bots.")
    bot_names = random.sample(available_names, k=bot_count)
    players = [human] + bot_names

    assign_player_colors(players)

    scores = {p: 0 for p in players}
    round_stats: list[dict[str, dict[str, int]]] = []
    round_labels: list[int] = []
    round_card_counts = compute_round_sequence(num_players)
    total_round_count = len(round_card_counts)

    try:
        for round_no, cards_per_player in enumerate(round_card_counts, start=1):
            play_round(
                round_no,
                cards_per_player,
                players,
                human,
                scores,
                round_stats,
                total_round_count,
                round_labels,
            )

    except KeyboardInterrupt:
        print("\nJuego interrumpido.")
        return

    print(f"\n{TITLE_COLOR}{BOLD}Puntuación final{RESET}")
    for player in players:
        print(f"{color_player(player)}: {scores[player]} puntos")

    winner = max(players, key=lambda p: scores[p])
    print(f"\n{TRIUMPH_COLOR}{color_player(winner)} gana la partida. ¡Felicidades!{RESET}")


class TestCardGame(unittest.TestCase):
    def test_normalize_card(self) -> None:
        self.assertEqual(normalize_card("9p"), "9♠")
        self.assertEqual(normalize_card("K♦"), "K♦")
        self.assertEqual(normalize_card("7x"), "7x")
        self.assertEqual(normalize_card("Jt"), "J♣")
        self.assertEqual(normalize_card("9♥"), "9♥")

    def test_ai_predict_hand(self) -> None:
        hand = ["A♠", "5♠", "J♥", "2♦"]
        self.assertEqual(ai_predict_hand(hand, "♠"), 3)

    def test_ai_play_card_lead(self) -> None:
        hand = ["2♣", "3♠", "K♦"]
        self.assertEqual(ai_play_card(hand, {}, None, "♥"), "2♣")

    def test_ai_play_card_follow_and_win(self) -> None:
        hand = ["8♣", "5♥", "7♦"]
        trick = {"X": "6♣"}
        self.assertEqual(ai_play_card(hand, trick, "♣", "♥"), "8♣")

    def test_ai_play_card_follow_low(self) -> None:
        hand = ["9♠", "5♦"]
        trick = {"X": "10♠"}
        self.assertEqual(ai_play_card(hand, trick, "♠", "♥"), "9♠")

    def test_ai_play_card_trump(self) -> None:
        hand = ["4♣", "7♥"]
        trick = {"X": "10♣"}
        self.assertEqual(ai_play_card(hand, trick, "♣", "♥"), "7♥")

    def test_calculate_score_hit(self) -> None:
        self.assertEqual(calculate_score(2, 2, 1, 7), 20)

    def test_calculate_score_miss(self) -> None:
        self.assertEqual(calculate_score(1, 0, 1, 7), -5)

    def test_determine_trick_winner_trump(self) -> None:
        trick = {"A": "2♦", "B": "8♣", "C": "K♦"}
        self.assertEqual(determine_trick_winner(trick, "♦", "♣"), "B")

    def test_calculate_score_double_round(self) -> None:
        self.assertEqual(calculate_score(1, 1, 12, 14), 30)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--test", action="store_true", help="Ejecuta los tests en lugar del juego interactivo.")
    return parser.parse_args(argv)


def main() -> None:
    args = parse_args(sys.argv[1:])
    if args.test:
        unittest.main(argv=[sys.argv[0]], exit=False)
    else:
        play_game()


if __name__ == "__main__":
    main()
