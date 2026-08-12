"""MTGNP turn and combat handler.

This file is the server's game-rule module.  It does not create or read TCP
sockets itself.  Instead, ``server.py`` gives it two simple functions: one to
send a message to one player and one to send a message to both players.  This
keeps the networking code separate from the game logic and makes the game
logic easier to test.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
import random
import threading
from typing import Callable

from shared import constants as c
from shared import messages, protocol

# The workbook defines 58 card bases
_CARD_ROWS = {
    # base: (type, mana cost, power, toughness, implemented effect)
    "mountain": ("Land", {}, None, None, "mana:R"),
    "forest": ("Land", {}, None, None, "mana:G"),
    "plains": ("Land", {}, None, None, "mana:W"),
    "island": ("Land", {}, None, None, "mana:U"),
    "swamp": ("Land", {}, None, None, "mana:B"),
    "lightning_bolt": ("Instant", {"R": 1}, None, None, "damage:any:3"),
    "shock": ("Instant", {"R": 1}, None, None, "damage:any:2"),
    "lava_spike": ("Sorcery", {"R": 1}, None, None, "damage:player:3"),
    "flame_slash": ("Sorcery", {"R": 1}, None, None, "damage:creature:4"),
    "searing_spear": ("Instant", {"R": 1, "X": 1}, None, None, "damage:any:3"),
    "skullcrack": ("Instant", {"R": 1, "X": 1}, None, None, "damage:any:3"),
    "rift_bolt": ("Sorcery", {"R": 1, "X": 2}, None, None, "damage:any:3"),
    "incinerate": ("Instant", {"R": 1, "X": 1}, None, None, "damage:any:3"),
    "goblin_guide": ("Creature", {"R": 1}, 2, 2, ""),
    "goblin_bushwhacker": ("Creature", {"R": 1}, 1, 1, ""),
    "reckless_wurm": ("Creature", {"R": 1, "X": 3}, 4, 4, ""),
    "monastery_swiftspear": ("Creature", {"R": 1}, 1, 2, "haste"),
    "counterspell": ("Instant", {"U": 2}, None, None, "counter"),
    "cancel": ("Instant", {"U": 2, "X": 1}, None, None, "counter"),
    "unsummon": ("Instant", {"U": 1}, None, None, "bounce"),
    "ponder": ("Sorcery", {"U": 1}, None, None, "draw:1"),
    "negate": ("Instant", {"U": 1, "X": 1}, None, None, "counter"),
    "mana_leak": ("Instant", {"U": 1, "X": 1}, None, None, "counter"),
    "merfolk_looter": ("Creature", {"U": 1, "X": 1}, 1, 1, ""),
    "prodigal_sorcerer": ("Creature", {"U": 1, "X": 2}, 1, 1, ""),
    "air_elemental": ("Creature", {"U": 2, "X": 3}, 4, 4, "flying"),
    "phantasmal_bear": ("Creature", {"U": 1}, 2, 2, ""),
    "giant_growth": ("Instant", {"G": 1}, None, None, "pump:3:3"),
    "rampant_growth": ("Sorcery", {"G": 1, "X": 1}, None, None, "ramp"),
    "naturalize": ("Instant", {"G": 1, "X": 1}, None, None, "destroy:artifact_enchantment"),
    "vines_of_vastwood": ("Instant", {"G": 1}, None, None, ""),
    "llanowar_elves": ("Creature", {"G": 1}, 1, 1, ""),
    "elvish_mystic": ("Creature", {"G": 1}, 1, 1, ""),
    "grizzly_bears": ("Creature", {"G": 1, "X": 1}, 2, 2, ""),
    "leatherback_baloth": ("Creature", {"G": 3}, 4, 5, ""),
    "troll_ascetic": ("Creature", {"G": 1, "X": 2}, 3, 2, ""),
    "wall_of_stone": ("Creature", {"R": 1, "X": 2}, 0, 8, ""),
    "swords_to_plowshares": ("Instant", {"W": 1}, None, None, "exile"),
    "path_to_exile": ("Instant", {"W": 1}, None, None, "exile"),
    "healing_salve": ("Instant", {"W": 1}, None, None, "heal:3"),
    "pacifism": ("Enchantment", {"W": 1, "X": 1}, None, None, ""),
    "white_knight": ("Creature", {"W": 2}, 2, 2, ""),
    "serra_angel": ("Creature", {"W": 2, "X": 3}, 4, 4, "flying"),
    "savannah_lions": ("Creature", {"W": 1}, 2, 1, ""),
    "mother_of_runes": ("Creature", {"W": 1}, 1, 1, ""),
    "dark_ritual": ("Instant", {"B": 1}, None, None, "mana:B:3"),
    "terror": ("Instant", {"B": 1, "X": 1}, None, None, "destroy:creature"),
    "doom_blade": ("Instant", {"B": 1, "X": 1}, None, None, "destroy:creature"),
    "raise_dead": ("Sorcery", {"B": 1}, None, None, "return"),
    "mind_rot": ("Sorcery", {"B": 1, "X": 2}, None, None, "discard:2"),
    "gray_merchant": ("Creature", {"B": 2, "X": 3}, 2, 4, ""),
    "gravedigger": ("Creature", {"B": 1, "X": 3}, 2, 2, ""),
    "royal_assassin": ("Creature", {"B": 1, "X": 2}, 1, 1, ""),
    "black_knight": ("Creature", {"B": 2}, 2, 2, ""),
    "sol_ring": ("Artifact", {"X": 1}, None, None, ""),
    "ornithopter": ("Artifact Creature", {}, 0, 2, "flying"),
    "millstone": ("Artifact", {"X": 2}, None, None, ""),
    "rod_of_ruin": ("Artifact", {"X": 4}, None, None, ""),
}
_COPIES = {"mountain": 20, "forest": 20, "plains": 20, "island": 20, "swamp": 20}


def card_base(card_id: str) -> str:
    """Return the workbook's card base for an instance such as ``shock_003``."""
    base, sep, suffix = card_id.rpartition("_")

    # Base IDs are also accepted so the server can work with a simpler client
    # card catalogue during development.
    return base if sep and suffix.isdigit() else card_id


