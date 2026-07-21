"""Codebase discovery (CBT-6/7): point one headless agent at an org's repo and let it write
AGENTS.md / CLAUDE.md / integrations.md describing framework, commands, integrations, and
conventions — then land those three files as org-scope knowledge-base blobs, exactly like any
other KB upload. ALL analysis judgment lives in `DISCOVERY_PROMPT`; this module never parses a
package manifest or infers a framework itself.

This is an ORG job, not a project stage: it runs outside `console.py`'s poller/lifecycle (its own
scratch dir, its own budget watcher), so this module deliberately does not import `console`.
`status()` is a PROJECTION of the live process + the log + the landed blobs — there is no stored
run-state machine, and a re-run simply lands new blobs (list_org_docs orders newest-first, same
as any other KB doc).
"""
from __future__ import annotations

import os
import shutil
import signal
import subprocess
import threading
import time
from urllib.parse import urlsplit, urlunsplit

from .. import env as _env
from .. import storage
from ..blobs import BlobStore
from ..log import get_logger
from ..repositories._exec import GlobalExec
from ..repositories.org_secrets import OrgSecretsRepository
from ..services.secrets import Secrets
from ..services.errors import ServiceError
from ..streamlog import cost_usd

logger = get_logger(__name__)

DISCOVERY_PROMPT = """You are a codebase-discovery agent. You have read access to a freshly
cloned repository at your current working directory. Your job: understand this codebase well
enough to write three files at the repo root that teach OTHER coding agents how to safely extend
it. Write ONLY these three files — touch nothing else in this repository:

1. AGENTS.md — architecture, module layout, conventions, and extension points: where a new
   feature would live, what patterns to follow, what NOT to touch. Cite the specific file paths
   you read as evidence for each claim (e.g. "src/api/routes.py defines the REST layer").
2. CLAUDE.md — install / build / test / lint / deploy commands, found in package manifests, CI
   workflow files, README, and Makefiles. Quote the exact commands and name the file each came
   from.
3. integrations.md — every external system this codebase talks to (APIs, databases, queues,
   third-party services): how each is configured, which files reference it, and which
   environment variables it expects — name the variable, never print a value you find.

Read broadly before writing: package manifests, CI config, README, top-level source layout.
Every claim in your three files must trace back to a file you actually read — never guess or
invent. If something is genuinely unclear from the repo, say so plainly instead of making it up."""

_ARTIFACTS = ("AGENTS.md", "CLAUDE.md", "integrations.md")
# Org scratch lives under the SAME writable root the project runs use (SF_PROJECTS_DIR — a Railway
# volume in prod): the volume only grants the server user write access to that pre-existing path,
# not a fresh top-level sibling — a bare "/data/org" 403s (staging incident, CBT-6 C4). `_org` is a
# reserved, non-project top-level entry under it, alongside the janitor's own `_quarantine`
# directory — see console/poller.py's boot janitor, which explicitly exempts both by name so
# neither gets swept as debris; `PROJECT_ID_RE.fullmatch("_org")` is false, so every place that
# scans PROJECTS_DIR for real project ids (console.py's `list_projects`/`reap_deploy_dbs`/repo-scan
# helpers, all filtered by that same regex) already ignores it naturally. SF_DISCOVERY_DIR remains
# a full override (used by local verification), taking precedence over the derived default.
_SCRATCH_ROOT = os.environ.get(
    "SF_DISCOVERY_DIR",
    os.path.join(os.environ.get("SF_PROJECTS_DIR", ".projects"), "_org"),
)
_CHECK_INTERVAL_S = 15.0
_SENTINEL = "cloning"  # reserves an org's slot in _procs while the (possibly slow) clone is in
                        # flight, so the lock only needs to be held for the check-and-reserve, not
                        # for the whole clone+launch — a second org's start() must not wait on it.

_procs: dict[str, subprocess.Popen | str] = {}
_lock = threading.Lock()


class DiscoveryError(Exception):
    """Raised with the honest, user-visible reason a discovery run could not start."""


def _scratch_dir(org_id: str) -> str:
    return os.path.join(_SCRATCH_ROOT, org_id, "discovery")


def _log_path(org_id: str) -> str:
    return os.path.join(_scratch_dir(org_id), "discovery.log")


def _clone_dir(org_id: str) -> str:
    return os.path.join(_scratch_dir(org_id), "clone")


def _pid_path(org_id: str) -> str:
    return os.path.join(_scratch_dir(org_id), "pid")


def _read_pid_file(org_id: str) -> int | None:
    try:
        with open(_pid_path(org_id)) as f:
            return int(f.read().strip())
    except (OSError, ValueError):
        return None


