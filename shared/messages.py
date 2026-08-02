"""
One dataclass per PDU type defined in RFC Section 10. Each class:
  - Subclasses PDU (shared/messages.py base), inheriting 'seq_num'.
  - Declares a class-level TYPE string constant (never an instance field,
    you can't construct a CastSpell that accidentally claims to be a
    PLAY_LAND, because the type isnt settable data).
  - Is registered in PDU_REGISTRY so parse() can dispatch on the raw
    dict's "type" field.

Design choice (shallow typing): only the TOP-LEVEL PDU is a typed
dataclass. Nested structures, battlefield permanents, stack items,
the 'state' blob inside GAME_STATE_UPDATE, stay as plain dicts/lists.
GAME_STATE_UPDATE in particular has 3 different shapes depending on
context (lobby / mulligan / in-game), which dont map cleanly onto one
fixed nested schema anyway. Server code reads 'pdu.state["battlefield"]'
etc. directly.

This module handles structural validation only (right field, right
JSON type). It does not know about game state, whose turn it is, or
whether an action is legal, see protocol.py's module docstring for
that boundary.
"""

from __future__ import annotations

from dataclasses import dataclass, field, fields
from typing import Any, ClassVar

from shared import constants as c
from shared.protocol import MalformedPDUError


# Base class
@dataclass
class PDU:
    # Common base for every PDU. Only seq_num is shared instance data.
    seq_num: int


def _require(raw: dict, key: str, expected_type: type, pdu_type: str) -> Any:
    """Fetch raw[key], raising MalformedPDUError if missing or wrong-typed."""
    if key not in raw:
        raise MalformedPDUError(
            f"{pdu_type} missing required field: {key}", rejected_action=raw
        )
    value = raw[key]
    if expected_type is float and isinstance(value, int):
        value = float(value)  # allow ints where a float would do
    if not isinstance(value, expected_type) or (
        expected_type is int and isinstance(value, bool)
    ):
        raise MalformedPDUError(
            f"{pdu_type} field '{key}' must be {expected_type.__name__}, "
            f"got {type(value).__name__}",
            rejected_action=raw,
        )
    return value


def _optional(raw: dict, key: str, expected_type: type, default: Any) -> Any:
    """Fetch raw[key] if present (type-checked), else return default."""
    if key not in raw or raw[key] is None:
        return default
    value = raw[key]
    if not isinstance(value, expected_type):
        raise MalformedPDUError(
            f"field '{key}' must be {expected_type.__name__}, "
            f"got {type(value).__name__}",
            rejected_action=raw,
        )
    return value


# 1. Lobby / session lifecycle
@dataclass
class PlayerReady(PDU):
    player_id: str
    deck_list: list

    TYPE: ClassVar[str] = c.PLAYER_READY

    @classmethod
    def from_dict(cls, raw: dict) -> "PlayerReady":
        seq_num = _require(raw, "seq_num", int, cls.TYPE)
        player_id = _require(raw, "player_id", str, cls.TYPE)
        if player_id == "":
            raise MalformedPDUError("player_id must be non-empty", rejected_action=raw)
        deck_list = _require(raw, "deck_list", list, cls.TYPE)
        if not all(isinstance(card, str) for card in deck_list):
            raise MalformedPDUError("deck_list must contain only strings", rejected_action=raw)
        return cls(seq_num=seq_num, player_id=player_id, deck_list=deck_list)


@dataclass
class GameStateUpdate(PDU):
    """
    Covers all 3 shapes from Section 10.2.2 (lobby / mulligan / in-game).
    'state' is intentionally left as a raw dict, see module docstring.
    """
    state: dict

    TYPE: ClassVar[str] = c.GAME_STATE_UPDATE

    @classmethod
    def from_dict(cls, raw: dict) -> "GameStateUpdate":
        seq_num = _require(raw, "seq_num", int, cls.TYPE)
        state = _require(raw, "state", dict, cls.TYPE)
        return cls(seq_num=seq_num, state=state)


