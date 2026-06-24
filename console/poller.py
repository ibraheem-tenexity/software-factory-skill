"""Background poller + boot + lifespan — the autonomy loop, lifted verbatim from the monolith.

Started from the app lifespan (`console.app` includes it). References the shared singletons through
the `state` module so a reassignment (e.g. tests patching `state._chat_runner`) is seen at call time.
"""
import contextlib
import json
import os
import threading
import time

from fastapi import FastAPI

from software_factory.chat_store import ChatStore, ChatMessage
from software_factory import notify
from software_factory import tracing
from software_factory import env as _env

import console.state as state

_stage2_launched: set = set()
_stage3_launched: set = set()
_narrated: set = set()
# project_id -> crash auto-resume attempts, bounded per server life. Configurable: long opencode
# sessions (multi-hour Kimi build/test loops) crash more often than claude's — run-b594a5f4
# exhausted 2 resumes mid-test-phase and stalled 12h. The bound exists to stop crash loops,
# not to ration recovery; budget enforcement is the real spend brake.
_AUTO_RESUME_MAX = int(os.environ.get("SF_AUTO_RESUME_MAX", "2") or 2)
_auto_resumed: dict = {}
_tracer = tracing.Tracer()
_health_bad_since = [None]  # [-]: None = healthy; float = first failure ts (alert once)


def _auto_advance(pid: str):
    """SPEC §1+§3: flip stage-done (gate + finished process) and launch the next stage, so runs
    advance with no manual nudge. Stage 2 auto-launches when Stage 1 is done; deps auto-satisfy
    when no human secret is needed; Stage 3 auto-launches once deps are satisfied. Launch guards
    are marked ONLY on success so a refusal (e.g. prior process still alive) retries next tick."""
    console = state.console
    try:
        if not console.is_pipeline_project(pid):
            return  # resurfaced pre-redesign dir (empty project store) — never auto-advance/zombie-launch it
        if console.detect_stage1_done(pid):
            s = console.status(pid)
            if s.get("stage") == 1 and pid not in _stage2_launched:
                if console.start_stage2(pid):
                    _stage2_launched.add(pid)
        if console.detect_stage2_done(pid):  # flips stage2_done + parses required tokens
            console.maybe_autosatisfy_deps(pid)   # SPEC §3: no 'provide' token -> no pause
            s = console.status(pid)
            if s.get("deps_satisfied") and s.get("stage") == 2 and pid not in _stage3_launched:
                if console.start_stage3(pid):
                    _stage3_launched.add(pid)
        console.detect_stage3_done(pid)  # marks done ONLY with a recorded passing Playwright verification
    except Exception:
        pass


def _append_notifications(pid: str, msgs):
    """Persist + push stage notifications, deduped against the persisted chat history —
    a restarted server re-walks stage transitions and re-fired old notifications AFTER
    newer messages, scrambling the chat panel's chronology (run-45b8c4d5)."""
    store = ChatStore(state._chat_path(pid))
    try:
        seen = {m.content for m in store.history()}
    except Exception:
        seen = set()
    fresh = [m for m in msgs if m.content not in seen]
    for m in fresh:
        store.append(m)
    if fresh:
        state._push_sse(pid, fresh)


def _narrate(pid: str, key: str, text: str):
    """SPEC §6: deterministic chat-panel narration — one message per (run, event), no LLM.
    Dedup survives server restarts by checking the persisted chat history, not just memory."""
    if (pid, key) in _narrated:
        return
    _narrated.add((pid, key))
    store = ChatStore(state._chat_path(pid))
    try:
        if any(m.content == text for m in store.history()):
            return  # already narrated in a previous server life
    except Exception:
        pass
    msg = ChatMessage(role="assistant", content=text)
    store.append(msg)
    state._push_sse(pid, [msg])
    # Operator email on the four operator-relevant events (done / depswait / budget / crash) —
    # placed AFTER the dedup so an email fires at most once per (run, event). Fire-and-forget:
    # notify.send never raises and must never block the poller.
    if notify.should_email(key):
        threading.Thread(
            target=notify.send,
            args=(f"[factory] {pid}: {text[:90]}", f"{text}\n\nrun: {pid}"),
            daemon=True,
        ).start()