def _is_orphaned_agent(org_id: str, pid: int) -> bool:
    """True when `pid` names a still-live process whose cwd is this org's own clone dir — i.e. the
    watcher thread that owned it died (a console restart) while the `claude` child lived on,
    uncapped by the budget watcher. Filesystem breadcrumb only, no DB state; the pid itself could
    already be recycled by an unrelated process, so the cwd check is what makes this safe."""
    try:
        cwd = os.readlink(f"/proc/{pid}/cwd")
    except OSError:
        return False
    return cwd == _clone_dir(org_id)


def _reap_orphan(pid: int) -> None:
    """SIGTERM→(~5s)→SIGKILL a real orphaned agent process. Caller is responsible for logging the
    honest reason — this runs BEFORE the run's own log file is (re)opened, since the reap must
    happen while the orphan's clone dir still exists (its `/proc/<pid>/cwd` check would otherwise
    resolve to "<path> (deleted)" once this run's fresh clone starts by removing that directory)."""
    try:
        os.kill(pid, signal.SIGTERM)
        for _ in range(50):
            time.sleep(0.1)
            try:
                os.kill(pid, 0)
            except OSError:
                break
        else:
            os.kill(pid, signal.SIGKILL)
    except OSError:
        pass  # already gone by the time we got here


def _authed_url(repo_url: str, pat: str) -> str:
    """Insert the PAT into the clone URL (GitHub's `x-access-token:<pat>@host` convention).
    Never logged, never returned — only ever handed straight to `git clone`."""
    url = repo_url if "://" in repo_url else f"https://{repo_url}"
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, f"x-access-token:{pat}@{parts.netloc}",
                       parts.path, parts.query, parts.fragment))


def _scrub(text: str, pat: str | None) -> str:
    """Strip a PAT out of captured subprocess output before it's logged or raised — a git error
    can otherwise echo the authed URL verbatim."""
    return text.replace(pat, "***") if pat else text


def _make_drop_privileges(uid: int, gid: int):
    """Mirrors console.py's `_default_launch` helper — dropped in here rather than imported
    because discovery deliberately does not import `console` (an org job, not a project stage)."""
    def _drop():
        os.setgid(gid)
        os.setuid(uid)
    return _drop


def _launch(argv: list[str], env: dict, cwd: str, log_path: str) -> subprocess.Popen:
    """Launch with stdout appended DIRECTLY to the log file (the child owns its own log fd) —
    same shape as `console.py::_default_launch`, so a console restart can't wedge this run on a
    readerless pipe."""
    preexec_fn = None
    if os.geteuid() == 0:
        import pwd as _pwd
        try:
            pw = _pwd.getpwnam("node")
            preexec_fn = _make_drop_privileges(pw.pw_uid, pw.pw_gid)
        except KeyError:
            pass  # node user absent (local dev) — proceed as-is
    with open(log_path, "ab") as logf:
        return subprocess.Popen(
            argv, env=_env.stage_env_baseline(env), cwd=cwd,
            stdout=logf, stderr=subprocess.STDOUT, preexec_fn=preexec_fn,
        )


