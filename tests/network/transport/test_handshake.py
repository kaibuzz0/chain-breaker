from __future__ import annotations

from chainbreaker.network import (
    HELLO,
    HELLO_ACK,
    NET_PROTOCOL_VERSION,
    NETWORK_ID,
    parse_envelope,
    serialize_envelope,
)
from chainbreaker.network.messages import HelloMessage
from chainbreaker.network.transport import (
    HandshakeContext,
    HandshakeSession,
    HandshakeState,
    PeerCapabilities,
)

LOCAL_FEATURES = ["headers", "blocks", "archive"]


def _context(
    genesis_hash: str = "0" * 64,
    network_id: str = NETWORK_ID,
    features: frozenset[str] | None = None,
) -> HandshakeContext:
    return HandshakeContext(
        network_id=network_id,
        genesis_hash=genesis_hash,
        local_features=features or frozenset(LOCAL_FEATURES),
    )


def _hello_payload(
    genesis_hash: str = "0" * 64,
    network_id: str = NETWORK_ID,
    features: list[str] | None = None,
    protocol_version: int = NET_PROTOCOL_VERSION,
) -> bytes:
    return HelloMessage(
        protocol_version=protocol_version,
        network_id=network_id,
        genesis_hash=genesis_hash,
        best_height=0,
        best_chain_work="0" * 64,
        feature_bits=sorted(features or []),
        node_limits={},
    ).to_payload()


def _ack_payload(ok: bool = True, reason: str = "") -> bytes:
    import json
    return serialize_envelope(
        HELLO_ACK,
        payload=json.dumps(
            {"ok": ok, "reason": reason},
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8"),
    )


def test_new_state() -> None:
    ctx = _context()
    session = HandshakeSession(ctx)
    assert session.state == HandshakeState.NEW


def test_send_hello_advances_state() -> None:
    ctx = _context()
    session = HandshakeSession(ctx)
    env = session.send_hello(0, "0" * 64)
    assert env.message_type == HELLO
    assert session.state == HandshakeState.SEND_HELLO


def test_handle_valid_hello() -> None:
    ctx = _context()
    session = HandshakeSession(ctx)
    hello = parse_envelope(serialize_envelope(HELLO, payload=_hello_payload()))
    session.handle_hello(hello)
    assert session.state == HandshakeState.VALIDATING
    assert session.peer_info is not None
    assert session.capabilities == PeerCapabilities(features=frozenset())


def test_handle_hello_wrong_network() -> None:
    ctx = _context()
    session = HandshakeSession(ctx)
    hello = parse_envelope(serialize_envelope(HELLO, payload=_hello_payload(network_id="wrong-net")))
    session.handle_hello(hello)
    assert session.state == HandshakeState.REJECTED
    assert session.reject_reason == "wrong network_id"


def test_handle_hello_wrong_genesis() -> None:
    ctx = _context()
    session = HandshakeSession(ctx)
    hello = parse_envelope(serialize_envelope(HELLO, payload=_hello_payload(genesis_hash="f" * 64)))
    session.handle_hello(hello)
    assert session.state == HandshakeState.REJECTED
    assert session.reject_reason == "wrong genesis_hash"


def test_handle_hello_unsupported_version() -> None:
    ctx = _context()
    session = HandshakeSession(ctx)
    hello = parse_envelope(serialize_envelope(HELLO, payload=_hello_payload(protocol_version=99)))
    session.handle_hello(hello)
    assert session.state == HandshakeState.REJECTED
    assert "unsupported protocol version" in (session.reject_reason or "")


def test_handle_hello_in_wrong_state() -> None:
    ctx = _context()
    session = HandshakeSession(ctx)
    session.transition_to(HandshakeState.VALIDATING)
    hello = parse_envelope(serialize_envelope(HELLO, payload=_hello_payload()))
    session.handle_hello(hello)
    assert session.state == HandshakeState.REJECTED


def test_handle_hello_ack_establishes() -> None:
    ctx = _context()
    session = HandshakeSession(ctx)
    session.send_hello(0, "0" * 64)
    hello = parse_envelope(serialize_envelope(HELLO, payload=_hello_payload()))
    session.handle_hello(hello)
    ack = parse_envelope(_ack_payload())
    session.handle_hello_ack(ack)
    assert session.state == HandshakeState.ESTABLISHED


def test_hello_ack_without_hello_rejected() -> None:
    ctx = _context()
    session = HandshakeSession(ctx)
    session.send_hello(0, "0" * 64)
    ack = parse_envelope(_ack_payload())
    session.handle_hello_ack(ack)
    assert session.state == HandshakeState.REJECTED


def test_unsolicited_hello_ack_when_waiting_for_hello() -> None:
    ctx = _context()
    session = HandshakeSession(ctx)
    ack = parse_envelope(_ack_payload())
    session.handle_hello(ack)  # wrong type
    assert session.state == HandshakeState.REJECTED


def test_build_hello_ack() -> None:
    ctx = _context()
    session = HandshakeSession(ctx)
    hello = parse_envelope(serialize_envelope(HELLO, payload=_hello_payload()))
    session.handle_hello(hello)
    ack = session.build_hello_ack(ok=True)
    assert ack.message_type == HELLO_ACK




def test_handle_hello_matching_features() -> None:
    ctx = _context()
    session = HandshakeSession(ctx)
    hello = parse_envelope(serialize_envelope(HELLO, payload=_hello_payload(features=LOCAL_FEATURES)))
    session.handle_hello(hello)
    assert session.capabilities == PeerCapabilities(features=frozenset(LOCAL_FEATURES))


def test_close() -> None:
    ctx = _context()
    session = HandshakeSession(ctx)
    session.send_hello(0, "0" * 64)
    session.close()
    assert session.state == HandshakeState.CLOSED
