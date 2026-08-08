from __future__ import annotations

import pytest

from chainbreaker.network.transport import (
    Connection,
    ConnectionState,
    TransportClosedError,
    TransportStateError,
)


def _state(c: Connection) -> ConnectionState:
    return c.state


def test_created_to_opening() -> None:
    c = Connection("x")
    assert _state(c) is ConnectionState.CREATED
    c.transition_to(ConnectionState.OPENING)
    assert _state(c) is ConnectionState.OPENING


def test_opening_to_active() -> None:
    c = Connection("x")
    c.transition_to(ConnectionState.OPENING)
    c.transition_to(ConnectionState.ACTIVE)
    assert _state(c) is ConnectionState.ACTIVE


def test_active_to_draining() -> None:
    c = Connection("x")
    c.transition_to(ConnectionState.OPENING)
    c.transition_to(ConnectionState.ACTIVE)
    c.transition_to(ConnectionState.DRAINING)
    assert _state(c) is ConnectionState.DRAINING


def test_draining_to_closed() -> None:
    c = Connection("x")
    c.transition_to(ConnectionState.OPENING)
    c.transition_to(ConnectionState.ACTIVE)
    c.transition_to(ConnectionState.DRAINING)
    c.transition_to(ConnectionState.CLOSED)
    assert _state(c) is ConnectionState.CLOSED


def test_invalid_transition_raises() -> None:
    c = Connection("x")
    with pytest.raises(TransportStateError):
        c.transition_to(ConnectionState.DRAINING)


def test_closed_cannot_reopen() -> None:
    c = Connection("x")
    c.transition_to(ConnectionState.OPENING)
    c.transition_to(ConnectionState.ACTIVE)
    c.transition_to(ConnectionState.CLOSED)
    with pytest.raises(TransportStateError):
        c.transition_to(ConnectionState.ACTIVE)


def test_ensure_open_rejects_closed() -> None:
    c = Connection("x")
    c.transition_to(ConnectionState.OPENING)
    c.transition_to(ConnectionState.ACTIVE)
    c.transition_to(ConnectionState.CLOSED)
    with pytest.raises(TransportClosedError):
        c.ensure_open()
