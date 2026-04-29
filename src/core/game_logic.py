from __future__ import annotations

import random
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Dict, List, Optional

# Rangos y valores
RANKS = [str(n) for n in range(2, 11)] + ["J", "Q", "K", "A"]
RANK_VALUE = {r: i + 2 for i, r in enumerate(RANKS)}

SUITS = ["♠", "♥", "♦", "♣"]

SUIT_MAP = {
    "P": "♠",
    "S": "♠",
    "♠": "♠",
    "C": "♥",
    "H": "♥",
    "♥": "♥",
    "D": "♦",
    "♦": "♦",
    "T": "♣",
    "♣": "♣",
}

BOT_NAME_POOL = [
    "Luna",
    "Max",
    "Chloe",
    "Diego",
    "Sofia",
    "Leo",
    "Val",
    "Nico",
    "Paz",
    "Rafa",
    "Iris",
    "Mate",
    "Eva",
    "Gus",
    "Mika",
    "Rin",
]


def normalize_card(card_str: str) -> str:
    s = card_str.strip().upper()
    if len(s) < 2:
        return s
    rank, suit_char = s[:-1], s[-1]
    if rank not in RANKS:
        return card_str
    suit = SUIT_MAP.get(suit_char)
    return (rank + suit) if suit else card_str


def create_deck() -> List[str]:
    return [rank + suit for suit in SUITS for rank in RANKS]


def sort_hand(hand: List[str]) -> List[str]:
    suit_order = {suit: idx for idx, suit in enumerate(SUITS)}
    return sorted(hand, key=lambda c: (suit_order[c[-1]], RANK_VALUE[c[:-1]]))


def deal_cards(players: List[str], cards_per_player: int) -> tuple[Dict[str, List[str]], str]:
    deck = create_deck()
    random.shuffle(deck)
    hands = {}
    for index, player in enumerate(players):
        start = index * cards_per_player
        end = start + cards_per_player
        hands[player] = sort_hand(deck[start:end])
    trump = deck[len(players) * cards_per_player]
    return hands, trump


def can_follow_suit(hand: List[str], card: str, lead_suit: Optional[str]) -> bool:
    if lead_suit is None:
        return True
    if any(c[-1] == lead_suit for c in hand):
        return card[-1] == lead_suit
    return True


def determine_trick_winner(trick_cards: Dict[str, str], lead_suit: Optional[str], trump_suit: str) -> str:
    trump_set = {p: c for p, c in trick_cards.items() if c[-1] == trump_suit}
    if trump_set:
        return max(trump_set.items(), key=lambda x: RANK_VALUE[x[1][:-1]])[0]

    if lead_suit:
        lead_set = {p: c for p, c in trick_cards.items() if c[-1] == lead_suit}
        if lead_set:
            return max(lead_set.items(), key=lambda x: RANK_VALUE[x[1][:-1]])[0]

    return max(trick_cards.items(), key=lambda x: RANK_VALUE[x[1][:-1]])[0]


def calculate_score(prediction: int, actual: int, round_no: int, total_round_count: int) -> int:
    if actual == prediction:
        pts = 10 + 5 * actual
    else:
        pts = -5 * abs(actual - prediction)
    if round_no > total_round_count - 3:
        pts *= 2
    return pts


def ai_predict_hand(hand: List[str], trump_suit: str) -> int:
    trump_count = sum(1 for c in hand if c[-1] == trump_suit)
    high_non_trump = sum(
        1 for c in hand if c[-1] != trump_suit and RANK_VALUE[c[:-1]] >= 11
    )
    return trump_count + high_non_trump


def ai_play_card(hand: List[str], trick_cards: Dict[str, str], lead_suit: Optional[str], trump_suit: str) -> str:
    playable = hand[:]

    def value(card: str) -> int:
        return RANK_VALUE[card[:-1]]

    lead_cards = [c for c in trick_cards.values() if lead_suit and c[-1] == lead_suit]
    current_high_lead = max((value(c) for c in lead_cards), default=-1)

    trump_cards = [c for c in trick_cards.values() if c[-1] == trump_suit]
    current_high_trump = max((value(c) for c in trump_cards), default=-1)

    lead_candidates = [
        c for c in playable if lead_suit and c[-1] == lead_suit and value(c) > current_high_lead
    ]
    trump_candidates = [
        c for c in playable if c[-1] == trump_suit and value(c) > current_high_trump
    ]

    if lead_candidates:
        return min(lead_candidates, key=value)
    if trump_candidates:
        return min(trump_candidates, key=value)

    follow_cards = [c for c in playable if lead_suit and c[-1] == lead_suit]
    if follow_cards:
        return min(follow_cards, key=value)

    return min(playable, key=value)


