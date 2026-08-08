"""Connection lifecycle and state management for transport."""

from __future__ import annotations

from enum import Enum, auto

from .errors import TransportClosedError, TransportStateError


class ConnectionState(Enum):
    """Finite set of connection states."""

    CREATED = auto()
    OPENING = auto()
    ACTIVE = auto()
    DRAINING = auto()
    CLOSED = auto()


class Connection:
    """Represents the local view of a transport connection.

    This class is intentionally lightweight. It only tracks the connection
    state machine and does not perform I/O.
    """

    _valid_transitions: dict[ConnectionState, set[ConnectionState]] = {
        ConnectionState.CREATED: {ConnectionState.OPENING, ConnectionState.CLOSED},
        ConnectionState.OPENING: {ConnectionState.ACTIVE, ConnectionState.CLOSED},
        ConnectionState.ACTIVE: {ConnectionState.DRAINING, ConnectionState.CLOSED},
        ConnectionState.DRAINING: {ConnectionState.CLOSED, ConnectionState.ACTIVE},
        ConnectionState.CLOSED: set(),
    }

    def __init__(self, connection_id: str) -> None:
        self.connection_id = connection_id
        self._state = ConnectionState.CREATED

    @property
    def state(self) -> ConnectionState:
        return self._state

    def transition_to(self, new_state: ConnectionState) -> None:
        """Move the connection to a new state if the transition is legal."""
        if new_state == self._state:
            return
        if new_state not in self._valid_transitions.get(self._state, set()):
            raise TransportStateError(
                f"invalid transition from {self._state.name} to {new_state.name}"
            )
        self._state = new_state

    def ensure_open(self) -> None:
        """Raise if the connection is not in an active/usable state."""
        if self._state not in {ConnectionState.ACTIVE, ConnectionState.OPENING}:
            if self._state == ConnectionState.CLOSED:
                raise TransportClosedError(f"connection {self.connection_id} is closed")
            raise TransportStateError(
                f"connection {self.connection_id} is not open (state={self._state.name})"
            )
