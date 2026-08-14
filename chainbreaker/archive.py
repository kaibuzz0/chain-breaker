"""Content-addressed document archive with signed manifests."""
from __future__ import annotations

import json
import zlib
from pathlib import Path
from typing import Any

from .block import NETWORK_ID
from .codec import validate_scripture_body
from .crypto import HashEngine
from .storage.filesystem import atomic_write, fsync_dir


class Archive:
    """Local content-addressed archive."""
    def __init__(self, base_dir: str):
        self.base_dir = Path(base_dir)
        self.objects_dir = self.base_dir / "objects"
        self.objects_dir.mkdir(parents=True, exist_ok=True)
        self.manifests_dir = self.base_dir / "manifests"
        self.manifests_dir.mkdir(parents=True, exist_ok=True)
    def _object_path(self, content_hash: str) -> Path:
        if len(content_hash) < 4:
            raise ValueError("content_hash too short")
        return self.objects_dir / content_hash[:2] / content_hash[2:4] / content_hash
    def add_document(self,
                     data: bytes,
                     title: str,
                     media_type: str = "application/octet-stream",
                     language: str | None = None,
                     source: str | None = None,
                     source_uri: str | None = None,
                     acquisition_date: int | None = None,
                     license: str | None = None,
                     parent_hash: str | None = None,
                     notes_hash: str | None = None,
                     metadata: dict[str, Any] | None = None) -> str:
        if not isinstance(data, bytes):
            raise TypeError("data must be bytes")
        content_hash = HashEngine.hash_single_hex(data)
        obj_path = self._object_path(content_hash)
        compressed = zlib.compress(data, level=6)
        atomic_write(obj_path, compressed)
        fsync_dir(obj_path.parent.parent)
        metadata_blob = HashEngine.canonical_json(metadata) if metadata else b"{}"
        metadata_hash = HashEngine.hash_single_hex(metadata_blob)
        manifest = {
            "schema": "chainbreaker-manifest-v1",
            "network_id": NETWORK_ID,
            "schema_version": 1,
            "content_hash": content_hash,
            "byte_length": len(data),
            "media_type": media_type,
            "title": title,
            "language": language,
            "source": source,
            "source_uri": source_uri,
            "acquisition_date": acquisition_date,
            "license": license,
            "parent_hash": parent_hash,
            "metadata_hash": metadata_hash,
            "notes_hash": notes_hash,
        }
        validate_scripture_body(manifest)
        manifest_bytes = HashEngine.canonical_json(manifest)
        manifest_hash = HashEngine.hash_single_hex(manifest_bytes)
        mpath = self.manifests_dir / manifest_hash
        atomic_write(mpath, manifest_bytes)
        fsync_dir(self.manifests_dir)
        return manifest_hash
    def get_manifest(self, manifest_hash: str) -> dict[str, Any]:
        mpath = self.manifests_dir / manifest_hash
        with open(mpath, "rb") as f:
            data = f.read()
        manifest: dict[str, Any] = json.loads(data.decode("utf-8"))
        validate_scripture_body(manifest)
        return manifest
    def get_document(self, content_hash: str, *, verify: bool = True) -> bytes:
        obj_path = self._object_path(content_hash)
        with open(obj_path, "rb") as f:
            compressed = f.read()
        data = zlib.decompress(compressed)
        if verify and HashEngine.hash_single_hex(data) != content_hash:
            raise ValueError(f"content hash mismatch for {content_hash}: object is corrupt or was replaced")
        return data

    def get_document_unverified(self, content_hash: str) -> bytes:
        """Return raw decompressed bytes without checking the content hash.

        This is intentionally named to make the absence of verification obvious.
        It exists only for callers that already have an independent integrity
        guarantee (e.g. a verified manifest binding checked separately).
        """
        return self.get_document(content_hash, verify=False)
    def verify_manifest(self, manifest_hash: str) -> bool:
        """Return True only if stored manifest bytes hash to manifest_hash.

        This is a fast manifest-only check. For a full manifest+content binding
        check, use verify_document().
        """
        try:
            mpath = self.manifests_dir / manifest_hash
            stored_bytes = mpath.read_bytes()
            manifest = json.loads(stored_bytes.decode("utf-8"))
            validate_scripture_body(manifest)
            return HashEngine.hash_single_hex(stored_bytes) == manifest_hash
        except Exception:
            return False

    def verify_document(self, manifest_hash: str) -> dict[str, Any]:
        """Verify a manifest and its referenced content as one binding.

        Raises ValueError if the manifest is missing, its bytes do not match
        the hash, its schema is invalid, its referenced object is missing,
        the object's bytes do not hash to content_hash, or the decompressed
        length differs from byte_length.

        Returns the validated manifest dict on success.
        """
        mpath = self.manifests_dir / manifest_hash
        stored_bytes = mpath.read_bytes()
        if HashEngine.hash_single_hex(stored_bytes) != manifest_hash:
            raise ValueError(f"manifest hash mismatch for {manifest_hash}")
        manifest: dict[str, Any] = json.loads(stored_bytes.decode("utf-8"))
        validate_scripture_body(manifest)

        content_hash = manifest["content_hash"]
        data = self.get_document(content_hash)
        if len(data) != manifest["byte_length"]:
            raise ValueError(
                f"content length mismatch for {manifest_hash}: "
                f"expected {manifest['byte_length']}, got {len(data)}"
            )
        return manifest

    def get_verified_document(self, manifest_hash: str) -> tuple[dict[str, Any], bytes]:
        """Return (manifest, content) after verifying the full binding."""
        manifest = self.verify_document(manifest_hash)
        content = self.get_document(manifest["content_hash"])
        return manifest, content
# Top-level convenience aliases
def make_manifest(schema: str, title: str, language: str, source_url: str,
                    source_date: str, canon_tier: str, documents: dict[str, bytes]) -> dict[str, Any]:
    """Create a canonical scripture manifest."""
    import json
    import time

    from .crypto import HashEngine
    doc_hashes = {}
    for name, data in documents.items():
        doc_hashes[name] = HashEngine.hash_single_hex(data)
    manifest = {
        "schema": schema,
        "title": title,
        "language": language,
        "source_url": source_url,
        "source_date": source_date,
        "canon_tier": canon_tier,
        "created_at": int(time.time()),
        "document_hashes": doc_hashes,
    }
    canonical = json.dumps(manifest, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    manifest["manifest_hash"] = HashEngine.hash_single_hex(canonical.encode("utf-8"))
    return manifest
def store_manifest(base_dir: str, manifest: dict[str, Any]) -> str:
    """Store the canonical manifest bytes in an Archive and return its hash."""
    import json
    body = dict(manifest)
    body.pop("manifest_hash", None)
    canonical = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    archive = Archive(base_dir)
    return archive.add_document(canonical.encode("utf-8"), title=body.get("title", "manifest"))
def load_manifest(base_dir: str, manifest_hash: str) -> dict[str, Any]:
    """Load a manifest from an Archive."""
    archive = Archive(base_dir)
    return archive.get_manifest(manifest_hash)
def verify_manifest(base_dir: str, manifest_hash: str) -> bool:
    """Verify a stored manifest hash matches its canonical bytes."""
    archive = Archive(base_dir)
    return archive.verify_manifest(manifest_hash)
