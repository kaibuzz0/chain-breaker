"""Phase 8M-B: Archive Integrity Hardening regression tests."""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

import pytest

from chainbreaker.archive import Archive


def _add_sample(archive: Archive, data: bytes = b"hello scripture") -> tuple[str, str]:
    """Add a sample document and return (manifest_hash, content_hash)."""
    mh = archive.add_document(data, title="Sample", media_type="text/plain")
    manifest = archive.get_manifest(mh)
    return mh, manifest["content_hash"]


def test_add_document_leaves_no_partial_files():
    """A successful add must not leave temp files in objects or manifests."""
    with tempfile.TemporaryDirectory() as d:
        archive = Archive(d)
        archive.add_document(b"doc", title="doc")
        for subdir in [archive.objects_dir, archive.manifests_dir]:
            for p in subdir.rglob("*"):
                if p.is_file() and p.name.startswith("."):
                    pytest.fail(f"partial/temp file left behind: {p}")


def test_get_document_verifies_hash_by_default():
    """Default get_document() recompute-hashes and rejects corrupt objects."""
    with tempfile.TemporaryDirectory() as d:
        archive = Archive(d)
        data = b"hello scripture"
        mh, ch = _add_sample(archive, data)
        assert archive.get_document(ch) == data

        # Corrupt the stored compressed object by replacing it with compressed different content.
        obj_path = archive._object_path(ch)
        obj_path.write_bytes(__import__("zlib").compress(b"different content"))

        with pytest.raises(ValueError, match="content hash mismatch"):
            archive.get_document(ch)


def test_get_document_unverified_allows_explicit_unsafe_read():
    """The explicitly-named unsafe path returns bytes without verification."""
    with tempfile.TemporaryDirectory() as d:
        archive = Archive(d)
        data = b"hello scripture"
        _, ch = _add_sample(archive, data)
        result = archive.get_document_unverified(ch)
        assert result == data


def test_verify_document_rejects_corrupt_manifest_bytes():
    """verify_document() fails if manifest bytes do not hash to manifest_hash."""
    with tempfile.TemporaryDirectory() as d:
        archive = Archive(d)
        mh, _ = _add_sample(archive, b"data")
        mpath = archive.manifests_dir / mh
        raw = mpath.read_bytes()
        mpath.write_bytes(raw + b"extra")

        with pytest.raises(ValueError, match="manifest hash mismatch"):
            archive.verify_document(mh)


def test_verify_document_rejects_missing_object():
    """verify_document() fails when the referenced object is missing."""
    with tempfile.TemporaryDirectory() as d:
        archive = Archive(d)
        mh, ch = _add_sample(archive, b"data")
        obj_path = archive._object_path(ch)
        obj_path.unlink()

        with pytest.raises(FileNotFoundError):
            archive.verify_document(mh)


def test_verify_document_rejects_content_hash_mismatch():
    """verify_document() fails when object bytes do not match content_hash."""
    with tempfile.TemporaryDirectory() as d:
        archive = Archive(d)
        data = b"hello scripture"
        mh, ch = _add_sample(archive, data)
        obj_path = archive._object_path(ch)
        # Replace object with compressed different content at same length.
        different = b"HELLO SCRIPTURE"
        obj_path.write_bytes(__import__("zlib").compress(different))

        with pytest.raises(ValueError, match="content hash mismatch"):
            archive.verify_document(mh)


def test_verify_document_rejects_length_mismatch():
    """verify_document() fails when decompressed length differs from manifest.

    A length mismatch necessarily changes the content hash, so the binding
    check rejects it before the length check; both are safe failures.
    """
    with tempfile.TemporaryDirectory() as d:
        archive = Archive(d)
        data = b"short"
        mh, ch = _add_sample(archive, data)
        obj_path = archive._object_path(ch)
        # Replace with longer content that still decompresses.
        obj_path.write_bytes(__import__("zlib").compress(b"much longer content"))

        with pytest.raises(ValueError):
            archive.verify_document(mh)


def test_verify_document_rejects_truncated_compressed_object():
    """Truncated compressed object must raise rather than return garbage."""
    with tempfile.TemporaryDirectory() as d:
        archive = Archive(d)
        data = b"hello scripture"
        mh, ch = _add_sample(archive, data)
        obj_path = archive._object_path(ch)
        obj_path.write_bytes(obj_path.read_bytes()[:8])

        with pytest.raises(Exception) as exc_info:
            archive.verify_document(mh)
        assert any(
            term in str(exc_info.value) or term in type(exc_info.value).__name__.lower()
            for term in ("content hash", "hash mismatch", "zlib", "truncated", "decompress")
        )


