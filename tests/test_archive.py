
import os
import tempfile

from chainbreaker.archive import ContentArchive, DocumentManifest


def test_archive_store_and_verify():
    with tempfile.TemporaryDirectory() as td:
        archive = ContentArchive(td)
        content = b"In the beginning was the Word."
        manifest = DocumentManifest(
            schema="chainbreaker-manifest-v1",
            content_hash="",
            size=len(content),
            media_type="text/plain",
            title="Test document",
            language="en",
            source="test",
            provenance={},
            timestamp=1,
        )
        import hashlib
        manifest.content_hash = hashlib.sha256(content).hexdigest()
        stored = archive.store(content, manifest)
        assert stored.content_hash == manifest.content_hash
        assert archive.verify(stored.content_hash)
        assert archive.retrieve(stored.content_hash) == content