# 2. Setup / mulligan
@dataclass
class MulliganChoice(PDU):
    keep: bool
    cards_to_bottom: list

    TYPE: ClassVar[str] = c.MULLIGAN_CHOICE

    @classmethod
    def from_dict(cls, raw: dict) -> "MulliganChoice":
        seq_num = _require(raw, "seq_num", int, cls.TYPE)
        keep = _require(raw, "keep", bool, cls.TYPE)
        cards_to_bottom = _require(raw, "cards_to_bottom", list, cls.TYPE)
        if not all(isinstance(card, str) for card in cards_to_bottom):
            raise MalformedPDUError(
                "cards_to_bottom must contain only strings", rejected_action=raw
            )
        if not keep and cards_to_bottom:
            raise MalformedPDUError(
                "cards_to_bottom must be empty when keep is false", rejected_action=raw
            )
        return cls(seq_num=seq_num, keep=keep, cards_to_bottom=cards_to_bottom)


# 3. Turn / phase flow control
@dataclass
class PhaseTransition(PDU):
    from_phase: str
    to_phase: str
    active_player: str
    turn: int = None  # not present on every emitted example, kept optional

    TYPE: ClassVar[str] = c.PHASE_TRANSITION

    @classmethod
    def from_dict(cls, raw: dict) -> "PhaseTransition":
        seq_num = _require(raw, "seq_num", int, cls.TYPE)
        from_phase = _require(raw, "from_phase", str, cls.TYPE)
        to_phase = _require(raw, "to_phase", str, cls.TYPE)
        active_player = _require(raw, "active_player", str, cls.TYPE)
        turn = _optional(raw, "turn", int, None)
        if to_phase not in c.PHASE_ORDER:
            raise MalformedPDUError(f"Unknown to_phase: {to_phase!r}", rejected_action=raw)
        return cls(
            seq_num=seq_num, from_phase=from_phase, to_phase=to_phase,
            active_player=active_player, turn=turn,
        )


# 4. Priority & the stack
@dataclass
class PriorityGrant(PDU):
    player_id: str
    time_limit_ms: int = c.DEFAULT_TIME_LIMIT_MS

    TYPE: ClassVar[str] = c.PRIORITY_GRANT

    @classmethod
    def from_dict(cls, raw: dict) -> "PriorityGrant":
        seq_num = _require(raw, "seq_num", int, cls.TYPE)
        player_id = _require(raw, "player_id", str, cls.TYPE)
        time_limit_ms = _optional(raw, "time_limit_ms", int, c.DEFAULT_TIME_LIMIT_MS)
        return cls(seq_num=seq_num, player_id=player_id, time_limit_ms=time_limit_ms)


@dataclass
class PriorityPass(PDU):
    TYPE: ClassVar[str] = c.PRIORITY_PASS

    @classmethod
    def from_dict(cls, raw: dict) -> "PriorityPass":
        seq_num = _require(raw, "seq_num", int, cls.TYPE)
        return cls(seq_num=seq_num)


@dataclass
class CastSpell(PDU):
    card_id: str
    targets: list
    mana_payment: dict

    TYPE: ClassVar[str] = c.CAST_SPELL

    @classmethod
    def from_dict(cls, raw: dict) -> "CastSpell":
        seq_num = _require(raw, "seq_num", int, cls.TYPE)
        card_id = _require(raw, "card_id", str, cls.TYPE)
        targets = _require(raw, "targets", list, cls.TYPE)
        mana_payment = _require(raw, "mana_payment", dict, cls.TYPE)
        _validate_mana_payment(mana_payment, raw)
        return cls(seq_num=seq_num, card_id=card_id, targets=targets, mana_payment=mana_payment)


@dataclass
class ActivateAbility(PDU):
    source_id: str
    ability_index: int
    targets: list
    cost_payment: dict

    TYPE: ClassVar[str] = c.ACTIVATE_ABILITY

    @classmethod
    def from_dict(cls, raw: dict) -> "ActivateAbility":
        seq_num = _require(raw, "seq_num", int, cls.TYPE)
        source_id = _require(raw, "source_id", str, cls.TYPE)
        ability_index = _require(raw, "ability_index", int, cls.TYPE)
        targets = _require(raw, "targets", list, cls.TYPE)
        cost_payment = _require(raw, "cost_payment", dict, cls.TYPE)
        return cls(
            seq_num=seq_num, source_id=source_id, ability_index=ability_index,
            targets=targets, cost_payment=cost_payment,
        )


