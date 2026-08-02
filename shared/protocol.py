"""
This module owns the wire format: how PDUs are framed over TCP (Section 5.2)
and how a raw dict is checked for structural validity BEFORE it is handed
to messages.py for parsing into a typed object.

Scope boundary (deliberate): this module does NOT know about game state.
It never asks "does this player hold priority" or "is this creature tapped."
Those are game-rule questions that only the server can answer,
because they require live state. This file only answers: "is this PDU
shaped the way the RFC says it must be shaped?"
"""

from __future__ import annotations

import json
import socket

from shared.constants import (
    LENGTH_PREFIX_BYTES,
    LENGTH_BYTEORDER,
    MAX_PDU_SIZE_BYTES,
    ALL_PDU_TYPES,
)

# Exceptions
class ProtocolError(Exception):
    # Base class for all protocol violations, structural and semantic.
    # Every subclass carries an 'error_code' matching one of the RFC Section 11
    # codes, so any caller can turn a caught ProtocolError directly into an
    # ERROR PDU without re-deriving what went wrong.
    error_code: str = "INVALID_JSON"

    def __init__(self, message: str, rejected_action: dict | None = None):
        super().__init__(message)
        self.message = message
        self.rejected_action = rejected_action


class InvalidJSONError(ProtocolError):
    # The received bytes could not be parsed as valid UTF-8 JSON.
    error_code = "INVALID_JSON"


class UnknownTypeError(ProtocolError):
    # The type field does not match any known PDU type.
    error_code = "UNKNOWN_TYPE"


class MalformedPDUError(ProtocolError):
    """
    Raised when a PDU's 'type' is recognized but its fields don't match
    the required shape (missing field, wrong type, etc).

    Not a literal RFC error code on its own -- defaults to INVALID_JSON
    as the closest structural bucket. Callers may re-map to a more
    specific code (e.g. ILLEGAL_DECK) where the RFC defines one.
    """
    error_code = "INVALID_JSON"


class PDUTooLargeError(ProtocolError):
    # PDU exceeds the 65,535-byte limit (RFC Section 5.2).
    error_code = "INVALID_JSON"


class IllegalDeckError(ProtocolError):
    """
    deck_list is empty, contains more than 50 cards, or includes one or
    more cards not in the legal card set.

    The size check (empty / more than 50) is structural. The "cards not in the
    legal card set" check requires the server's card catalog and is
    semantic, should be raised by server logic.
    """
    error_code = "ILLEGAL_DECK"

class StaleActionError(ProtocolError):
    # The seq_num does not match the current priority token.
    error_code = "STALE_ACTION"


class NotYourPriorityError(ProtocolError):
    # The client submitted an action PDU when it does not hold priority.
    error_code = "NOT_YOUR_PRIORITY"


class IllegalActionError(ProtocolError):
    # The action is syntactically valid but violates game rules.
    error_code = "ILLEGAL_ACTION"


class IllegalTargetError(ProtocolError):
    # One or more targets are not legal targets.
    error_code = "ILLEGAL_TARGET"


class TriggerOrderInvalidError(ProtocolError):
    # TRIGGER_ORDER_RESPONSE does not contain exactly the trigger IDs sent in the corresponding TRIGGER_ORDER PDU.
    error_code = "TRIGGER_ORDER_INVALID"


class TriggerChoiceInvalidError(ProtocolError):
    # TRIGGER_CHOICE_RESPONSE references an unknown trigger_id, or chosen_target is absent when a target is required.
    error_code = "TRIGGER_CHOICE_INVALID"


class InsufficientManaError(ProtocolError):
    # The mana_payment provided does not satisfy the spell's mana cost.
    error_code = "INSUFFICIENT_MANA"


class WrongPhaseError(ProtocolError):
    # The action is not legal in the current phase.
    error_code = "WRONG_PHASE"


class DuplicateIdError(ProtocolError):
    # The player_id in a PLAYER_READY PDU is already claimed by the other connected player in this lobby session.
    error_code = "DUPLICATE_ID"


class ConnectionClosedError(Exception):
    # Raised when the socket closes mid-read, distinct from a protocol error.
    pass


# Framing: exact-read helper (Section 5.2)
def recv_exact(sock: socket.socket, n: int) -> bytes:
    """
    Read exactly n bytes from sock, looping as needed.

    recv() on a TCP stream is not guaranteed to return all requested bytes
    in one call. This function blocks until exactly n bytes have been
    collected, or raises ConnectionClosedError if the peer closes first.
    """
    buff = bytearray()
    while len(buff) < n:
        chunk = sock.recv(n - len(buff))
        if not chunk:
            raise ConnectionClosedError(f"Connection closed after {len(buff)}/{n} bytes")
        buff.extend(chunk)
    return bytes(buff)


# Framing: send / receive a full PDU
def send_pdu(sock: socket.socket, pdu_dict: dict) -> None:
    """
    Serialize pdu_dict to JSON, frame it with a 4-byte big-endian length
    prefix, and send it over sock.
    """
    payload = json.dumps(pdu_dict).encode("utf-8")

    if len(payload) > MAX_PDU_SIZE_BYTES:
        raise PDUTooLargeError(f"PDU is {len(payload)} bytes; exceeds max of {MAX_PDU_SIZE_BYTES}")

    length_prefix = len(payload).to_bytes(LENGTH_PREFIX_BYTES, LENGTH_BYTEORDER)
    sock.sendall(length_prefix + payload)


def recv_pdu(sock: socket.socket) -> dict:
    """
    Read one complete PDU from sock: the 4-byte length prefix, then that
    many bytes of JSON payload. Returns the parsed dict.

    Raises InvalidJSONError if the payload isn't valid UTF-8 JSON, and
    ConnectionClosedError if the peer disconnects mid-read.
    """
    length_bytes = recv_exact(sock, LENGTH_PREFIX_BYTES)
    payload_length = int.from_bytes(length_bytes, LENGTH_BYTEORDER)

    if payload_length > MAX_PDU_SIZE_BYTES:
        raise PDUTooLargeError(
            f"Incoming PDU declares {payload_length} bytes; "
            f"exceeds max of {MAX_PDU_SIZE_BYTES}"
        )

    payload_bytes = recv_exact(sock, payload_length)

    try:
        return json.loads(payload_bytes.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise InvalidJSONError(f"Could not decode PDU payload: {exc}") from exc


# Structural validation (pre-parse gate)
def validate_envelope(raw: dict) -> None:
    """
    Check the two fields every PDU MUST have (Section 5.4), before any
    type-specific parsing happens.

    This is intentionally minimal: it does not check field values beyond
    "present and correctly typed." Type-specific field validation lives in
    messages.py, one dataclass constructor at a time.
    """
    if not isinstance(raw, dict):
        raise InvalidJSONError("PDU must be a JSON object")

    if "type" not in raw:
        raise MalformedPDUError("PDU missing required field: type", rejected_action=raw)
    if not isinstance(raw["type"], str):
        raise MalformedPDUError("PDU field 'type' must be a string", rejected_action=raw)
    if raw["type"] not in ALL_PDU_TYPES:
        raise UnknownTypeError(f"Unknown PDU type: {raw['type']!r}", rejected_action=raw)

    if "seq_num" not in raw:
        raise MalformedPDUError("PDU missing required field: seq_num", rejected_action=raw)
    if not isinstance(raw["seq_num"], int) or isinstance(raw["seq_num"], bool):
        # bool is a subclass of int in Python -- explicitly excluded
        raise MalformedPDUError("PDU field 'seq_num' must be an integer", rejected_action=raw)