def _narrate_project(pid: str, st: dict):
    console = state.console
    links = console.project_links(pid)
    if links.get("repo"):
        _narrate(pid, "repo", f"📦 Source repo: {links['repo']}")
    if st.get("stage1_done"):
        _narrate(pid, "s1", "✅ Research complete — design & architecture starting.")
    if st.get("stage2_done"):
        if st.get("deps_satisfied"):
            _narrate(pid, "deps", "🔓 Design complete — dependencies satisfied, build starting.")
        elif st.get("deps_required"):
            need = [n for n in (st.get("deps_required") or [])]
            _narrate(pid, "depswait", "⏸ Design complete — waiting for you to supply: " + ", ".join(need))
    if links.get("live") and not st.get("done"):
        _narrate(pid, "deployed", f"🚀 Deployed (verifying): {links['live']}")
    if st.get("done"):
        live = st.get("deploy_url") or links.get("live") or ""
        repo = links.get("repo") or ""
        msg = f"✅ Done — Live demo: {live}" + (f" · 📦 Repo: {repo}" if repo else "")
        try:
            creds = console.demo_credentials(pid)
        except Exception:
            creds = None
        if creds:
            # The seeded throwaway demo login (SPEC §6) — without it an auth'd app can't be demoed.
            msg += "\n🔑 Demo login:\n" + creds
        _narrate(pid, "done", msg)


def _health() -> dict:
    """Liveness for probes + the console dot."""
    import shutil as _sh
    from software_factory import dbshim
    try:
        dbshim.registry_projects()
        pg = True
    except Exception:
        pg = False
    try:
        free_mb = int(_sh.disk_usage(state.PROJECTS_DIR).free / 1048576)
    except OSError:
        free_mb = -1
    ok = pg and free_mb > 200
    return {"ok": ok, "pg": pg, "disk_free_mb": free_mb}


def _reaper_tick(tick: int, interval: int, console) -> dict | None:
    """Run the deploy-DB reaper if both gates are open: interval knob (ibraheem's activation) and
    the teardown arm (SF_DEPLOY_DB_TEARDOWN). Returns the report dict or None when skipped."""
    from software_factory import deploy_db
    if interval <= 0 or tick <= 0 or tick % interval != 0:
        return None
    if deploy_db.teardown_mode() == "off":
        return None  # disarmed: silent skip — avoid log spam until ibraheem arms the policy
    report = console.reap_deploy_dbs(dry_run=False)
    reaped = len(report.get("reaped") or [])
    would = len(report.get("would_reap") or [])
    kept = len(report.get("kept") or [])
    print(f"[reaper] sweep done: reaped={reaped} would_reap={would} kept={kept} "
          f"mode={report.get('mode')}", flush=True)
    return report


def _poll_transitions():
    """Background thread: auto-advance stages, enforce the per-project budget, narrate progress."""
    console = state.console
    tick = 0
    _reaper_interval = int(os.environ.get("SF_REAPER_INTERVAL_TICKS", "0") or "0")
    while True:
        time.sleep(3)
        tick += 1
        if tick % 10 == 0:  # health every ~30s; email once per unhealthy episode
            try:
                h = _health()
                if not h["ok"] and _health_bad_since[0] is None:
                    _health_bad_since[0] = time.time()
                    notify.send("factory-console UNHEALTHY",
                                f"health: {json.dumps(h)} — pg unreachable or disk low.")
                elif h["ok"]:
                    _health_bad_since[0] = None
            except Exception:
                pass
        try:
            _reaper_tick(tick, _reaper_interval, console)
        except Exception:
            pass
        try:
            for project_info in console.list_projects():
                pid = project_info.get("id") or project_info.get("project_id", "")
                if not pid:
                    continue
                if project_info.get("held"):  # gated hold: nothing to advance/enforce/narrate
                    continue
                _auto_advance(pid)
                st = console.status(pid)
                # LLM traces: ship this run's new log lines to Langfuse (no-op without keys).
                _tracer.tick(pid, os.path.join(state.PROJECTS_DIR, pid, "project.log"),
                             meta={"runtime": st.get("runtime", "")})
                try:
                    if not st.get("done") and console.enforce_budget(pid):
                        _narrate(pid, "budget-%d" % int(console._budget_ceiling(pid)),
                                 "⏸ Budget cap reached — stage stopped (state preserved). "
                                 "Raise the cap to continue.")
                    # SPEC §3 zero-touch: resume a crashed stage automatically (bounded).
                    if not st.get("done") and _auto_resumed.get(pid, 0) < _AUTO_RESUME_MAX:
                        if console.auto_resume_dead_stage(pid):
                            _auto_resumed[pid] = _auto_resumed.get(pid, 0) + 1
                            _narrate(pid, "resume-%d" % _auto_resumed[pid],
                                     "⚠️ Stage process died mid-flight — auto-resumed "
                                     f"(attempt {_auto_resumed[pid]}/{_AUTO_RESUME_MAX}).")
                    elif not st.get("done") and _auto_resumed.get(pid, 0) >= _AUTO_RESUME_MAX:
                        # Auto-resume cap exhausted — land in 'crashed' for Recovery-bar resume.
                        if console.mark_stage_crashed(pid):
                            _narrate(pid, "crashed-final",
                                     f"⛔ Stage crashed after {_AUTO_RESUME_MAX} auto-resume "
                                     "attempts — paused for operator (use Resume to continue).")
                    _narrate_project(pid, st)
                except Exception:
                    pass
                if st.get("done") or st.get("phase") == "pending":
                    continue
                prev = state._project_stages.get(pid, 0)
                cur = st.get("stage", 1)
                if cur != prev:
                    state._project_stages[pid] = cur
                    if state._chat_runner:
                        _append_notifications(pid, state._chat_runner.check_and_notify(pid, prev_stage=prev))
                if st.get("done") and prev > 0:
                    if state._chat_runner:
                        _append_notifications(pid, state._chat_runner.check_and_notify(pid, prev_stage=cur))
                    state._project_stages.pop(pid, None)
        except Exception:
            pass


