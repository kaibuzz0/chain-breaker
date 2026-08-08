"""Connection manager for the Chain-Breaker network layer.

Phase 8D implements connection lifecycle ownership, capacity limits, and
handshake execution over the existing abstract transport. No sockets,
discovery, sync, relay, or mempool functionality exists.
"""

from __future__ import annotations

import contextlib
from dataclasses import dataclass, field
from typing import Any

from chainbreaker.network import HELLO_ACK, NetworkEnvelope, parse_envelope, serialize_envelope
from chainbreaker.network.codec import encode_payload
from chainbreaker.network.transport import (
    Connection,
    ConnectionState,
    HandshakeContext,
    HandshakeSession,
    Transport,
    TransportLimitError,
    TransportLimits,
    TransportStateError,
    TransportValidationError,
)
from chainbreaker.network.transport.handshake import HandshakeState, PeerCapabilities


@dataclass(slots=True)
class ManagedConnection:
    """A transport connection plus its handshake and metadata."""

    connection_id: str
    transport: Transport
    handshake: HandshakeSession
    limits: TransportLimits
    connection: Connection = field(init=False)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def is_established(self) -> bool:
        return self.handshake.state == HandshakeState.ESTABLISHED

    @property
    def is_open(self) -> bool:
        return self.transport.is_open and not self.is_terminal

    @property
    def is_terminal(self) -> bool:
        return self.handshake.state in {HandshakeState.REJECTED, HandshakeState.CLOSED}

    @property
    def capabilities(self) -> PeerCapabilities | None:
        return self.handshake.capabilities

    async def close(self) -> None:
        self.handshake.close()
        with contextlib.suppress(Exception):
            await self.transport.close()


class ConnectionManager:
    """Owns a bounded set of managed connections and drives handshakes."""

    def __init__(
        self,
        handshake_context: HandshakeContext,
        max_connections: int = 128,
        limits: TransportLimits | None = None,
    ) -> None:
        self._context = handshake_context
        self._max_connections = max_connections
        self._limits = limits or TransportLimits()
        self._connections: dict[str, ManagedConnection] = {}
        self._reject_counts: dict[str, int] = {}
        self._banned_peers: set[str] = set()

    @property
    def connection_count(self) -> int:
        return len(self._connections)

    @property
    def available_slots(self) -> int:
        return max(0, self._max_connections - len(self._connections))

    def is_banned(self, peer_key: str) -> bool:
        return peer_key in self._banned_peers

    async def accept(
        self,
        connection_id: str,
        transport: Transport,
        peer_key: str,
    ) -> ManagedConnection:
        """Register an outbound-style connection and run the handshake."""
        managed = self._prepare(connection_id, transport, peer_key)
        session = managed.handshake

        try:
            # Outbound-style handshake: send HELLO first, then wait for HELLO_ACK.
            hello = session.send_hello(local_height=0, local_chain_work="0" * 64)
            await transport.send(hello)

            # Wait for peer's HELLO
            peer_hello = await transport.receive()
            session.handle_hello(peer_hello)
            if _is_rejected(session):
                self._record_reject(peer_key)
                raise TransportValidationError(session.reject_reason or "rejected")

            # Build and send HELLO_ACK
            ack = session.build_hello_ack(ok=True)
            await transport.send(ack)

            # Wait for our HELLO_ACK from the peer
            peer_ack = await transport.receive()
            session.handle_hello_ack(peer_ack)
            if _is_rejected(session):
                self._record_reject(peer_key)
                raise TransportValidationError(session.reject_reason or "rejected")

            if session.state != HandshakeState.ESTABLISHED:
                raise TransportValidationError("handshake did not establish")

            managed.connection.transition_to(ConnectionState.ACTIVE)
            return managed
        finally:
            if not managed.is_established:
                await managed.close()
                self._connections.pop(connection_id, None)

    async def register_inbound(
        self,
        connection_id: str,
        transport: Transport,
        peer_key: str,
    ) -> ManagedConnection:
        """Run the inbound side of the handshake.

        The peer sends HELLO first; we respond with HELLO_ACK.
        """
        managed = self._prepare(connection_id, transport, peer_key)
        session = managed.handshake

        try:
            # Wait for peer HELLO first
            peer_hello = await transport.receive()
            session.handle_hello(peer_hello)
            if _is_rejected(session):
                reason = session.reject_reason or "rejected"
                ack = _build_ack(ok=False, reason=reason)
                with contextlib.suppress(Exception):
                    await transport.send(ack)
                self._record_reject(peer_key)
                raise TransportValidationError(reason)

            # Build and send HELLO_ACK
            ack = session.build_hello_ack(ok=True)
            await transport.send(ack)
            session.transition_to(HandshakeState.ESTABLISHED)
            managed.connection.transition_to(ConnectionState.ACTIVE)
            return managed
        finally:
            if not managed.is_established:
                await managed.close()
                self._connections.pop(connection_id, None)

    async def remove(self, connection_id: str) -> None:
        managed = self._connections.pop(connection_id, None)
        if managed:
            await managed.close()

    async def cleanup(self) -> None:
        """Close and remove all managed connections."""
        ids = list(self._connections.keys())
        for connection_id in ids:
            await self.remove(connection_id)

    def status(self) -> dict[str, Any]:
        return {
            "max_connections": self._max_connections,
            "active": self.connection_count,
            "available_slots": self.available_slots,
            "banned_peers": len(self._banned_peers),
            "connection_ids": sorted(self._connections.keys()),
        }

    def _prepare(
        self,
        connection_id: str,
        transport: Transport,
        peer_key: str,
    ) -> ManagedConnection:
        if self.is_banned(peer_key):
            raise TransportLimitError(f"peer {peer_key} is banned")
        if len(self._connections) >= self._max_connections:
            raise TransportLimitError("connection manager at capacity")
        if connection_id in self._connections:
            raise TransportStateError(f"connection id {connection_id} already exists")

        connection = Connection(connection_id)
        connection.transition_to(ConnectionState.OPENING)
        session = HandshakeSession(self._context)
        managed = ManagedConnection(
            connection_id=connection_id,
            transport=transport,
            handshake=session,
            limits=self._limits,
            metadata={"peer_key": peer_key},
        )
        managed.connection = connection
        self._connections[connection_id] = managed
        return managed

    def _record_reject(self, peer_key: str) -> None:
        self._reject_counts[peer_key] = self._reject_counts.get(peer_key, 0) + 1
        if self._reject_counts[peer_key] >= 3:
            self._banned_peers.add(peer_key)


def _is_rejected(session: HandshakeSession) -> bool:
    return session.state == HandshakeState.REJECTED


def _build_ack(ok: bool, reason: str = "") -> NetworkEnvelope:
    payload = {"ok": ok, "reason": reason}
    return parse_envelope(serialize_envelope(HELLO_ACK, payload=encode_payload(payload)))