@dataclass
class StackPush(PDU):
    stack_item_id: str
    item_type: str
    source: str
    targets: list
    controller: str

    TYPE: ClassVar[str] = c.STACK_PUSH

    @classmethod
    def from_dict(cls, raw: dict) -> "StackPush":
        seq_num = _require(raw, "seq_num", int, cls.TYPE)
        stack_item_id = _require(raw, "stack_item_id", str, cls.TYPE)
        item_type = _require(raw, "item_type", str, cls.TYPE)
        if item_type not in c.STACK_ITEM_TYPES:
            raise MalformedPDUError(f"Unknown item_type: {item_type!r}", rejected_action=raw)
        source = _require(raw, "source", str, cls.TYPE)
        targets = _require(raw, "targets", list, cls.TYPE)
        controller = _require(raw, "controller", str, cls.TYPE)
        return cls(
            seq_num=seq_num, stack_item_id=stack_item_id, item_type=item_type,
            source=source, targets=targets, controller=controller,
        )


@dataclass
class TriggerOrder(PDU):
    player_id: str
    trigger_ids: list

    TYPE: ClassVar[str] = c.TRIGGER_ORDER

    @classmethod
    def from_dict(cls, raw: dict) -> "TriggerOrder":
        seq_num = _require(raw, "seq_num", int, cls.TYPE)
        player_id = _require(raw, "player_id", str, cls.TYPE)
        trigger_ids = _require(raw, "trigger_ids", list, cls.TYPE)
        return cls(seq_num=seq_num, player_id=player_id, trigger_ids=trigger_ids)


@dataclass
class TriggerOrderResponse(PDU):
    ordered_trigger_ids: list

    TYPE: ClassVar[str] = c.TRIGGER_ORDER_RESPONSE

    @classmethod
    def from_dict(cls, raw: dict) -> "TriggerOrderResponse":
        seq_num = _require(raw, "seq_num", int, cls.TYPE)
        ordered_trigger_ids = _require(raw, "ordered_trigger_ids", list, cls.TYPE)
        return cls(seq_num=seq_num, ordered_trigger_ids=ordered_trigger_ids)


@dataclass
class TriggerChoice(PDU):
    trigger_id: str
    source_id: str
    effect_summary: str
    requires_target: bool = False
    legal_targets: list = field(default_factory=list)

    TYPE: ClassVar[str] = c.TRIGGER_CHOICE

    @classmethod
    def from_dict(cls, raw: dict) -> "TriggerChoice":
        seq_num = _require(raw, "seq_num", int, cls.TYPE)
        trigger_id = _require(raw, "trigger_id", str, cls.TYPE)
        source_id = _require(raw, "source_id", str, cls.TYPE)
        effect_summary = _require(raw, "effect_summary", str, cls.TYPE)
        requires_target = _optional(raw, "requires_target", bool, False)
        legal_targets = _optional(raw, "legal_targets", list, [])
        return cls(
            seq_num=seq_num, trigger_id=trigger_id, source_id=source_id,
            effect_summary=effect_summary, requires_target=requires_target,
            legal_targets=legal_targets,
        )


@dataclass
class TriggerChoiceResponse(PDU):
    trigger_id: str
    accept: bool
    chosen_target: Any = None

    TYPE: ClassVar[str] = c.TRIGGER_CHOICE_RESPONSE

    @classmethod
    def from_dict(cls, raw: dict) -> "TriggerChoiceResponse":
        seq_num = _require(raw, "seq_num", int, cls.TYPE)
        trigger_id = _require(raw, "trigger_id", str, cls.TYPE)
        accept = _require(raw, "accept", bool, cls.TYPE)
        chosen_target = raw.get("chosen_target")
        if accept and chosen_target is not None and not isinstance(chosen_target, str):
            raise MalformedPDUError("chosen_target must be a string or null", rejected_action=raw)
        return cls(seq_num=seq_num, trigger_id=trigger_id, accept=accept, chosen_target=chosen_target)


@dataclass
class StackResolve(PDU):
    stack_item_id: str
    result: str
    state_changes: list

    TYPE: ClassVar[str] = c.STACK_RESOLVE

    @classmethod
    def from_dict(cls, raw: dict) -> "StackResolve":
        seq_num = _require(raw, "seq_num", int, cls.TYPE)
        stack_item_id = _require(raw, "stack_item_id", str, cls.TYPE)
        result = _require(raw, "result", str, cls.TYPE)
        if result not in c.STACK_RESOLVE_RESULTS:
            raise MalformedPDUError(f"Unknown result: {result!r}", rejected_action=raw)
        state_changes = _require(raw, "state_changes", list, cls.TYPE)
        return cls(seq_num=seq_num, stack_item_id=stack_item_id, result=result, state_changes=state_changes)