def legal_card(card_id: str) -> bool:
    """Check whether a card ID exists in the restricted card list."""
    base = card_base(card_id)
    if base not in _CARD_ROWS:
        return False
    if "_" not in card_id:
        return True  # Supports clients that use base IDs from a JSON catalogue.
    suffix = card_id.rsplit("_", 1)[1]
    return suffix.isdigit() and 1 <= int(suffix) <= _COPIES.get(base, 4)


@dataclass
class PlayerState:
    """All private and public game data owned by one player."""
    player_id: str
    deck: list[str]
    library: list[str] = field(default_factory=list)
    hand: list[str] = field(default_factory=list)
    battlefield: list[dict] = field(default_factory=list)
    graveyard: list[str] = field(default_factory=list)
    life: int = c.STARTING_LIFE_TOTAL
    mulligans: int = 0
    kept: bool = False
    land_played: bool = False


class GameManager:
    def __init__(
        self,
        send_to: Callable[[str, dict], None],
        broadcast: Callable[[dict], None],
        *,
        rng: random.Random | None = None,
    ):
        # These callbacks are supplied by server.py.  Keeping them as
        # callbacks avoids mixing socket operations with game-rule decisions.
        self.send_to = send_to
        self.broadcast = broadcast
        self.rng = rng or random.Random()
        self.lock = threading.RLock()
        self.seq_num = 0
        self.reset_lobby()

    def reset_lobby(self) -> None:
        """Clear one finished game while keeping the TCP connections alive."""
        self.state = c.STATE_LOBBY
        self.players: dict[str, PlayerState] = {}
        self.ready_by_connection: dict[object, str] = {}
        self.active_player: str | None = None
        self.phase: str | None = None
        self.turn = 0
        self.priority_holder: str | None = None
        self.priority_token: int | None = None
        self.consecutive_passes = 0
        self.stack: list[dict] = []
        self.attackers: list[dict] = []
        self.blockers: list[dict] = []
        self.pending_damage_orders: set[str] = set()

    # ---- PDU emission and state projection ---------------------------------
    def _emit(self, pdu: dict, recipient: str | None = None) -> int:
        """Add the next server sequence number and send one complete PDU."""
        self.seq_num += 1
        message = {**pdu, "seq_num": self.seq_num}

        if recipient:
            self.send_to(recipient, message)
        else:
            self.broadcast(message)

        return self.seq_num

    def _error(self, player_id: str | None, code: str, message: str, rejected: dict | None = None) -> None:
        """Send an RFC ERROR PDU without changing the current game state."""
        if player_id:
            pdu = {"type": c.ERROR, "code": code, "message": message}
            if rejected is not None:
                pdu["rejected_action"] = rejected
            self._emit(pdu, player_id)

    def _error_connection(self, connection: object, code: str, message: str, rejected: dict | None = None) -> None:
        """Report an error before a connection has successfully claimed an ID."""
        if not hasattr(connection, "send"):
            return
        self.seq_num += 1
        pdu = {"type": c.ERROR, "seq_num": self.seq_num, "code": code, "message": message}
        if rejected is not None:
            pdu["rejected_action"] = rejected
        connection.send(pdu)

    def _visible_state(self, viewer: str) -> dict:
        """Build a state update while hiding the other player's hand."""
        def permanent(p: dict) -> dict:
            # Copy the dictionary so a client cannot change server-owned state.
            return dict(p)

        return {
            "turn": self.turn,
            "phase": self.phase or self.state,
            "active_player": self.active_player,
            "life_totals": {pid: p.life for pid, p in self.players.items()},
            "hand": list(self.players[viewer].hand) if viewer in self.players else [],
            "hand_counts": {
                pid: len(player.hand)
                for pid, player in self.players.items()
                if pid != viewer
            },
            "library_counts": {pid: len(p.library) for pid, p in self.players.items()},
            "battlefield": {
                pid: [permanent(card) for card in player.battlefield]
                for pid, player in self.players.items()
            },
            "graveyard": {pid: list(p.graveyard) for pid, p in self.players.items()},
            "stack": list(self.stack),
        }

    def _send_state(self, recipient: str | None = None) -> int | None:
        """Send a personalized GAME_STATE_UPDATE to one or both players."""
        if recipient:
            return self._emit({"type": c.GAME_STATE_UPDATE, "state": self._visible_state(recipient)}, recipient)
        for pid in list(self.players):
            self._emit({"type": c.GAME_STATE_UPDATE, "state": self._visible_state(pid)}, pid)
        return None

    def _broadcast_transition(self, to_phase: str) -> int:
        """Change the current phase and notify both clients."""
        before = self.phase or "LOBBY"
        self.phase = to_phase
        return self._emit(
            {
                "type": c.PHASE_TRANSITION,
                "from_phase": before,
                "to_phase": to_phase,
                "active_player": self.active_player,
                "turn": self.turn,
            }
        )

    def _grant_priority(self, player_id: str) -> None:
        """Give one player permission to act and save the required token."""
        self.priority_holder = player_id
        token = self._emit(
            {
                "type": c.PRIORITY_GRANT,
                "player_id": player_id,
                "time_limit_ms": c.DEFAULT_TIME_LIMIT_MS,
            },
            player_id,
        )
        self.priority_token = token

    def _opponent(self, player_id: str) -> str:
        return next(pid for pid in self.players if pid != player_id)

    # ---- inbound dispatch ----------------------------------------------------
    def receive(self, connection: object, raw: dict) -> str | None:
        """Validate and apply one client PDU.

        The network thread calls this method after it has received a full
        length-prefixed JSON message.  The lock is important because either
        client can send a PDU at almost the same time.
        """
        with self.lock:
            player_id = self.ready_by_connection.get(connection)
            try:
                protocol.validate_envelope(raw)
                pdu = messages.parse(raw)
            except protocol.ProtocolError as exc:
                if player_id:
                    self._error(player_id, exc.error_code, exc.message, getattr(exc, "rejected_action", raw))
                else:
                    self._error_connection(connection, exc.error_code, exc.message, getattr(exc, "rejected_action", raw))
                return None
            if isinstance(pdu, messages.PlayerReady):
                self._player_ready(connection, pdu, raw)
                return self.ready_by_connection.get(connection)
            if not player_id or player_id not in self.players:
                self._error(player_id, c.ERR_ILLEGAL_ACTION, "Send PLAYER_READY in the lobby first.", raw)
                return None
            if isinstance(pdu, messages.Ping):
                # PING has its own client counter, so it never uses a priority
                # token.  The timestamp lets the client match this PONG reply.
                self._emit({"type": c.PONG, "timestamp": pdu.timestamp, "seq_num": pdu.seq_num}, player_id)
                return None
            if isinstance(pdu, messages.Concede):
                if pdu.player_id != player_id:
                    self._error(player_id, c.ERR_ILLEGAL_ACTION, "CONCEDE player_id does not match sender.", raw)
                else:
                    self._game_over(self._opponent(player_id), player_id, c.REASON_CONCEDE)
                return None
                
            # Mulligan choices echo each player's personalized setup/redraw
            # update, rather than the shared priority token (RFC 5.4/6.4).
            if (
                not isinstance(pdu, messages.MulliganChoice)
                and not messages.is_seq_num_exempt(pdu.TYPE)
                and pdu.seq_num != self.priority_token
            ):
                self._error(
                    player_id,
                    c.ERR_STALE_ACTION,
                    f"Priority token mismatch: expected {self.priority_token}, got {pdu.seq_num}.",
                    raw,
                )
                if self.priority_holder:
                    self._grant_priority(self.priority_holder)
                return None
            self._dispatch_action(player_id, pdu, raw)
            return None

    def _player_ready(self, connection: object, pdu: messages.PlayerReady, raw: dict) -> None:
        """Register or replace one player's deck while in the lobby."""
        if self.state != c.STATE_LOBBY:
            self._error(
                self.ready_by_connection.get(connection),
                c.ERR_ILLEGAL_ACTION,
                "PLAYER_READY is accepted only in LOBBY.",
                raw,
            )
            return

        valid_size = c.MIN_DECK_SIZE <= len(pdu.deck_list) <= c.MAX_DECK_SIZE
        valid_cards = all(legal_card(card_id) for card_id in pdu.deck_list)
        if not valid_size or not valid_cards:
            previous = self.ready_by_connection.get(connection)
            if previous:
                self._error(previous, c.ERR_ILLEGAL_DECK, "Deck must contain 1-50 legal card instance IDs.", raw)
            else:
                self._error_connection(connection, c.ERR_ILLEGAL_DECK, "Deck must contain 1-50 legal card instance IDs.", raw)
            return
        previous = self.ready_by_connection.get(connection)
        if pdu.player_id in self.players and pdu.player_id != previous:
            if previous:
                self._error(previous, c.ERR_DUPLICATE_ID, "player_id is already claimed by the other player.", raw)
            else:
                self._error_connection(connection, c.ERR_DUPLICATE_ID, "player_id is already claimed by the other player.", raw)
            return
        if previous and previous != pdu.player_id:
            self.players.pop(previous, None)
        self.ready_by_connection[connection] = pdu.player_id
        self.players[pdu.player_id] = PlayerState(pdu.player_id, list(pdu.deck_list))
        self._emit(
            {
                "type": c.GAME_STATE_UPDATE,
                "state": {
                    "phase": c.STATE_LOBBY,
                    "players_ready": len(self.players),
                    "waiting_for": ["another_player"] if len(self.players) == 1 else [],
                },
            },
            pdu.player_id,
        )
        if len(self.players) == 2:
            self._start_game()

    def _dispatch_action(self, player_id: str, pdu: messages.PDU, raw: dict) -> None:
        """Send each valid PDU type to the method that owns its game rule."""
        mandatory = (
            messages.MulliganChoice,
            messages.Discard,
            messages.DeclareAttackers,
            messages.DeclareBlockers,
            messages.AssignDamageOrder,
        )
        if not isinstance(pdu, mandatory) and player_id != self.priority_holder:
            self._error(player_id, c.ERR_NOT_YOUR_PRIORITY, "You do not hold priority.", raw)
            return

        if isinstance(pdu, messages.MulliganChoice):
            self._mulligan(player_id, pdu, raw)
        elif isinstance(pdu, messages.Discard):
            self._discard(player_id, pdu, raw)
        elif isinstance(pdu, messages.PriorityPass):
            self._pass(player_id)
        elif isinstance(pdu, messages.PlayLand):
            self._play_land(player_id, pdu, raw)
        elif isinstance(pdu, messages.CastSpell):
            self._cast_spell(player_id, pdu, raw)
        elif isinstance(pdu, messages.DeclareAttackers):
            self._declare_attackers(player_id, pdu, raw)
        elif isinstance(pdu, messages.DeclareBlockers):
            self._declare_blockers(player_id, pdu, raw)
        elif isinstance(pdu, messages.AssignDamageOrder):
            self._damage_order(player_id, pdu, raw)
        else:
            self._error(player_id, c.ERR_ILLEGAL_ACTION, f"{pdu.TYPE} is not implemented by this rules subset.", raw)

    # ---- lifecycle and phases -----------------------------------------------
    def _start_game(self) -> None:
        """Shuffle both decks, deal opening hands, and enter MULLIGAN."""
        self.state = c.STATE_GAME_SETUP
        self.phase = c.STATE_MULLIGAN
        self.turn = 0

        for player in self.players.values():
            # The library is a separate list so the submitted deck is retained.
            player.library = list(player.deck)
            self.rng.shuffle(player.library)
            self._draw(player.player_id, c.STARTING_HAND_SIZE, end_game=False)

        self.active_player = self.rng.choice(list(self.players))
        # For debugging purposes: 
        #self.active_player = next(iter(self.players))
        self.state = c.STATE_MULLIGAN

        for pid in self.players: self._send_state(pid)

        # Each player echoes their own received setup update; retain token per-player.
        self.mulligan_tokens = {pid: self.seq_num - (len(self.players) - 1 - i) for i, pid in enumerate(self.players)}
        print("[DEBUG] MULLIGAN TOKENS:", self.mulligan_tokens)

    def _mulligan(self, pid: str, pdu: messages.MulliganChoice, raw: dict) -> None:
        """Apply one London Mulligan decision for a player."""
        player = self.players[pid]
        if self.state != c.STATE_MULLIGAN or player.kept:
            self._error(pid, c.ERR_ILLEGAL_ACTION, "Mulligan choice is not currently requested.", raw)
            return
        if pdu.seq_num != self.mulligan_tokens.get(pid):
            self._error(pid, c.ERR_STALE_ACTION, "Mulligan token mismatch.", raw)
            return

        if not pdu.keep:
            # Return the old hand, shuffle it back in, then redraw seven cards.
            player.library.extend(player.hand)
            player.hand.clear()
            self.rng.shuffle(player.library)
            player.mulligans += 1
            self._draw(pid, c.STARTING_HAND_SIZE, end_game=False)
            self.mulligan_tokens[pid] = self._send_state(pid)
            return

        if len(pdu.cards_to_bottom) != player.mulligans or any(x not in player.hand for x in pdu.cards_to_bottom):
            self._error(pid, c.ERR_ILLEGAL_ACTION, "Must bottom exactly the mulligan count from your current hand.", raw)
            return

        for card in pdu.cards_to_bottom:
            player.hand.remove(card)
            player.library.insert(0, card)

        player.kept = True
        if all(p.kept for p in self.players.values()):
            self.state = c.STATE_IN_GAME
            self.turn = 1
            self._begin_turn()

    def _begin_turn(self) -> None:
        """Perform the automatic Untap step, then move to Upkeep."""
        ap = self.players[self.active_player]
        self._broadcast_transition(c.PHASE_UNTAP)
        ap.land_played = False

        for permanent in ap.battlefield:
            permanent["tapped"] = False
            permanent["summoning_sick"] = False

        self._send_state()
        self._enter_phase(c.PHASE_UPKEEP)

    def _enter_phase(self, phase: str) -> None:
        """Start a phase and perform its automatic action, if it has one."""
        token = self._broadcast_transition(phase)
        if phase == c.PHASE_DRAW:
            if self.turn != 1: self._draw(self.active_player, 1)
            self._send_state()
        if phase == c.PHASE_DECLARE_ATTACKERS:
            # The PHASE_TRANSITION itself is the request PDU for attackers.
            self.priority_holder = self.active_player
            self.priority_token = token
            return
        if phase == c.PHASE_DECLARE_BLOCKERS:
            self.priority_holder = self._opponent(self.active_player)
            self.priority_token = token
            return
        if phase == c.PHASE_ASSIGN_DAMAGE_ORDER:
            self.priority_holder = self.active_player
            self.priority_token = token
            return
        if phase == c.PHASE_FIRST_STRIKE_DAMAGE:
            self._combat_damage(first_strike=True); self._grant_priority(self.active_player); return
        if phase == c.PHASE_COMBAT_DAMAGE:
            self._combat_damage(first_strike=False); self._enter_phase(c.PHASE_END_OF_COMBAT); return
        if phase == c.PHASE_CLEANUP:
            self._cleanup(); return
        self._grant_priority(self.active_player)

    def _advance_after_empty_stack(self) -> None:
        """Move to the next RFC phase after both players pass priority."""
        order = list(c.PHASE_ORDER)
        index = order.index(self.phase)
        if self.phase == c.PHASE_BEGIN_COMBAT: self._enter_phase(c.PHASE_DECLARE_ATTACKERS)
        elif self.phase == c.PHASE_DECLARE_ATTACKERS: self._enter_phase(c.PHASE_DECLARE_BLOCKERS)
        elif self.phase == c.PHASE_DECLARE_BLOCKERS:
            multi = {a["creature_id"] for a in self.attackers if sum(b["blocking_id"] == a["creature_id"] for b in self.blockers) > 1}
            if multi:
                self.pending_damage_orders = multi
                self._enter_phase(c.PHASE_ASSIGN_DAMAGE_ORDER)
            else:
                self._enter_phase(c.PHASE_COMBAT_DAMAGE)
        elif self.phase == c.PHASE_ASSIGN_DAMAGE_ORDER: self._enter_phase(c.PHASE_COMBAT_DAMAGE)
        elif self.phase == c.PHASE_END_OF_COMBAT:
            self.attackers.clear()
            self.blockers.clear()
            self._enter_phase(c.PHASE_POSTCOMBAT_MAIN)
        elif self.phase == c.PHASE_END_STEP: self._enter_phase(c.PHASE_CLEANUP)
        elif self.phase in (c.PHASE_UPKEEP, c.PHASE_DRAW, c.PHASE_PRECOMBAT_MAIN, c.PHASE_POSTCOMBAT_MAIN): self._enter_phase(order[index + 1])

    def _cleanup(self) -> None:
        """Handle hand-size discard, end-of-turn cleanup, and the next turn."""
        ap = self.players[self.active_player]
        if len(ap.hand) > c.MAX_HAND_SIZE:
            # The state update is the token the client must echo in DISCARD.
            self.priority_holder = self.active_player
            self.priority_token = self._send_state(self.active_player)
            return

        for player in self.players.values():
            for permanent in player.battlefield:
                permanent["damage"] = 0
                permanent.pop("power_bonus", None)
                permanent.pop("toughness_bonus", None)

        self._send_state()
        self.turn += 1
        self.active_player = self._opponent(self.active_player)
        self._begin_turn()

    # ---- normal actions ------------------------------------------------------
    def _pass(self, pid: str) -> None:
        """Process PRIORITY_PASS and either switch priority or advance play."""
        self.consecutive_passes += 1
        if self.consecutive_passes < 2:
            self._grant_priority(self._opponent(pid))
            return

        self.consecutive_passes = 0
        if self.stack:
            # A non-empty stack resolves only after two consecutive passes.
            self._resolve_top()
            self._grant_priority(self.active_player)
        else:
            self._advance_after_empty_stack()

    def _play_land(self, pid: str, pdu: messages.PlayLand, raw: dict) -> None:
        """Validate and play one land without putting it on the stack."""
        player = self.players[pid]
        main_phase = self.phase in (c.PHASE_PRECOMBAT_MAIN, c.PHASE_POSTCOMBAT_MAIN)
        card_is_land = _CARD_ROWS[card_base(pdu.card_id)][0] == "Land"
        allowed = (
            pid == self.active_player
            and main_phase
            and not self.stack
            and not player.land_played
            and pdu.card_id in player.hand
            and card_is_land
        )
        if not allowed:
            self._error(pid, c.ERR_ILLEGAL_ACTION, "A land may be played once per turn by the active player in an empty-stack main phase.", raw)
            return

        player.hand.remove(pdu.card_id)
        player.battlefield.append(self._permanent(pdu.card_id))
        player.land_played = True
        self._send_state()
        self._grant_priority(pid)

    def _cast_spell(self, pid: str, pdu: messages.CastSpell, raw: dict) -> None:
        """Validate mana and targets, then push a spell onto the LIFO stack."""
        player = self.players[pid]
        if pdu.card_id not in player.hand:
            self._error(pid, c.ERR_ILLEGAL_ACTION, "Card is not in your hand.", raw)
            return

        base = card_base(pdu.card_id)
        spec = _CARD_ROWS.get(base)
        main_phase = self.phase in (c.PHASE_PRECOMBAT_MAIN, c.PHASE_POSTCOMBAT_MAIN)
        sorcery_speed = pid == self.active_player and main_phase and not self.stack
        if not spec or spec[0] == "Land" or (spec[0] != "Instant" and not sorcery_speed):
            self._error(pid, c.ERR_WRONG_PHASE, "That spell cannot be cast in this phase.", raw)
            return

        if not self._pay_mana(player, spec[1], pdu.mana_payment):
            self._error(pid, c.ERR_INSUFFICIENT_MANA, "Declared mana payment cannot be satisfied by untapped mana sources.", raw)
            return
        if not self._valid_targets(base, pdu.targets, pid):
            self._error(pid, c.ERR_ILLEGAL_TARGET, "One or more targets are illegal for this spell.", raw)
            return

        player.hand.remove(pdu.card_id)
        item = {
            "stack_item_id": f"stk_{self.seq_num + 1:04d}",
            "item_type": c.ITEM_TYPE_SPELL,
            "source": pdu.card_id,
            "targets": list(pdu.targets),
            "controller": pid,
        }
        self.stack.append(item)
        self._emit({"type": c.STACK_PUSH, **item})
        # The caster keeps priority after adding an item to the stack.
        self._grant_priority(pid)

    def _declare_attackers(self, pid: str, pdu: messages.DeclareAttackers, raw: dict) -> None:
        if self.phase != c.PHASE_DECLARE_ATTACKERS or pid != self.active_player:
            self._error(pid, c.ERR_WRONG_PHASE, "Only the active player declares attackers in this step.", raw); return
        seen = set(); opponent = self._opponent(pid)
        for attack in pdu.attackers:
            permanent = self._find_permanent(pid, attack["creature_id"])
            if not permanent or attack["creature_id"] in seen or attack["target"] != opponent or permanent["tapped"] or permanent["summoning_sick"]:
                self._error(pid, c.ERR_ILLEGAL_ACTION, "Attackers must be distinct, untapped, non-sick creatures targeting the opponent.", raw); return
            seen.add(attack["creature_id"])
        self.attackers = [dict(x) for x in pdu.attackers]
        for attack in self.attackers: self._find_permanent(pid, attack["creature_id"])["tapped"] = True
        self._send_state()
        if not self.attackers: self._enter_phase(c.PHASE_END_OF_COMBAT)
        else: self._grant_priority(pid)

    def _declare_blockers(self, pid: str, pdu: messages.DeclareBlockers, raw: dict) -> None:
        if self.phase != c.PHASE_DECLARE_BLOCKERS or pid != self._opponent(self.active_player):
            self._error(pid, c.ERR_WRONG_PHASE, "Only the defending player declares blockers in this step.", raw); return
        seen = set(); attacking = {a["creature_id"] for a in self.attackers}
        for block in pdu.blockers:
            permanent = self._find_permanent(pid, block["creature_id"])
            if not permanent or permanent["tapped"] or block["creature_id"] in seen or block["blocking_id"] not in attacking:
                self._error(pid, c.ERR_ILLEGAL_ACTION, "Blockers must be distinct untapped creatures blocking an attacker.", raw); return
            seen.add(block["creature_id"])
        self.blockers = [dict(x) for x in pdu.blockers]; self._send_state(); self._grant_priority(self.active_player)

    def _damage_order(self, pid: str, pdu: messages.AssignDamageOrder, raw: dict) -> None:
        blockers = [b["creature_id"] for b in self.blockers if b["blocking_id"] == pdu.attacker_id]
        if self.phase != c.PHASE_ASSIGN_DAMAGE_ORDER or pid != self.active_player or pdu.attacker_id not in self.pending_damage_orders or Counter(pdu.blocker_order) != Counter(blockers):
            self._error(pid, c.ERR_ILLEGAL_ACTION, "Damage order must list each blocker of one multiply-blocked attacker exactly once.", raw); return
        self.pending_damage_orders.remove(pdu.attacker_id)
        for attack in self.attackers:
            if attack["creature_id"] == pdu.attacker_id: attack["damage_order"] = list(pdu.blocker_order)
        if not self.pending_damage_orders: self._grant_priority(pid)

    def _discard(self, pid: str, pdu: messages.Discard, raw: dict) -> None:
        player = self.players[pid]
        if self.phase != c.PHASE_CLEANUP or pid != self.active_player or any(x not in player.hand for x in pdu.card_ids) or len(set(pdu.card_ids)) != len(pdu.card_ids):
            self._error(pid, c.ERR_ILLEGAL_ACTION, "Discard cards must be distinct cards from the active hand during cleanup.", raw); return
        for card in pdu.card_ids: player.hand.remove(card); player.graveyard.append(card)
        self._cleanup()

    # ---- effects, mana, and combat ------------------------------------------
    def _permanent(self, card_id: str) -> dict:
        typ, _, power, toughness, effect = _CARD_ROWS[card_base(card_id)]
        return {"card_id": card_id, "type": typ, "power": power, "toughness": toughness, "tapped": False,
                "damage": 0, "summoning_sick": "haste" not in effect}

    def _find_permanent(self, pid: str, card_id: str) -> dict | None:
        return next((x for x in self.players[pid].battlefield if x["card_id"] == card_id), None)

    def _pay_mana(self, player: PlayerState, cost: dict, payment: dict) -> bool:
        if any(payment.get(k, 0) < v for k, v in cost.items()) or sum(payment.values()) != sum(cost.values()): return False
        sources = Counter()
        for permanent in player.battlefield:
            base = card_base(permanent["card_id"])
            if not permanent["tapped"] and _CARD_ROWS[base][4].startswith("mana:"): sources[_CARD_ROWS[base][4].split(":")[1]] += 1
        colored = sum(payment.get(color, 0) for color in "WUBRG")
        if any(payment.get(color, 0) > sources[color] for color in "WUBRG") or payment.get("X", 0) > sum(sources.values()) - colored: return False
        remaining = Counter({color: payment.get(color, 0) for color in "WUBRG"})
        generic = payment.get("X", 0)
        for permanent in player.battlefield:
            base = card_base(permanent["card_id"]); effect = _CARD_ROWS[base][4]
            if permanent["tapped"] or not effect.startswith("mana:"): continue
            color = effect.split(":")[1]
            if remaining[color] > 0 or generic > 0:
                permanent["tapped"] = True
                if remaining[color] > 0: remaining[color] -= 1
                else: generic -= 1
        return generic == 0 and not any(remaining.values())

    def _valid_targets(self, base: str, targets: list, controller: str) -> bool:
        effect = _CARD_ROWS[base][4]
        if effect in ("counter", "draw:1", "ramp") or not effect: return not targets
        if len(targets) != 1: return False
        target = targets[0]
        if "player" in effect: return target in self.players
        if "creature" in effect or effect in ("bounce", "exile", "pump:3:3"):
            return any(self._find_permanent(pid, target) and "Creature" in self._find_permanent(pid, target)["type"] for pid in self.players)
        return target in self.players or any(self._find_permanent(pid, target) for pid in self.players)

    def _resolve_top(self) -> None:
        item = self.stack.pop(); base, effect = card_base(item["source"]), _CARD_ROWS[card_base(item["source"])][4]
        changes: list[dict] = []
        if effect.startswith("damage"):
            target, amount = item["targets"][0], int(effect.rsplit(":", 1)[1]); self._damage(target, amount, item["source"], changes)
        elif effect == "draw:1": self._draw(item["controller"], 1); changes.append({"type": "DRAW", "player": item["controller"], "amount": 1})
        elif effect == "pump:3:3":
            permanent = next((self._find_permanent(pid, item["targets"][0]) for pid in self.players if self._find_permanent(pid, item["targets"][0])), None)
            if permanent: permanent["power_bonus"] = permanent.get("power_bonus", 0) + 3; permanent["toughness_bonus"] = permanent.get("toughness_bonus", 0) + 3; changes.append({"type": "PUMP", "target": item["targets"][0], "power": 3, "toughness": 3})
        elif effect == "heal:3": self.players[item["targets"][0]].life += 3; changes.append({"type": "LIFE_GAIN", "target": item["targets"][0], "amount": 3})
        elif _CARD_ROWS[base][0] in ("Creature", "Artifact", "Enchantment", "Artifact Creature"):
            self.players[item["controller"]].battlefield.append(self._permanent(item["source"])); changes.append({"type": "ENTER_BATTLEFIELD", "card": item["source"]})
        else: self.players[item["controller"]].graveyard.append(item["source"])
        self._emit({"type": c.STACK_RESOLVE, "stack_item_id": item["stack_item_id"], "result": c.RESULT_RESOLVED, "state_changes": changes})
        self._send_state(); self._check_life()

    def _damage(self, target: str, amount: int, source: str, events: list[dict]) -> None:
        if target in self.players: self.players[target].life -= amount
        else:
            permanent = next((self._find_permanent(pid, target) for pid in self.players if self._find_permanent(pid, target)), None)
            if permanent: permanent["damage"] += amount
        events.append({"type": "DAMAGE", "source": source, "target": target, "amount": amount})

    def _combat_damage(self, *, first_strike: bool) -> None:
        events: list[dict] = []
        for attack in self.attackers:
            attacker = self._find_permanent(self.active_player, attack["creature_id"])
            if not attacker: continue
            blockers = [self._find_permanent(self._opponent(self.active_player), b["creature_id"]) for b in self.blockers if b["blocking_id"] == attack["creature_id"]]
            blockers = [x for x in blockers if x]
            power = attacker["power"] + attacker.get("power_bonus", 0)
            if not blockers: self._damage(attack["target"], power, attack["creature_id"], events)
            else:
                ordered = attack.get("damage_order") or [b["card_id"] for b in blockers]
                self._damage(ordered[0], power, attack["creature_id"], events)
                for blocker in blockers: self._damage(attack["creature_id"], blocker["power"] + blocker.get("power_bonus", 0), blocker["card_id"], events)
        died = self._state_based_actions()
        self._emit({"type": c.COMBAT_DAMAGE_RESULT, "damage_events": events,
                    "life_totals": {pid: p.life for pid, p in self.players.items()}, "creatures_died": died})
        self._send_state(); self._check_life()

    def _state_based_actions(self) -> list[str]:
        died = []
        for player in self.players.values():
            survivors = []
            for permanent in player.battlefield:
                if "Creature" in permanent["type"] and permanent["damage"] >= permanent["toughness"] + permanent.get("toughness_bonus", 0):
                    player.graveyard.append(permanent["card_id"]); died.append(permanent["card_id"])
                else: survivors.append(permanent)
            player.battlefield = survivors
        return died

    def _draw(self, pid: str, count: int, *, end_game: bool = True) -> bool:
        player = self.players[pid]
        for _ in range(count):
            if not player.library:
                if end_game: self._game_over(self._opponent(pid), pid, c.REASON_DECK_EMPTY)
                return False
            player.hand.append(player.library.pop())
        return True

    def _check_life(self) -> None:
        losers = [pid for pid, player in self.players.items() if player.life <= 0]
        if losers: self._game_over(self._opponent(losers[0]), losers[0], c.REASON_LIFE_ZERO)

    def _game_over(self, winner: str, loser: str, reason: str) -> None:
        self.state = c.STATE_GAME_OVER
        self._emit({"type": c.GAME_OVER, "winner_id": winner, "loser_id": loser, "reason": reason})
        # Preserve TCP ownership; only logical player/game state is reset.
        connections = dict(self.ready_by_connection)
        self.reset_lobby(); self.ready_by_connection = connections

    def disconnected(self, connection: object) -> None:
        with self.lock:
            pid = self.ready_by_connection.pop(connection, None)
            if pid and self.state not in (c.STATE_LOBBY, c.STATE_GAME_OVER) and len(self.players) == 2:
                self._game_over(self._opponent(pid), pid, c.REASON_DISCONNECT)
