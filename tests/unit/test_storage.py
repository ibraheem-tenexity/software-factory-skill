"""Storage adapter + blobs manifest — exercised against the local-filesystem fallback
(no Supabase creds), which is the dev/test path."""
import io
import json
import os
import pytest
from unittest.mock import patch, MagicMock

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


# ── SOF-50: re-fetch by full path (what a stored blobs.storage_key actually is) ─────────────
# storage_key is recorded as the FULL <scope_id>/<key> path (see blobs.record call sites in
# projects.py/org_service.py). Re-fetching with the two-arg scope_id+key form re-prefixes
# scope_id onto an already-full path — a real FileNotFoundError this caught in conversation_
# provider.py's image resolver. url_by_path/get_by_path take the full path as-is, no re-prefixing.

def test_get_by_path_resolves_a_full_storage_key_project_scoped(local):
    scope_id, key = "project-abc12345", "materials/spec.pdf"
    storage.put(scope_id, key, b"PDFDATA123")
    full_storage_key = f"{scope_id}/{key}"   # what blobs.record() actually persists
    assert storage.get_by_path(full_storage_key) == b"PDFDATA123"


def test_get_by_path_resolves_a_full_storage_key_org_scoped(local):
    # org-scoped storage uses a DIFFERENT scope_id convention ("org/<org_id>") than the blobs
    # table's own scope_id column (bare org_id) — get_by_path must not care, since it never
    # reconstructs the path from a scope_id at all.
    storage_scope_id, key = "org/org-9f", "kb/handbook.pdf"
    storage.put(storage_scope_id, key, b"HANDBOOK")
    full_storage_key = f"{storage_scope_id}/{key}"
    assert storage.get_by_path(full_storage_key) == b"HANDBOOK"


def test_url_by_path_does_not_reprefix_an_already_full_path(local):
    scope_id, key = "project-x", "materials/report.pdf"
    storage.put(scope_id, key, b"x")
    full_storage_key = f"{scope_id}/{key}"
    u = storage.url_by_path(full_storage_key)
    assert u == "file://" + os.path.join(str(local / "blobs"), full_storage_key)


def test_double_prefixing_the_old_buggy_way_really_does_404(local):
    # Regression anchor: confirms get(scope_id, full_storage_key) — the call pattern SOF-50 fixed
    # — genuinely 404s, so this test would have caught the original bug had it existed pre-fix.
    scope_id, key = "project-y", "materials/x.pdf"
    storage.put(scope_id, key, b"y")
    full_storage_key = f"{scope_id}/{key}"
    with pytest.raises(FileNotFoundError):
        storage.get(scope_id, full_storage_key)


def test_listing(local):
    storage.put("project-z", "a/1.txt", b"1")
    storage.put("project-z", "b/2.txt", b"2")
    assert storage.listing("project-z") == ["a/1.txt", "b/2.txt"]


def _mock_sign_response(signed_path: str):
    """Return a mock urlopen context manager that yields the sign endpoint response."""
    body = json.dumps({"signedURL": signed_path}).encode()
    cm = MagicMock()
    cm.__enter__ = MagicMock(return_value=MagicMock(read=MagicMock(return_value=body)))
    cm.__exit__ = MagicMock(return_value=False)
    return cm


def test_supabase_signed_url_shape(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://proj.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_KEY", "svc-key")
    monkeypatch.setenv("SF_STORAGE_BUCKET", "factory-run-blobs")
    assert storage.enabled() is True
    signed_path = "/object/sign/factory-run-blobs/project-x/qa/s.png?token=jwt123"
    with patch("urllib.request.urlopen", return_value=_mock_sign_response(signed_path)) as mock_open:
        result = storage.url("project-x", "qa/s.png")
    assert result == "https://proj.supabase.co/storage/v1" + signed_path
    # Verify the sign endpoint was called (not the old public URL)
    req = mock_open.call_args[0][0]
    assert "/object/sign/factory-run-blobs/project-x/qa/s.png" in req.full_url
    assert req.method == "POST"


def test_supabase_signed_url_uses_ttl(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://proj.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_KEY", "svc-key")
    monkeypatch.setenv("SF_STORAGE_BUCKET", "factory-run-blobs")
    monkeypatch.setenv("SF_STORAGE_URL_TTL", "86400")
    signed_path = "/object/sign/factory-run-blobs/project-x/f.txt?token=tok"
    with patch("urllib.request.urlopen", return_value=_mock_sign_response(signed_path)) as mock_open:
        storage.url("project-x", "f.txt")
    req = mock_open.call_args[0][0]
    body = json.loads(req.data)
    assert body["expiresIn"] == 86400


def test_supabase_signed_url_default_ttl(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://proj.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_KEY", "svc-key")
    monkeypatch.setenv("SF_STORAGE_BUCKET", "factory-run-blobs")
    monkeypatch.delenv("SF_STORAGE_URL_TTL", raising=False)
    signed_path = "/object/sign/factory-run-blobs/project-x/f.txt?token=tok"
    with patch("urllib.request.urlopen", return_value=_mock_sign_response(signed_path)) as mock_open:
        storage.url("project-x", "f.txt")
    req = mock_open.call_args[0][0]
    body = json.loads(req.data)
    assert body["expiresIn"] == 315360000  # 10 years


def test_sha256(local):
    import hashlib
    assert storage.sha256(b"abc") == hashlib.sha256(b"abc").hexdigest()


# -- manifest ---------------------------------------------------------------------------
@pytest.fixture()
def store(tmp_path, monkeypatch):
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
