
import tempfile

from chainbreaker.archive import Archive


def test_archive_roundtrip():
    with tempfile.TemporaryDirectory() as d:
        archive = Archive(d)
        data = b"hello scripture"
        mh = archive.add_document(data, title="Hello", media_type="text/plain")
        manifest = archive.get_manifest(mh)
        assert manifest["byte_length"] == len(data)
        assert manifest["content_hash"] is not None
        assert archive.get_document(manifest["content_hash"]) == data
        assert archive.verify_manifest(mh)
