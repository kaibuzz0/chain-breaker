"""Deterministic failpoint mechanism for storage tests."""

from __future__ import annotations

from typing import Callable


class FailpointController:
    """Invoke a registered callback when a named failpoint is reached.

    Each failpoint may be armed once or persistently. Use this to simulate
    crashes at specific stages of the storage commit path.
    """

    def __init__(self) -> None:
        self._handlers: dict[str, Callable[[], None] | None] = {}

    def arm(self, name: str, handler: Callable[[], None]) -> None:
        """Arm a failpoint so the next time `name` is reached `handler` runs."""
        self._handlers[name] = handler

    def fire(self, name: str) -> None:
        """Fire the failpoint if armed, then disarm it."""
        handler = self._handlers.get(name)
        if handler is not None:
            del self._handlers[name]
            handler()

    def is_armed(self, name: str) -> bool:
        return name in self._handlers
