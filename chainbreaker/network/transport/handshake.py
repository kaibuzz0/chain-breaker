"""Connection handshake state machine and validation.

Phase 8D implements only the HELLO/HELLO_ACK exchange over the existing
abstract transport. No sockets, discovery, sync, or relay logic exists.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto
from typing import Any

from chainbreaker.network import HELLO, HELLO_ACK, NET_PROTOCOL_VERSION, NetworkEnvelope
from chainbreaker.network.messages import HelloMessage
from chainbreaker.network.transport.errors import (
    TransportStateError,
    TransportValidationError,
)


class HandshakeState(Enum):
    """Lifecycle of a single handshake attempt."""

    NEW = auto()
    SEND_HELLO = auto()
    WAIT_HELLO_ACK = auto()
    VALIDATING = auto()
    ESTABLISHED = auto()
    REJECTED = auto()
    CLOSED = auto()


_HANDSHAKE_VALID_TRANSITIONS: dict[HandshakeState, set[HandshakeState]] = {
    HandshakeState.NEW: {HandshakeState.SEND_HELLO, HandshakeState.VALIDATING, HandshakeState.REJECTED},
    HandshakeState.SEND_HELLO: {HandshakeState.WAIT_HELLO_ACK, HandshakeState.REJECTED, HandshakeState.CLOSED},
    HandshakeState.WAIT_HELLO_ACK: {
        HandshakeState.ESTABLISHED,
        HandshakeState.REJECTED,
        HandshakeState.CLOSED,
    },
    HandshakeState.VALIDATING: {HandshakeState.ESTABLISHED, HandshakeState.REJECTED, HandshakeState.CLOSED},
    HandshakeState.ESTABLISHED: {HandshakeState.CLOSED, HandshakeState.REJECTED},
    HandshakeState.REJECTED: {HandshakeState.CLOSED},
    HandshakeState.CLOSED: set(),
}


@dataclass(frozen=True, slots=True)
class PeerCapabilities:
    """Negotiated intersection of local and remote feature bits."""

    features: frozenset[str]

    def supports(self, feature: str) -> bool:
        return feature in self.features


@dataclass(frozen=True, slots=True)
class HandshakeContext:
    """Static parameters required to validate an incoming/outgoing peer."""

    network_id: str
    genesis_hash: str
    local_features: frozenset[str]
    protocol_version: int = NET_PROTOCOL_VERSION

    def validate_hello(self, msg: HelloMessage) -> tuple[bool, str]:
        """Return (ok, reason)."""
        if msg.protocol_version != self.protocol_version:
            return False, f"unsupported protocol version {msg.protocol_version}"
        if msg.network_id != self.network_id:
            return False, "wrong network_id"
        if msg.genesis_hash != self.genesis_hash:
            return False, "wrong genesis_hash"
        return True, ""


class HandshakeSession:
    """Single handshake state machine.

    The session is intentionally passive: it accepts and validates messages
    but does not perform I/O. The connection manager drives transport calls.
    """

    def __init__(self, context: HandshakeContext) -> None:
        self.context = context
        self.state = HandshakeState.NEW
        self.peer_info: HelloMessage | None = None
        self.capabilities: PeerCapabilities | None = None
        self.reject_reason: str | None = None

    def transition_to(self, new_state: HandshakeState) -> None:
        if new_state not in _HANDSHAKE_VALID_TRANSITIONS[self.state]:
            raise TransportStateError(
                f"invalid handshake transition {self.state.name} -> {new_state.name}"
            )
        self.state = new_state

    def send_hello(self, local_height: int, local_chain_work: str) -> NetworkEnvelope:
        """Create the local HELLO message and advance state."""
        if self.state != HandshakeState.NEW:
            raise TransportStateError(f"cannot send HELLO from {self.state.name}")
        self.transition_to(HandshakeState.SEND_HELLO)
        msg = HelloMessage(
            protocol_version=self.context.protocol_version,
            network_id=self.context.network_id,
            genesis_hash=self.context.genesis_hash,
            best_height=local_height,
            best_chain_work=local_chain_work,
            feature_bits=sorted(self.context.local_features),
            node_limits={},
        )
        from chainbreaker.network import parse_envelope, serialize_envelope

        return parse_envelope(serialize_envelope(HELLO, payload=msg.to_payload()))

    def handle_hello(self, envelope: NetworkEnvelope) -> None:
        """Process a HELLO from the peer."""
        if envelope.message_type != HELLO:
            self.reject("expected HELLO")
            return
        if self.state not in {HandshakeState.NEW, HandshakeState.SEND_HELLO, HandshakeState.WAIT_HELLO_ACK}:
            self.reject("unexpected HELLO")
            return
        try:
            msg = HelloMessage.from_payload(envelope.payload)
        except Exception as exc:
            self.reject(f"invalid HELLO payload: {exc}")
            return

        ok, reason = self.context.validate_hello(msg)
        if not ok:
            self.reject(reason)
            return

        self.peer_info = msg
        common = self.context.local_features & frozenset(msg.feature_bits)
        self.capabilities = PeerCapabilities(features=common)
        if self.state == HandshakeState.SEND_HELLO:
            self.transition_to(HandshakeState.WAIT_HELLO_ACK)
        elif self.state == HandshakeState.NEW:
            self.transition_to(HandshakeState.VALIDATING)

    def handle_hello_ack(self, envelope: NetworkEnvelope) -> None:
        """Process a HELLO_ACK from the peer."""
        if envelope.message_type != HELLO_ACK:
            self.reject("expected HELLO_ACK")
            return
        if self.state != HandshakeState.WAIT_HELLO_ACK:
            self.reject("unexpected HELLO_ACK")
            return
        try:
            payload = _decode_ack_payload(envelope.payload)
        except Exception as exc:
            self.reject(f"invalid HELLO_ACK payload: {exc}")
            return
        if not payload.get("ok"):
            self.reject(payload.get("reason", "rejected"))
            return
        self.transition_to(HandshakeState.ESTABLISHED)

    def build_hello_ack(self, ok: bool, reason: str = "") -> NetworkEnvelope:
        """Build a HELLO_ACK response.

        REJECTED is allowed so that an inbound endpoint can send a negative
        HELLO_ACK explaining why the peer was rejected before closing.
        """
        if self.state not in {
            HandshakeState.VALIDATING,
            HandshakeState.WAIT_HELLO_ACK,
            HandshakeState.REJECTED,
        }:
            raise TransportStateError(f"cannot build HELLO_ACK from {self.state.name}")
        payload = {"ok": ok, "reason": reason}
        from chainbreaker.network import parse_envelope, serialize_envelope

        return parse_envelope(serialize_envelope(HELLO_ACK, payload=_encode_ack_payload(payload)))

    def reject(self, reason: str) -> None:
        """Move session to REJECTED."""
        if self.state in {HandshakeState.ESTABLISHED, HandshakeState.CLOSED}:
            raise TransportStateError(f"cannot reject from {self.state.name}")
        self.reject_reason = reason
        if self.state != HandshakeState.REJECTED:
            self.transition_to(HandshakeState.REJECTED)

    def close(self) -> None:
        """Close the handshake session if not already terminal."""
        if self.state not in {HandshakeState.REJECTED, HandshakeState.CLOSED}:
            self.transition_to(HandshakeState.CLOSED)


def _encode_ack_payload(payload: dict[str, Any]) -> bytes:
    from chainbreaker.network.codec import encode_payload

    return encode_payload(payload)


def _decode_ack_payload(payload: bytes) -> dict[str, Any]:
    from chainbreaker.network.codec import decode_payload

    data = decode_payload(payload)
    if not isinstance(data, dict):
        raise TransportValidationError("HELLO_ACK payload must be an object")
    return data