def start(org_id: str, repo_url: str, pat_secret: str | None = None) -> dict:
    """Clone `repo_url` (optionally authed via the org secret named `pat_secret`) and launch one
    discovery agent over it. Raises `DiscoveryError` with the honest reason on refusal — a run
    already in progress for this org, an unresolvable secret, a clone timeout, or a clone failure
    (the verbatim git error, PAT scrubbed).

    The lock is held only long enough to check-and-reserve this org's slot (a `_SENTINEL`
    placeholder) — the clone itself (up to 120s) and the launch run OUTSIDE the lock, so a second
    org's `start()` never waits on this one's clone. Any failure clears the reservation."""
    with _lock:
        p = _procs.get(org_id)
        if p is not None and (p == _SENTINEL or p.poll() is None):
            raise DiscoveryError("a discovery run is already in progress for this org")
        # No in-memory handle for this org — note (don't act on yet) whether a prior console
        # restart orphaned a live agent for it; the reap itself must run OUTSIDE the lock (it can
        # take up to ~5s) and BEFORE this run's own clone dir gets removed below (an orphan's
        # `/proc/<pid>/cwd` would otherwise resolve to "<path> (deleted)" and evade detection).
        orphan_pid = _read_pid_file(org_id) if p is None else None
        _procs[org_id] = _SENTINEL

    try:
        reaped_pid = None
        if orphan_pid and _is_orphaned_agent(org_id, orphan_pid):
            _reap_orphan(orphan_pid)
            reaped_pid = orphan_pid

        pat = None
        if pat_secret:
            try:
                pat = Secrets(OrgSecretsRepository(GlobalExec())).get_value(org_id, pat_secret)
            except ServiceError as exc:
                raise DiscoveryError(str(exc)) from exc

        scratch = _scratch_dir(org_id)
        clone_dir = _clone_dir(org_id)
        shutil.rmtree(clone_dir, ignore_errors=True)
        os.makedirs(scratch, exist_ok=True)
        log_path = _log_path(org_id)

        clone_url = _authed_url(repo_url, pat) if pat else repo_url
        with open(log_path, "w") as f:
            if reaped_pid:
                f.write(f"[discovery] reaped an orphaned agent (pid {reaped_pid}) left running "
                       f"uncapped by a prior console restart\n")
            f.write(f"cloning {repo_url} (shallow)...\n")
        try:
            result = subprocess.run(["git", "clone", "--depth", "1", clone_url, clone_dir],
                                    capture_output=True, text=True, timeout=120)
        except subprocess.TimeoutExpired as exc:
            # TimeoutExpired's own str()/repr() embeds the full argv — i.e. the PAT-bearing clone
            # URL — so exc itself must never be logged or raised; only this scrubbed, hand-written
            # message may reach the log or the caller.
            err = _scrub(f"clone timed out after {exc.timeout:.0f}s", pat)
            with open(log_path, "a") as f:
                f.write(f"clone failed: {err}\n")
            raise DiscoveryError(f"could not clone {repo_url}: {err}") from None
        if result.returncode != 0:
            err = _scrub((result.stderr or result.stdout).strip(), pat)[-500:]
            with open(log_path, "a") as f:
                f.write(f"clone failed: {err}\n")
            raise DiscoveryError(f"could not clone {repo_url}: {err}")
        with open(log_path, "a") as f:
            f.write("clone complete — launching discovery agent\n")

        argv = ["claude", "-p", DISCOVERY_PROMPT, "--model", "claude-sonnet-4-6",
               "--dangerously-skip-permissions", "--output-format", "stream-json", "--verbose"]
        proc = _launch(argv, {"ANTHROPIC_API_KEY": os.environ.get("ANTHROPIC_API_KEY", "")},
                      cwd=clone_dir, log_path=log_path)
        with open(_pid_path(org_id), "w") as f:
            f.write(str(proc.pid))
        with _lock:
            _procs[org_id] = proc
    except Exception:
        with _lock:
            _procs.pop(org_id, None)
        raise

    threading.Thread(target=_watch, args=(org_id, proc), daemon=True,
                     name=f"discovery-{org_id}").start()
    return status(org_id)


def _watch(org_id: str, proc: subprocess.Popen) -> None:
    """Money (the one sanctioned piece of machinery here): re-parse the log's cost every
    `_CHECK_INTERVAL_S` and kill the agent if it crosses `SF_DISCOVERY_COST_CEILING`. On exit
    (killed or natural), land whatever of the three files exist — no completeness gate."""
    ceiling = float(os.environ.get("SF_DISCOVERY_COST_CEILING", "10") or "10")
    log_path = _log_path(org_id)
    timer_box: dict = {}

    def _tick():
        if proc.poll() is not None:
            return
        try:
            with open(log_path, "r", errors="replace") as f:
                spent = cost_usd(f.read())
        except OSError:
            spent = 0.0
        if spent >= ceiling:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
            with open(log_path, "a") as f:
                f.write(f"\n[discovery] stopped — spend ${spent:.2f} reached the "
                       f"${ceiling:.2f} cap (SF_DISCOVERY_COST_CEILING)\n")
            return
        timer_box["t"] = threading.Timer(_CHECK_INTERVAL_S, _tick)
        timer_box["t"].daemon = True
        timer_box["t"].start()

    timer_box["t"] = threading.Timer(_CHECK_INTERVAL_S, _tick)
    timer_box["t"].daemon = True
    timer_box["t"].start()
    proc.wait()
    if timer_box.get("t"):
        timer_box["t"].cancel()
    try:
        _land_artifacts(org_id)
    except Exception:
        logger.exception("[discovery] %s: failed landing artifacts", org_id)
    finally:
        try:
            os.remove(_pid_path(org_id))
        except OSError:
            pass  # already gone, or was never written (e.g. failed before launch)
        with _lock:
            _procs.pop(org_id, None)


