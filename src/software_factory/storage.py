"""Run/org blob storage — Supabase Storage when configured, local filesystem otherwise.

The immediate need is durable QA screenshot URLs (a bug report bounced to a ticket's
`description` links `![](<url>)` images that must outlive the workspace). The same adapter
also carries logs/artifacts off the `/data` volume (ARCHITECTURE §6).

Two scopes share one bucket: run-scoped `<project_id>/<kind>/<file>` and org-scoped
`org/<org_id>/<kind>/<file>`. Callers pass `scope_id` (e.g. "project-abc123" or "org/org-9f")
and a `key` (e.g. "qa/ticket-3-1718.png"); the object path is `<scope_id>/<key>`.

Env-gated, mirroring `notify`: with `SUPABASE_URL` + `SUPABASE_SERVICE_KEY`
+ `SF_STORAGE_BUCKET` set, uploads go to Supabase Storage via its REST API using the
*project-scoped* service key (a console-side secret — agents never get an account-wide
Supabase token). The bucket is PRIVATE; url() mints a long-lived signed URL via the
Supabase sign endpoint (POST /storage/v1/object/sign/{bucket}/{obj}) so objects are
accessible in external tools (tickets, email) without requiring auth.
TTL is configurable via SF_STORAGE_URL_TTL (default 315360000 s = 10 years).
Without credentials it falls back to a local directory (`SF_BLOB_DIR`, default `./.blobs`),
so dev and the hermetic test suite work with no credentials.
"""
from __future__ import annotations

import hashlib
import json
import mimetypes
import os
import urllib.error
import urllib.request

from .log import get_logger

logger = get_logger(__name__)


def enabled() -> bool:
    """True when Supabase Storage is configured; else the local-filesystem fallback is used."""
    return bool(os.environ.get("SUPABASE_URL") and os.environ.get("SUPABASE_SERVICE_KEY")
                and os.environ.get("SF_STORAGE_BUCKET"))


def _object_path(scope_id: str, key: str) -> str:
    return f"{scope_id.strip('/')}/{key.strip('/')}"


def _local_root() -> str:
    return os.environ.get("SF_BLOB_DIR") or os.path.join(os.getcwd(), ".blobs")


def _ttl() -> int:
    return int(os.environ.get("SF_STORAGE_URL_TTL", "315360000") or "315360000")


def _as_bytes(data) -> bytes:
    """`data` is raw bytes, or a filesystem path (str) to read."""
    if isinstance(data, (bytes, bytearray)):
        return bytes(data)
    with open(data, "rb") as f:
        return f.read()


