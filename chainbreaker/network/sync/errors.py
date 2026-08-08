"""Sync-layer exceptions."""

from __future__ import annotations

from chainbreaker.network.errors import NetworkError


class SyncError(NetworkError):
    """Base class for sync-layer errors."""


class SyncInvalidDataError(SyncError):
    """A peer sent data that failed consensus validation."""


class SyncTimeoutError(SyncError):
    """A sync operation exceeded its timeout."""


class SyncStorageError(SyncError):
    """Storage rejected a commit operation."""


class SyncPeerError(SyncError):
    """A sync peer misbehaved or disconnected."""
