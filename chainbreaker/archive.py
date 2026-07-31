
"""Content-addressed document archive."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, Iterator, Optional


class ArchiveError(ValueError):
    """Raised for archive misuse."""


@dataclass
class DocumentManifest:
    schema: str
    content_hash: str
    size: int
    media_type: str
    title: str
    language: Optional[str]
    source: Optional[str]
    provenance: Dict[str, Any]
    timestamp: int
    notes_hash: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class ContentArchive:
    """Store documents by SHA-256 content hash."""

    MAX_SIZE = 64 * 1024 * 1024  # 64 MiB

    def __init__(self, base_dir: Path):
        self.base_dir = Path(base_dir)
        self.objects_dir = self.base_dir / "objects"
        self.objects_dir.mkdir(parents=True, exist_ok=True)

    def _path(self, content_hash: str) -> Path:
        if len(content_hash) < 4:
            raise ArchiveError("invalid content hash")
        return self.objects_dir / content_hash[:2] / content_hash[2:4] / content_hash

    def store(self, content: bytes, manifest: DocumentManifest) -> DocumentManifest:
        if len(content) > self.MAX_SIZE:
            raise ArchiveError("document exceeds maximum size")
        content_hash = hashlib.sha256(content).hexdigest()
        if manifest.content_hash != content_hash:
            raise ArchiveError("manifest content hash does not match actual content")
        path = self._path(content_hash)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        with open(tmp, "wb") as f:
            f.write(content)
        tmp.replace(path)
        return manifest

    def retrieve(self, content_hash: str) -> Optional[bytes]:
        path = self._path(content_hash)
        if not path.exists():
            return None
        with open(path, "rb") as f:
            return f.read()

    def verify(self, content_hash: str) -> bool:
        data = self.retrieve(content_hash)
        if data is None:
            return False
        return hashlib.sha256(data).hexdigest() == content_hash

    def iter_hashes(self) -> Iterator[str]:
        for p in self.objects_dir.rglob("*"):
            if p.is_file() and not p.name.endswith(".tmp"):
                yield p.name
