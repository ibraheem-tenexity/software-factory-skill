"""Run/org blob storage — Supabase Storage when configured, local filesystem otherwise.

The immediate need is durable QA screenshot URLs (a bug report bounced to a ticket's
`description` links `![](<url>)` images that must outlive the workspace). The same adapter
later carries inputs/logs/artifacts off the `/data` volume (ARCHITECTURE §6).

Two scopes share one bucket: run-scoped `<run_id>/<kind>/<file>` and org-scoped
`org/<org_id>/<kind>/<file>`. Callers pass `scope_id` (e.g. "run-abc123" or "org/org-9f")
and a `key` (e.g. "qa/ticket-3-1718.png"); the object path is `<scope_id>/<key>`.

Env-gated, mirroring `notify`/`tracing`: with `SUPABASE_URL` + `SUPABASE_SERVICE_KEY`
+ `SF_STORAGE_BUCKET` set, uploads go to Supabase Storage via its REST API using the
*project-scoped* service key (a console-side secret — agents never get an account-wide
Supabase token). Without them it falls back to a local directory (`SF_BLOB_DIR`, default
`./.blobs`), so dev and the hermetic test suite work with no credentials.
"""
from __future__ import annotations

import hashlib
import mimetypes
import os
import urllib.request


def enabled() -> bool:
    """True when Supabase Storage is configured; else the local-filesystem fallback is used."""
    return bool(os.environ.get("SUPABASE_URL") and os.environ.get("SUPABASE_SERVICE_KEY")
                and os.environ.get("SF_STORAGE_BUCKET"))


def _object_path(scope_id: str, key: str) -> str:
    return f"{scope_id.strip('/')}/{key.strip('/')}"


def _local_root() -> str:
    return os.environ.get("SF_BLOB_DIR") or os.path.join(os.getcwd(), ".blobs")


def _as_bytes(data) -> bytes:
    """`data` is raw bytes, or a filesystem path (str) to read."""
    if isinstance(data, (bytes, bytearray)):
        return bytes(data)
    with open(data, "rb") as f:
        return f.read()


def url(scope_id: str, key: str) -> str:
    """The retrieval URL for an object (does not upload). Supabase public-object URL when
    configured, else a file:// URL into the local fallback root."""
    obj = _object_path(scope_id, key)
    if enabled():
        base = os.environ["SUPABASE_URL"].rstrip("/")
        bucket = os.environ["SF_STORAGE_BUCKET"]
        return f"{base}/storage/v1/object/public/{bucket}/{obj}"
    return "file://" + os.path.join(_local_root(), obj)


def put(scope_id: str, key: str, data) -> str:
    """Store bytes (or a file at the given path) at `<scope_id>/<key>`; return its URL."""
    obj = _object_path(scope_id, key)
    raw = _as_bytes(data)
    content_type = mimetypes.guess_type(key)[0] or "application/octet-stream"
    if enabled():
        base = os.environ["SUPABASE_URL"].rstrip("/")
        bucket = os.environ["SF_STORAGE_BUCKET"]
        endpoint = f"{base}/storage/v1/object/{bucket}/{obj}"
        req = urllib.request.Request(
            endpoint, data=raw, method="POST",
            headers={"Authorization": f"Bearer {os.environ['SUPABASE_SERVICE_KEY']}",
                     "Content-Type": content_type, "x-upsert": "true"})
        with urllib.request.urlopen(req, timeout=30):
            pass
    else:
        dest = os.path.join(_local_root(), obj)
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        with open(dest, "wb") as f:
            f.write(raw)
    return url(scope_id, key)


def get(scope_id: str, key: str) -> bytes:
    obj = _object_path(scope_id, key)
    if enabled():
        base = os.environ["SUPABASE_URL"].rstrip("/")
        bucket = os.environ["SF_STORAGE_BUCKET"]
        endpoint = f"{base}/storage/v1/object/{bucket}/{obj}"
        req = urllib.request.Request(
            endpoint, headers={"Authorization": f"Bearer {os.environ['SUPABASE_SERVICE_KEY']}"})
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.read()
    with open(os.path.join(_local_root(), obj), "rb") as f:
        return f.read()


def listing(scope_id: str) -> list[str]:
    """Object keys (relative to `scope_id`) stored under a scope. Local fallback only walks
    the directory; the Supabase listing is left to the manifest (BlobStore) which is the
    durable index of what was written."""
    if enabled():
        return []
    root = os.path.join(_local_root(), scope_id.strip("/"))
    out = []
    for dirpath, _dirs, files in os.walk(root):
        for name in files:
            out.append(os.path.relpath(os.path.join(dirpath, name), root))
    return sorted(out)


def sha256(data) -> str:
    return hashlib.sha256(_as_bytes(data)).hexdigest()
