"""Storage adapter + blobs manifest — exercised against the local-filesystem fallback
(no Supabase creds), which is the dev/test path."""
import pytest

from software_factory import storage
from software_factory.blobs import BlobStore


@pytest.fixture()
def local(tmp_path, monkeypatch):
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_SERVICE_KEY", raising=False)
    monkeypatch.delenv("SF_STORAGE_BUCKET", raising=False)
    monkeypatch.setenv("SF_BLOB_DIR", str(tmp_path / "blobs"))
    return tmp_path


def test_disabled_without_creds(local):
    assert storage.enabled() is False


def test_put_get_roundtrip_bytes(local):
    u = storage.put("project-abc12345", "qa/ticket-3.png", b"\x89PNG fake")
    assert u.startswith("file://")
    assert storage.get("project-abc12345", "qa/ticket-3.png") == b"\x89PNG fake"


def test_put_from_file_path(local, tmp_path):
    p = tmp_path / "shot.png"
    p.write_bytes(b"imagedata")
    storage.put("project-abc12345", "qa/shot.png", str(p))
    assert storage.get("project-abc12345", "qa/shot.png") == b"imagedata"


def test_org_scope_path(local):
    u = storage.put("org/org-9f", "business-process/walkthrough.txt", b"hi")
    assert "org/org-9f/business-process/walkthrough.txt" in u


def test_url_does_not_upload(local):
    u = storage.url("project-x", "k.txt")
    assert u.startswith("file://")
    with pytest.raises(FileNotFoundError):
        storage.get("project-x", "k.txt")


def test_listing(local):
    storage.put("project-z", "a/1.txt", b"1")
    storage.put("project-z", "b/2.txt", b"2")
    assert storage.listing("project-z") == ["a/1.txt", "b/2.txt"]


def test_supabase_public_url_shape(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://proj.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_KEY", "svc-key")
    monkeypatch.setenv("SF_STORAGE_BUCKET", "factory-run-blobs")
    assert storage.enabled() is True
    assert storage.url("project-x", "qa/s.png") == (
        "https://proj.supabase.co/storage/v1/object/public/factory-run-blobs/project-x/qa/s.png")


def test_sha256(local):
    import hashlib
    assert storage.sha256(b"abc") == hashlib.sha256(b"abc").hexdigest()


# -- manifest ---------------------------------------------------------------------------
@pytest.fixture()
def store(tmp_path, monkeypatch):
    monkeypatch.delenv("SF_DB", raising=False)
    return BlobStore()


def test_record_and_list(store):
    store.record("project", "project-abc12345", "project-abc12345/qa/t3.png", kind="qa-screenshot",
                 content_type="image/png", size_bytes=9, sha256="deadbeef")
    store.record("org", "org-9f", "org/org-9f/business-process/v.mp4",
                 kind="business-process-video")
    runs = store.list_for("project", "project-abc12345")
    assert len(runs) == 1 and runs[0]["kind"] == "qa-screenshot"
    assert runs[0]["storage_key"] == "project-abc12345/qa/t3.png"
    orgs = store.list_for("org", "org-9f")
    assert len(orgs) == 1 and orgs[0]["kind"] == "business-process-video"


def test_record_rejects_bad_scope(store):
    with pytest.raises(ValueError):
        store.record("nonsense", "x", "x/y")