def _land_artifacts(org_id: str) -> None:
    """Persist whatever of the three files the agent actually wrote as org-scope KB blobs —
    mirrors the persistence block of the org KB upload route (OrgService.upload_doc): storage.put
    + BlobStore.record only. Ingestion is deliberately LAZY here too, exactly like an uploaded KB
    doc — it fires at project-import time (`record_doc_use` → `maybe_ingest_async`, SOF-32), not
    eagerly at landing time. An eager per-file ingest call here would be a cost-bearing behavior
    deviation from every other KB doc, not a mirror of it."""
    clone_dir = _clone_dir(org_id)
    scope_id = f"org/{org_id}"
    blobs = BlobStore()
    for name in _ARTIFACTS:
        path = os.path.join(clone_dir, name)
        if not os.path.exists(path):
            continue
        with open(path, "rb") as f:
            raw = f.read()
        key = f"kb/{name}"
        storage.put(scope_id, key, raw)
        blobs.record("org", org_id, f"{scope_id}/{key}", name=name, tag="discovery",
                     kind="doc", content_type="text/markdown",
                     size_bytes=len(raw), sha256=storage.sha256(raw))
    shutil.rmtree(clone_dir, ignore_errors=True)


def sweep_orphaned_discovery_runs() -> list[str]:
    """SOF-208 boot-time sweep. `start()`/`status()` already reap an orphan lazily on the NEXT org
    interaction (SOF-205/#391) — but an org nobody interacts with again is never swept, and the
    `claude -p` child it left behind keeps running with no budget watcher, uncapped. Call once at
    boot (console/poller.py::_boot()). Mirrors `reap_completed_zombie`'s posture: kill machinery
    only for money/lifecycle, small and bounded, no DB state — a pure filesystem scan of
    `_SCRATCH_ROOT`'s per-org pid breadcrumbs, reusing the exact same helpers the lazy path uses so
    the two can't diverge.

    For each org with a pid breadcrumb: a still-live process whose cwd anchors to that org's clone
    dir is reaped (SIGTERM->SIGKILL) and logged. Anything else — pid file missing/unreadable, pid
    dead, or cwd mismatch (a recycled pid) — is just a stale breadcrumb: delete it, no other
    action. Returns the org_ids actually reaped (for the caller's boot-log summary)."""
    reaped: list[str] = []
    try:
        org_ids = os.listdir(_SCRATCH_ROOT)
    except OSError:
        return reaped  # scratch root doesn't exist yet (no discovery run has ever happened)
    for org_id in org_ids:
        pid_path = _pid_path(org_id)
        if not os.path.exists(pid_path):
            continue  # no breadcrumb for this org — nothing to do
        pid = _read_pid_file(org_id)
        try:
            if pid is not None and _is_orphaned_agent(org_id, pid):
                _reap_orphan(pid)
                logger.info(
                    "[discovery-sweep] org %s: reaped an orphaned agent (pid %s) left running "
                    "uncapped by a prior console restart", org_id, pid)
                reaped.append(org_id)
        except Exception:
            logger.exception("[discovery-sweep] org %s: reap attempt failed", org_id)
        finally:
            try:
                os.remove(pid_path)
            except OSError:
                pass  # already gone
    return reaped


def status(org_id: str) -> dict:
    """A projection of live state — never stored: is the process alive, what the log says so
    far, what's landed in the KB, and what this run has spent.

    `running` cross-checks the pid-file breadcrumb when this process has no in-memory handle for
    the org (e.g. this console restarted since the run was launched) — an unmanaged-but-still-live
    agent is honestly reported as running, not silently dropped to False."""
    p = _procs.get(org_id)
    if p is None:
        orphan_pid = _read_pid_file(org_id)
        running = bool(orphan_pid and _is_orphaned_agent(org_id, orphan_pid))
    elif p == _SENTINEL:
        running = True
    else:
        running = p.poll() is None
    log_path = _log_path(org_id)
    log_tail, spent = "", 0.0
    if os.path.exists(log_path):
        with open(log_path, "r", errors="replace") as f:
            text = f.read()
        log_tail = text[-4000:]
        try:
            spent = cost_usd(text)
        except Exception:
            spent = 0.0
    docs = BlobStore().list_org_docs(org_id)  # newest-first (id desc) — a re-run's docs sort above
    seen: set = set()
    artifacts = []
    for d in docs:
        if d["name"] in _ARTIFACTS and d["name"] not in seen:
            seen.add(d["name"])
            artifacts.append({"name": d["name"], "blob_id": d["id"], "updated": d["updated"]})
    return {"running": running, "log_tail": log_tail, "artifacts": artifacts,
           "spent_usd": round(spent, 4)}