# 5. Combat sub-phase actions
@dataclass
class DeclareAttackers(PDU):
    attackers: list  # [{creature_id, target}, ...]; empty = no attack

    TYPE: ClassVar[str] = c.DECLARE_ATTACKERS

    @classmethod
    def from_dict(cls, raw: dict) -> "DeclareAttackers":
        seq_num = _require(raw, "seq_num", int, cls.TYPE)
        attackers = _require(raw, "attackers", list, cls.TYPE)
        for a in attackers:
            if not isinstance(a, dict) or "creature_id" not in a or "target" not in a:
                raise MalformedPDUError(
                    "each attacker needs creature_id and target", rejected_action=raw
                )
        return cls(seq_num=seq_num, attackers=attackers)


@dataclass
class DeclareBlockers(PDU):
    blockers: list  # [{creature_id, blocking_id}, ...]

    TYPE: ClassVar[str] = c.DECLARE_BLOCKERS

    @classmethod
    def from_dict(cls, raw: dict) -> "DeclareBlockers":
        seq_num = _require(raw, "seq_num", int, cls.TYPE)
        blockers = _require(raw, "blockers", list, cls.TYPE)
        for b in blockers:
            if not isinstance(b, dict) or "creature_id" not in b or "blocking_id" not in b:
                raise MalformedPDUError(
                    "each blocker needs creature_id and blocking_id", rejected_action=raw
                )
        return cls(seq_num=seq_num, blockers=blockers)


@dataclass
class AssignDamageOrder(PDU):
    attacker_id: str
    blocker_order: list

    TYPE: ClassVar[str] = c.ASSIGN_DAMAGE_ORDER

    @classmethod
    def from_dict(cls, raw: dict) -> "AssignDamageOrder":
        seq_num = _require(raw, "seq_num", int, cls.TYPE)
        attacker_id = _require(raw, "attacker_id", str, cls.TYPE)
        blocker_order = _require(raw, "blocker_order", list, cls.TYPE)
        return cls(seq_num=seq_num, attacker_id=attacker_id, blocker_order=blocker_order)


@dataclass
class CombatDamageResult(PDU):
    damage_events: list
    life_totals: dict
    creatures_died: list

    TYPE: ClassVar[str] = c.COMBAT_DAMAGE_RESULT

    @classmethod
    def from_dict(cls, raw: dict) -> "CombatDamageResult":
        seq_num = _require(raw, "seq_num", int, cls.TYPE)
        damage_events = _require(raw, "damage_events", list, cls.TYPE)
        life_totals = _require(raw, "life_totals", dict, cls.TYPE)
        creatures_died = _require(raw, "creatures_died", list, cls.TYPE)
        return cls(
            seq_num=seq_num, damage_events=damage_events,
            life_totals=life_totals, creatures_died=creatures_died,
        )


# 6. Player actions outside the stack
@dataclass
class PlayLand(PDU):
    card_id: str

    TYPE: ClassVar[str] = c.PLAY_LAND

    @classmethod
    def from_dict(cls, raw: dict) -> "PlayLand":
        seq_num = _require(raw, "seq_num", int, cls.TYPE)
        card_id = _require(raw, "card_id", str, cls.TYPE)
        return cls(seq_num=seq_num, card_id=card_id)


@dataclass
class Discard(PDU):
    card_ids: list

    TYPE: ClassVar[str] = c.DISCARD

    @classmethod
    def from_dict(cls, raw: dict) -> "Discard":
        seq_num = _require(raw, "seq_num", int, cls.TYPE)
        card_ids = _require(raw, "card_ids", list, cls.TYPE)
        if not all(isinstance(cid, str) for cid in card_ids):
            raise MalformedPDUError("card_ids must contain only strings", rejected_action=raw)
        return cls(seq_num=seq_num, card_ids=card_ids)


# 7. Session-ending
@dataclass
class Concede(PDU):
    player_id: str

    TYPE: ClassVar[str] = c.CONCEDE

    @classmethod
    def from_dict(cls, raw: dict) -> "Concede":
        seq_num = _require(raw, "seq_num", int, cls.TYPE)
        player_id = _require(raw, "player_id", str, cls.TYPE)
        return cls(seq_num=seq_num, player_id=player_id)