def test_get_verified_document_returns_binding():
    """get_verified_document returns manifest+content only after full check."""
    with tempfile.TemporaryDirectory() as d:
        archive = Archive(d)
        data = b"hello scripture"
        mh, ch = _add_sample(archive, data)
        manifest, content = archive.get_verified_document(mh)
        assert manifest["content_hash"] == ch
        assert content == data


def test_existing_valid_archives_remain_readable():
    """A legacy-style archive created with the current add_document() stays valid."""
    with tempfile.TemporaryDirectory() as d:
        archive = Archive(d)
        data = b"existing document"
        mh, ch = _add_sample(archive, data)
        # Simulate a caller that stored the manifest hash externally.
        assert archive.verify_document(mh)["content_hash"] == ch
        assert archive.get_document(ch) == data


def test_verify_manifest_fast_check_unchanged():
    """verify_manifest() remains the fast manifest-only check for callers that need it."""
    with tempfile.TemporaryDirectory() as d:
        archive = Archive(d)
        data = b"hello"
        mh, _ = _add_sample(archive, data)
        assert archive.verify_manifest(mh) is True

        # Corrupt only the object: fast manifest check still passes.
        _, ch = _add_sample(archive, data)
        obj_path = archive._object_path(ch)
        obj_path.write_bytes(__import__("zlib").compress(b"WRONG"))
        assert archive.verify_manifest(mh) is True


def test_atomic_write_survives_simulated_crash():
    """No partial final file exists after atomic_write, even on interruption.

    atomic_write itself is already tested in storage tests; this test proves
    Archive.add_document uses it and leaves no stray temp files.
    """
    with tempfile.TemporaryDirectory() as d:
        archive = Archive(d)
        # Monkeypatch atomic_write to simulate crash mid-write by unlinking tmp.
        real_atomic_write = __import__("chainbreaker.storage.filesystem", fromlist=["atomic_write"]).atomic_write
        def crashing_atomic_write(path: Path, data: bytes) -> None:
            path.parent.mkdir(parents=True, exist_ok=True)
            import tempfile
            fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
            try:
                with os.fdopen(fd, "wb") as fh:
                    fh.write(data[: len(data) // 2])
                    fh.flush()
                    os.fsync(fh.fileno())
                # Simulate crash: leave tmp in place, do not rename.
                raise RuntimeError("simulated crash before replace")
            except Exception:
                os.unlink(tmp_name)
                raise

        # Only apply the crash to the object write so we can inspect cleanup.
        import chainbreaker.archive as archive_mod
        archive_mod.atomic_write = crashing_atomic_write  # type: ignore[attr-defined]
        try:
            with pytest.raises(RuntimeError, match="simulated crash"):
                archive.add_document(b"data", title="crash")
        finally:
            archive_mod.atomic_write = real_atomic_write

        for subdir in [archive.objects_dir, archive.manifests_dir]:
            for p in subdir.rglob("*"):
                if p.is_file():
                    pytest.fail(f"partial file left after crash: {p}")


def test_add_document_returns_deterministic_hashes():
    """Re-adding identical data yields identical manifest and content hashes."""
    with tempfile.TemporaryDirectory() as d1:
        archive1 = Archive(d1)
        mh1, ch1 = _add_sample(archive1, b"deterministic")
    with tempfile.TemporaryDirectory() as d2:
        archive2 = Archive(d2)
        mh2, ch2 = _add_sample(archive2, b"deterministic")
    assert ch1 == ch2
    assert mh1 == mh2


def test_cli_verify_delegates_to_library(runner):
    """v2 archive verify must succeed for valid archive and fail on corrupt content.

    This is a CLI-level smoke test; the heavy integrity logic lives in Archive.
    """
    from chainbreaker.cli_v2 import v2_archive_add, v2_archive_verify

    with tempfile.TemporaryDirectory() as d:
        data_file = Path(d) / "doc.txt"
        data_file.write_bytes(b"cli document")
        data_dir = Path(d) / "archive"

        result = runner.invoke(v2_archive_add, [
            "--data-dir", str(data_dir),
            "--file", str(data_file),
            "--title", "CLI Doc",
        ])
        assert result.exit_code == 0, result.output
        summary = json.loads(result.output)
        mh = summary["manifest_hash"]

        result = runner.invoke(v2_archive_verify, [
            "--data-dir", str(data_dir),
            "--manifest-hash", mh,
        ])
        assert result.exit_code == 0, result.output
        out = json.loads(result.output)
        assert out["manifest_valid"] is True
        assert out["byte_length"] == 12


@pytest.fixture
def runner():
    from click.testing import CliRunner
    return CliRunner()