def _boot():
    """One-time boot work that lived in the old server's __main__ block: announce the runtime
    user, quarantine debris, prod pg-backfill, and owner-backfill. Runs in the app lifespan."""
    import getpass
    console = state.console
    print(f"[runner] uid={os.getuid()} user={getpass.getuser()} home={os.environ.get('HOME')}", flush=True)
    if not state._has_chat_key:
        print("[warn] no OPENAI_API_KEY or OPENROUTER_API_KEY — chat agent disabled, API-only mode")
    # Quarantine debris under projects_dir: agents misusing db verbs once created dirs like
    # "build-plan.md/project store" on the volume — moved aside (never deleted), so discovery and
    # the boot backfill only ever see real runs.
    try:
        from software_factory.console import PROJECT_ID_RE
        qdir = os.path.join(state.PROJECTS_DIR, "_quarantine")
        for name in os.listdir(state.PROJECTS_DIR):
            p = os.path.join(state.PROJECTS_DIR, name)
            if os.path.isdir(p) and name != "_quarantine" and not PROJECT_ID_RE.fullmatch(name):
                os.makedirs(qdir, exist_ok=True)
                os.rename(p, os.path.join(qdir, f"{name}.{int(time.time())}"))
                print(f"[janitor] quarantined {name}", flush=True)
    except Exception as e:
        print(f"[janitor] FAILED: {e}", flush=True)
    if _env.sf_environment() == "prod":
        # Apply migrations (Alembic upgrade head) so every table exists. Defensive backstop to
        # entrypoint.sh (idempotent).
        try:
            from software_factory import migrate as _migrate
            _migrate.run()
        except Exception as e:
            print(f"[migrate] boot FAILED: {e}", flush=True)
    # Backfill ownership on pre-multitenancy runs → the bootstrap admin (idempotent).
    _boot_admin = os.environ.get("SF_BOOTSTRAP_ADMIN_EMAIL", "").strip().lower()
    if _boot_admin:
        try:
            n = console.assign_unowned(_boot_admin)
            if n:
                print(f"[owners] assigned {n} unowned run(s) to {_boot_admin}", flush=True)
        except Exception as e:
            print(f"[owners] backfill FAILED: {e}", flush=True)

    # Backfill the immutable created_by from the current owner for pre-existing projects (idempotent).
    try:
        n = console.backfill_created_by()
        if n:
            print(f"[created_by] backfilled {n} project(s) from owner", flush=True)
    except Exception as e:
        print(f"[created_by] backfill FAILED: {e}", flush=True)


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    _boot()
    t = threading.Thread(target=_poll_transitions, daemon=True)
    t.start()
    print(f"software-factory console (FastAPI) — runs in {os.path.abspath(state.PROJECTS_DIR)}", flush=True)
    yield