@dataclass
class GameOver(PDU):
    winner_id: str
    loser_id: str
    reason: str

    TYPE: ClassVar[str] = c.GAME_OVER

    @classmethod
    def from_dict(cls, raw: dict) -> "GameOver":
        seq_num = _require(raw, "seq_num", int, cls.TYPE)
        winner_id = _require(raw, "winner_id", str, cls.TYPE)
        loser_id = _require(raw, "loser_id", str, cls.TYPE)
        reason = _require(raw, "reason", str, cls.TYPE)
        if reason not in c.GAME_OVER_REASONS:
            raise MalformedPDUError(f"Unknown reason: {reason!r}", rejected_action=raw)
        return cls(seq_num=seq_num, winner_id=winner_id, loser_id=loser_id, reason=reason)


# 8. Connection health / errors
@dataclass
class Ping(PDU):
    timestamp: int

    TYPE: ClassVar[str] = c.PING

    @classmethod
    def from_dict(cls, raw: dict) -> "Ping":
        seq_num = _require(raw, "seq_num", int, cls.TYPE)
        timestamp = _require(raw, "timestamp", int, cls.TYPE)
        return cls(seq_num=seq_num, timestamp=timestamp)


@dataclass
class Pong(PDU):
    timestamp: int

    TYPE: ClassVar[str] = c.PONG

    @classmethod
    def from_dict(cls, raw: dict) -> "Pong":
        seq_num = _require(raw, "seq_num", int, cls.TYPE)
        timestamp = _require(raw, "timestamp", int, cls.TYPE)
        return cls(seq_num=seq_num, timestamp=timestamp)


@dataclass
class Error(PDU):
    code: str
    message: str
    rejected_action: dict = None

    TYPE: ClassVar[str] = c.ERROR

    @classmethod
    def from_dict(cls, raw: dict) -> "Error":
        seq_num = _require(raw, "seq_num", int, cls.TYPE)
        code = _require(raw, "code", str, cls.TYPE)
        if code not in c.ERROR_CODES:
            raise MalformedPDUError(f"Unknown error code: {code!r}", rejected_action=raw)
        message = _require(raw, "message", str, cls.TYPE)
        rejected_action = _optional(raw, "rejected_action", dict, None)
        return cls(seq_num=seq_num, code=code, message=message, rejected_action=rejected_action)


# Mana payment helper (shared by CAST_SPELL / used loosely elsewhere)
def _validate_mana_payment(mana_payment: dict, raw: dict) -> None:
    for color, amount in mana_payment.items():
        if color not in c.MANA_COLORS:
            raise MalformedPDUError(f"Unknown mana color: {color!r}", rejected_action=raw)
        if not isinstance(amount, int) or isinstance(amount, bool) or amount < 0:
            raise MalformedPDUError(
                f"mana_payment[{color!r}] must be a non-negative integer", rejected_action=raw
            )


# Registry + dispatcher
PDU_REGISTRY: dict[str, type] = {
    cls.TYPE: cls
    for cls in (
        PlayerReady, GameStateUpdate, MulliganChoice, PhaseTransition,
        PriorityGrant, PriorityPass, CastSpell, ActivateAbility,
        StackPush, TriggerOrder, TriggerOrderResponse, TriggerChoice,
        TriggerChoiceResponse, StackResolve, DeclareAttackers, DeclareBlockers,
        AssignDamageOrder, CombatDamageResult, PlayLand, Discard,
        Concede, GameOver, Ping, Pong, Error,
    )
}


def parse(raw: dict) -> PDU:
    # Parse a raw dict (already passed protocol.validate_envelope) into its typed PDU subclass.
    
    # Callers are expected to have called protocol.validate_envelope(raw) first; 
    # this function re-checks 'type' defensively but assumes the caller has already handled the JSON-decode step.

    pdu_type = raw.get("type")
    pdu_class = PDU_REGISTRY.get(pdu_type)
    if pdu_class is None:
        raise MalformedPDUError(f"No parser registered for type: {pdu_type!r}", rejected_action=raw)
    return pdu_class.from_dict(raw)


def to_dict(pdu: PDU) -> dict:
    # Serialize a typed PDU back into a plain dict suitable for protocol.send_pdu(). 
    
    # Inserts "type" from the class constant since it's not stored as instance data.
    result = {"type": pdu.TYPE}
    for f in fields(pdu):
        result[f.name] = getattr(pdu, f.name)
    return result


def is_seq_num_exempt(pdu_type: str) -> bool:
    # True if this PDU type does NOT follow the "echo the last priority-bearing seq_num" rule (CONCEDE, PING, see Section 5.4).
    # Server/client use this to know which validation path to take.

    return pdu_type in c.SEQ_NUM_EXEMPT_TYPES