def compute_round_sequence(num_players: int) -> List[int]:
    max_cards = min(7, 52 // num_players)
    if max_cards <= 0:
        raise ValueError("No es posible repartir cartas con la configuración actual.")
    ascending = list(range(1, max_cards))
    descending = list(range(max_cards - 1, 0, -1)) if max_cards > 1 else []
    return ascending + [max_cards, max_cards] + descending


@dataclass
class PlayerState:
    name: str
    is_human: bool
    hand: List[str] = field(default_factory=list)
    prediction: Optional[int] = None
    tricks_won: int = 0
    score: int = 0


class GamePhase(Enum):
    HUMAN_PREDICTION = auto()
    AI_PREDICTIONS = auto()
    PLAY_TRICK = auto()
    TRICK_RESOLUTION = auto()
    ROUND_END = auto()
    GAME_OVER = auto()


class CardGameState:
    def __init__(self, human_name: str | List[str], bot_names: List[str]) -> None:
        human_names = [human_name] if isinstance(human_name, str) else list(human_name)
        human_name_set = set(human_names)
        all_names = human_names + bot_names
        self.players: List[PlayerState] = [
            PlayerState(name=name, is_human=(name in human_name_set))
            for name in all_names
        ]
        self.player_lookup: Dict[str, PlayerState] = {p.name: p for p in self.players}
        self.round_sequence = compute_round_sequence(len(self.players))
        self.total_round_count = len(self.round_sequence)
        self.round_index = -1
        self.round_stats: List[Dict[str, Dict[str, int]]] = []
        self.round_labels: List[int] = []

        self.trump_card: Optional[str] = None
        self.trump_suit: Optional[str] = None
        self.round_order: List[str] = []
        self.turn_order: List[str] = []
        self.prediction_order: List[str] = []
        self.prediction_index: int = 0
        self.active_player_index: int = 0
        self.current_trick_cards: Dict[str, str] = {}
        self.lead_suit: Optional[str] = None
        self.current_phase = GamePhase.HUMAN_PREDICTION
        self.cards_per_player: int = 0
        self.trick_number: int = 0
        self.last_trick_winner: Optional[str] = None

        self.start_next_round()

    @property
    def current_player(self) -> PlayerState:
        name = self.turn_order[self.active_player_index]
        return self.player_lookup[name]

    def get_human_player(self) -> PlayerState:
        for player in self.players:
            if player.is_human:
                return player
        return self.players[0]

    def get_player(self, player_name: str) -> Optional[PlayerState]:
        return self.player_lookup.get(player_name)

    def start_next_round(self) -> None:
        self.round_index += 1
        if self.round_index >= len(self.round_sequence):
            self.current_phase = GamePhase.GAME_OVER
            return

        self.cards_per_player = self.round_sequence[self.round_index]
        self.round_labels.append(self.cards_per_player)

        player_names = [p.name for p in self.players]
        hands, trump_card = deal_cards(player_names, self.cards_per_player)

        for player in self.players:
            player.hand = hands[player.name]
            player.prediction = None
            player.tricks_won = 0

        self.trump_card = trump_card
        self.trump_suit = trump_card[-1]
        self.trick_number = 0
        self.current_trick_cards = {}
        self.lead_suit = None
        self.last_trick_winner = None

        start_index = self.round_index % len(self.players)
        self.round_order = player_names[start_index:] + player_names[:start_index]
        self.turn_order = self.round_order[:]
        self.active_player_index = 0

        self.prediction_order = self.round_order[:]
        self.prediction_index = 0

        self.current_phase = GamePhase.AI_PREDICTIONS
        self._advance_prediction_phase()

    def _advance_prediction_phase(self) -> None:
        while self.prediction_index < len(self.prediction_order):
            player_name = self.prediction_order[self.prediction_index]
            player = self.player_lookup[player_name]
            if player.is_human:
                self.current_phase = GamePhase.HUMAN_PREDICTION
                return

            prediction = min(
                self.cards_per_player,
                max(0, ai_predict_hand(player.hand, self.trump_suit or "")),
            )
            player.prediction = prediction
            self.prediction_index += 1

        self._start_trick_phase()

    def set_human_prediction(self, value: int) -> None:
        if self.current_phase != GamePhase.HUMAN_PREDICTION:
            return
        current_name = self.prediction_order[self.prediction_index]
        self.set_player_prediction(current_name, value)

    def set_player_prediction(self, player_name: str, value: int) -> bool:
        if self.current_phase != GamePhase.HUMAN_PREDICTION:
            return False
        if self.prediction_index >= len(self.prediction_order):
            return False
        expected_name = self.prediction_order[self.prediction_index]
        if player_name != expected_name:
            return False
        player = self.player_lookup[player_name]
        if not player.is_human:
            return False
        player.prediction = min(self.cards_per_player, max(0, value))
        self.prediction_index += 1
        self.current_phase = GamePhase.AI_PREDICTIONS
        self._advance_prediction_phase()
        return True

    def _start_trick_phase(self) -> None:
        self.current_phase = GamePhase.PLAY_TRICK
        self.turn_order = self.round_order[:]
        self.active_player_index = 0
        self.current_trick_cards = {}
        self.lead_suit = None

    def play_human_card(self, card: str) -> bool:
        if self.current_phase != GamePhase.PLAY_TRICK:
            return False
        player = self.current_player
        return self.play_player_card(player.name, card)

    def play_player_card(self, player_name: str, card: str) -> bool:
        if self.current_phase != GamePhase.PLAY_TRICK:
            return False
        player = self.current_player
        if not player.is_human or player.name != player_name or card not in player.hand:
            return False
        if not can_follow_suit(player.hand, card, self.lead_suit):
            return False
        self._commit_card(player, card)
        return True

    def play_ai_card(self) -> Optional[str]:
        if self.current_phase != GamePhase.PLAY_TRICK:
            return None
        player = self.current_player
        if player.is_human:
            return None
        card = ai_play_card(player.hand, self.current_trick_cards, self.lead_suit, self.trump_suit or "")
        self._commit_card(player, card)
        return card

    def _commit_card(self, player: PlayerState, card: str) -> None:
        player.hand.remove(card)
        self.current_trick_cards[player.name] = card
        if self.lead_suit is None:
            self.lead_suit = card[-1]

        if len(self.current_trick_cards) == len(self.players):
            self._resolve_trick()
        else:
            self.active_player_index = (self.active_player_index + 1) % len(self.turn_order)

    def _resolve_trick(self) -> None:
        winner_name = determine_trick_winner(self.current_trick_cards, self.lead_suit, self.trump_suit or "")
        winner = self.player_lookup[winner_name]
        winner.tricks_won += 1
        self.last_trick_winner = winner_name
        self.trick_number += 1
        self.round_order = self._rotate_to(self.round_order, winner_name)
        self.turn_order = self.round_order[:]
        self.active_player_index = 0
        self.current_phase = GamePhase.TRICK_RESOLUTION

    def advance_after_trick(self) -> None:
        if self.current_phase != GamePhase.TRICK_RESOLUTION:
            return
        if self.trick_number >= self.cards_per_player:
            self._finalize_round()
            return
        self.current_trick_cards = {}
        self.lead_suit = None
        self.current_phase = GamePhase.PLAY_TRICK

    def _finalize_round(self) -> None:
        summary: Dict[str, Dict[str, int]] = {}
        round_no = self.round_index + 1
        for player in self.players:
            prediction = player.prediction or 0
            actual = player.tricks_won
            pts = calculate_score(prediction, actual, round_no, self.total_round_count)
            player.score += pts
            summary[player.name] = {
                "pred": prediction,
                "made": actual,
                "pts": pts,
            }
        self.round_stats.append(summary)
        self.current_phase = GamePhase.ROUND_END

    def proceed_after_round(self) -> None:
        if self.current_phase != GamePhase.ROUND_END:
            return
        if self.round_index + 1 >= len(self.round_sequence):
            self.current_phase = GamePhase.GAME_OVER
            return
        self.start_next_round()

    def _rotate_to(self, order: List[str], leader: str) -> List[str]:
        idx = order.index(leader)
        return order[idx:] + order[:idx]

    def is_game_over(self) -> bool:
        return self.current_phase == GamePhase.GAME_OVER

    def advance_automatic(self, max_steps: int = 64) -> None:
        steps = 0
        while steps < max_steps:
            steps += 1
            if self.current_phase == GamePhase.AI_PREDICTIONS:
                self._advance_prediction_phase()
                continue
            if self.current_phase == GamePhase.PLAY_TRICK and not self.current_player.is_human:
                self.play_ai_card()
                continue
            break

    def to_snapshot(self, viewer_name: Optional[str] = None) -> Dict[str, Any]:
        players: List[Dict[str, Any]] = []
        ordered_players = self.players[:]
        if viewer_name:
            ordered_players.sort(key=lambda player: 0 if player.name == viewer_name else 1)
        for player in ordered_players:
            is_viewer = viewer_name is not None and player.name == viewer_name
            visible_hand = player.hand[:] if viewer_name is None or is_viewer else ["?"] * len(player.hand)
            players.append(
                {
                    "name": player.name,
                    "is_human": player.is_human if viewer_name is None else is_viewer,
                    "hand": visible_hand,
                    "prediction": player.prediction,
                    "tricks_won": player.tricks_won,
                    "score": player.score,
                }
            )

        return {
            "players": players,
            "round_sequence": self.round_sequence[:],
            "total_round_count": self.total_round_count,
            "round_index": self.round_index,
            "round_stats": self.round_stats[:],
            "round_labels": self.round_labels[:],
            "trump_card": self.trump_card,
            "trump_suit": self.trump_suit,
            "round_order": self.round_order[:],
            "turn_order": self.turn_order[:],
            "prediction_order": self.prediction_order[:],
            "prediction_index": self.prediction_index,
            "active_player_index": self.active_player_index,
            "current_trick_cards": dict(self.current_trick_cards),
            "lead_suit": self.lead_suit,
            "current_phase": self.current_phase.name,
            "cards_per_player": self.cards_per_player,
            "trick_number": self.trick_number,
            "last_trick_winner": self.last_trick_winner,
        }

    @classmethod
    def from_snapshot(cls, snapshot: Dict[str, Any]) -> "CardGameState":
        state = cls.__new__(cls)
        state.players = [
            PlayerState(
                name=player["name"],
                is_human=bool(player.get("is_human")),
                hand=list(player.get("hand", [])),
                prediction=player.get("prediction"),
                tricks_won=int(player.get("tricks_won", 0)),
                score=int(player.get("score", 0)),
            )
            for player in snapshot.get("players", [])
        ]
        state.player_lookup = {p.name: p for p in state.players}
        state.round_sequence = list(snapshot.get("round_sequence", []))
        state.total_round_count = int(snapshot.get("total_round_count", len(state.round_sequence)))
        state.round_index = int(snapshot.get("round_index", -1))
        state.round_stats = list(snapshot.get("round_stats", []))
        state.round_labels = list(snapshot.get("round_labels", []))
        state.trump_card = snapshot.get("trump_card")
        state.trump_suit = snapshot.get("trump_suit")
        state.round_order = list(snapshot.get("round_order", []))
        state.turn_order = list(snapshot.get("turn_order", []))
        state.prediction_order = list(snapshot.get("prediction_order", []))
        state.prediction_index = int(snapshot.get("prediction_index", 0))
        state.active_player_index = int(snapshot.get("active_player_index", 0))
        state.current_trick_cards = dict(snapshot.get("current_trick_cards", {}))
        state.lead_suit = snapshot.get("lead_suit")
        phase_name = snapshot.get("current_phase", GamePhase.HUMAN_PREDICTION.name)
        state.current_phase = GamePhase[phase_name]
        state.cards_per_player = int(snapshot.get("cards_per_player", 0))
        state.trick_number = int(snapshot.get("trick_number", 0))
        state.last_trick_winner = snapshot.get("last_trick_winner")
        return state