def url_by_path(obj: str) -> str:
    """Signed retrieval URL for an object at its full bucket-relative path (does not upload).
    For callers that already hold the full path — e.g. `blobs.storage_key`, which every writer
    records as the complete `<scope_id>/<key>` path (see `put`) — so it must NOT be re-prefixed
    with a scope_id a second time (that was SOF-50: FileNotFoundError on re-fetch). `url`/`get`
    below are for callers that only have scope_id + key separately; they delegate here.
    POSTs to the Supabase sign endpoint to mint a long-lived bearer-token URL
    (TTL from SF_STORAGE_URL_TTL, default 10 years). Falls back to file:// when
    storage is not configured."""
    if enabled():
        base = os.environ["SUPABASE_URL"].rstrip("/")
        bucket = os.environ["SF_STORAGE_BUCKET"]
        endpoint = f"{base}/storage/v1/object/sign/{bucket}/{obj}"
        body = json.dumps({"expiresIn": _ttl()}).encode()
        req = urllib.request.Request(
            endpoint, data=body, method="POST",
            headers={"apikey": os.environ["SUPABASE_SERVICE_KEY"],
                     "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                signed_path = json.loads(r.read())["signedURL"]
        except Exception:
            logger.exception("[storage] signing URL failed for %s — object URL unavailable "
                             "(egress/quota 402 or upstream error)", obj)
            raise
        return f"{base}/storage/v1{signed_path}"
    return "file://" + os.path.join(_local_root(), obj)


def url(scope_id: str, key: str) -> str:
    """Signed retrieval URL for an object addressed by scope_id + key (see `url_by_path` for the
    full-path variant, which is what a stored `storage_key` needs)."""
    return url_by_path(_object_path(scope_id, key))


def put(scope_id: str, key: str, data) -> str:
    """Store bytes (or a file at the given path) at `<scope_id>/<key>`; return its URL."""
    obj = _object_path(scope_id, key)
    raw = _as_bytes(data)
    content_type = mimetypes.guess_type(key)[0] or "application/octet-stream"
    try:
        if enabled():
            base = os.environ["SUPABASE_URL"].rstrip("/")
            bucket = os.environ["SF_STORAGE_BUCKET"]
            endpoint = f"{base}/storage/v1/object/{bucket}/{obj}"
            req = urllib.request.Request(
                endpoint, data=raw, method="POST",
                headers={"apikey": os.environ["SUPABASE_SERVICE_KEY"],
                         "Content-Type": content_type, "x-upsert": "true"})
            with urllib.request.urlopen(req, timeout=30):
                pass
        else:
            dest = os.path.join(_local_root(), obj)
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            with open(dest, "wb") as f:
                f.write(raw)
    except Exception:
        logger.exception("[storage] upload failed for %s (%d bytes) — object not stored "
                         "(egress/quota 402 or upstream error)", obj, len(raw))
        raise
    return url_by_path(obj)


def get_by_path(obj: str) -> bytes:
    """Fetch an object's bytes at its full bucket-relative path — see `url_by_path`."""
    try:
        if enabled():
            base = os.environ["SUPABASE_URL"].rstrip("/")
            bucket = os.environ["SF_STORAGE_BUCKET"]
            endpoint = f"{base}/storage/v1/object/{bucket}/{obj}"
            req = urllib.request.Request(
                endpoint, headers={"apikey": os.environ["SUPABASE_SERVICE_KEY"]})
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.read()
        with open(os.path.join(_local_root(), obj), "rb") as f:
            return f.read()
    except Exception:
        logger.exception("[storage] download failed for %s (egress/quota 402 or upstream error)", obj)
        raise


def get(scope_id: str, key: str) -> bytes:
    """Fetch an object's bytes addressed by scope_id + key (see `get_by_path` for the full-path
    variant, which is what a stored `storage_key` needs)."""
    return get_by_path(_object_path(scope_id, key))


def delete_by_path(obj: str) -> None:
    """Delete one object at its full bucket-relative path. Missing objects are already gone."""
    if enabled():
        base = os.environ["SUPABASE_URL"].rstrip("/")
        bucket = os.environ["SF_STORAGE_BUCKET"]
        endpoint = f"{base}/storage/v1/object/{bucket}/{obj}"
        req = urllib.request.Request(endpoint, method="DELETE",
                                     headers={"apikey": os.environ["SUPABASE_SERVICE_KEY"]})
        try:
            with urllib.request.urlopen(req, timeout=30):
                pass
        except urllib.error.HTTPError as exc:
            if exc.code != 404:
                raise
        return
    try:
        os.remove(os.path.join(_local_root(), obj))
    except FileNotFoundError:
        pass


def get_by_url(url: str) -> bytes:
    """Fetch an object's bytes given the URL `put()`/`url_by_path()` returned — a `file://` URL
    (local fallback) or a Supabase signed `https://` URL (works with a plain GET, no auth headers;
    the token is embedded in the query string). For callers that only kept the URL a writer
    returned, not the original scope_id/key/path."""
    try:
        if url.startswith("file://"):
            with open(url[len("file://"):], "rb") as f:
                return f.read()
        with urllib.request.urlopen(url, timeout=30) as r:
            return r.read()
    except Exception:
        # Strip the query string: a Supabase signed URL carries its bearer token there.
        logger.exception("[storage] download-by-url failed for %s", url.split("?", 1)[0])
        raise


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
