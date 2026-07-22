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

from software_factory.data_transfer_objects.chat_agent import ChatMessage
from software_factory import notify
from software_factory import env as _env
from software_factory import recovery

import console.state as state
from console import chat_persistence

_stage2_launched: set = set()
_stage3_launched: set = set()
_narrated: set = set()
_recovery_done_resolved: set = set()  # SOF-165: pids whose recovery actions were resolved on done (once per server life)
_log_offsets: dict = {}  # pid -> bytes uploaded on last log flush
# Crash auto-resume attempts. Configurable: long opencode sessions (multi-hour Kimi build/test
# loops) crash more often than claude's — run-b594a5f4 exhausted 2 resumes mid-test-phase and
# stalled 12h. The bound exists to stop crash loops, not to ration recovery; budget enforcement is
# the real spend brake. SOF-116: the count itself is PERSISTED on ProjectState (auto_resume_count),
# not an in-process dict — a console restart (redeploy/OOM) must not hand out a fresh set of "free"
# resumes, or a run can retry forever across restarts without ever reaching mark_stage_crashed
# (the only path that notifies the operator).
#
# SOF-217: read FRESH every tick (a function, not a module-level constant frozen at import) —
# console.py's own auto_resume_dead_stage() reads this SAME env var fresh on every call. A frozen
# import-time constant here assumed "a Railway env change always restarts the process" (see the
# _SILENCE_* comment below) — if that assumption is ever wrong for a given deploy/runtime, poller
# and console would silently disagree on the cap: e.g. poller still thinks resumes_so_far < a
# STALE higher max (so it keeps calling auto_resume_dead_stage — which internally refuses via its
# own FRESH, lower cap) and the `elif resumes_so_far >= _AUTO_RESUME_MAX` branch that calls
# mark_stage_crashed() is never reached at all — a silent, permanent wedge, never a crash, never a
# resume, matching exactly what was observed live (project-414784ebacee4dca sat in phase=research
# with auto_resume_count pinned at the cap for 45+ minutes, no crash-park, no blocker). Reading
# fresh here closes that whole risk class regardless of whether it was the exact trigger.
def _auto_resume_max() -> int:
    return int(os.environ.get("SF_AUTO_RESUME_MAX", "2") or 2)
_health_bad_since = [None]  # [-]: None = healthy; float = first failure ts (alert once)
# SOF-164: output-silence classification bands (seconds), env-tunable. Coherent with the existing
# scales — 300s = stage_finished's opencode idle grace (past normal streaming-quiet); 900s sits
# above that yet below run_autopsy's STALL_HOURS (3600s), so the PROD poller notices a frozen run
# BEFORE the benchmark cron would. Read at import like _AUTO_RESUME_MAX (a Railway env change
# restarts the process and picks them up). NOT a new scale — anchored to the two that already exist.
_SILENCE_SUSPICIOUS_S = int(os.environ.get("SF_SILENCE_SUSPICIOUS_S", "300") or 300)
_SILENCE_CRITICAL_S = int(os.environ.get("SF_SILENCE_CRITICAL_S", "900") or 900)


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


def _narrate(pid: str, key: str, text: str):
    """SPEC §6: deterministic chat-panel narration — one message per (run, event), no LLM.
    Dedup survives server restarts by checking the persisted chat history, not just memory."""
    if (pid, key) in _narrated:
        return
    _narrated.add((pid, key))
    try:
        if any(m.get("content") == text for m in chat_persistence.chat_history(pid)):
            return  # already narrated in a previous server life
    except Exception:
        pass
    msg = ChatMessage(role="assistant", content=text)
    chat_persistence.persist_chat_turn(pid, msg)
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
    links = console.records.project_links(pid)
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


def _silence_tick(log_path: str) -> tuple[str, float]:
    """SOF-164 (Proposal 4): classify a run's output-silence — 'ok' | 'suspicious' | 'critical' |
    'no-log'. PURE noticing: reads only the log's mtime — never the process, never a kill/resume/
    advance. This is a PARALLEL observation channel to stage_finished's binary finish/kill/resume
    path, which stays completely untouched (zero regression to the twice-patched acting logic).

    Bands from _SILENCE_SUSPICIOUS_S / _SILENCE_CRITICAL_S. A missing/never-written log on an
    ACTIVE run is NOT 'ok' — it's its own 'no-log' signal (a stage that died before writing a
    single line), which the caller treats as critical. Returns (state, idle_seconds); idle is -1
    for the no-log case."""
    try:
        idle = time.time() - os.path.getmtime(log_path)
    except OSError:
        return ("no-log", -1.0)
    if idle < _SILENCE_SUSPICIOUS_S:
        return ("ok", idle)
    if idle < _SILENCE_CRITICAL_S:
        return ("suspicious", idle)
    return ("critical", idle)


def _run_is_silence_classifiable(st: dict) -> bool:
    """True only for a run whose stage orchestrator SHOULD be streaming output right now — the only
    runs where silence is meaningful. Excludes everything that is intentionally quiet: done, held,
    budget_stopped, and credential_stopped (SOF-148 — a run parked on either must never flag), plus
    the pre-launch and terminal phases (no orchestrator is running to go silent). Exclusion-based so
    a NEW mid-execution phase defaults to classifiable — the safe direction for a noticing layer."""
    if st.get("done") or st.get("held") or st.get("budget_stopped") or st.get("credential_stopped"):
        return False
    phase = (st.get("phase") or "").lower()
    return phase not in ("draft", "pending", "provision", "stopped", "crashed", "paused", "done")


def _recovery_action_seam(pid: str, console, idle: float) -> None:
    """SOF-165: a 'critical' silence opens the tier-2 Recovery Action — but ONLY when the process is
    genuinely ALIVE-but-silent. The liveness gate (SOF-161's durable _stage_process_alive) is the
    key separation: a DEAD silent stage is owned by the auto_resume → mark_stage_crashed 'dead_stage'
    path, which opens its OWN action; opening a 'silent_run' here too would double-count the same
    incident. So: alive+silent → open('silent_run') (idempotent — a persistent silence refreshes the
    one open action, never spams); dead → do nothing, the dead_stage path has it."""
    try:
        if console._stage_process_alive(pid):
            cause = "no output written yet while alive" if idle < 0 else f"silent {int(idle)}s while alive"
            recovery.open_recovery_action(pid, kind="silent_run", cause=cause,
                                          evidence={"idle_seconds": int(idle)})
    except Exception:
        pass  # best-effort — a recovery-bookkeeping hiccup must never wedge the poll loop


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


def _github_reaper_tick(tick: int, interval: int, console) -> dict | None:
    """Run the GitHub repo reaper if both gates are open: interval knob and SF_GITHUB_REPO_REAPER.
    Returns the report dict or None when skipped. Silent skip when disarmed (avoids log spam)."""
    from software_factory import github_repo_reaper
    if interval <= 0 or tick <= 0 or tick % interval != 0:
        return None
    if github_repo_reaper.github_reaper_mode() == "off":
        return None
    org = os.environ.get("SF_GITHUB_ORG", "ibraheem-tenexity")
    report = console.reap_github_repos(org, dry_run=False)
    reaped = len(report.get("reaped") or [])
    would = len(report.get("would_reap") or [])
    kept = len(report.get("kept") or [])
    unknown = len(report.get("unknown_repos") or [])
    print(f"[github-reaper] sweep done: reaped={reaped} would_reap={would} kept={kept} "
          f"unknown={unknown} mode={report.get('mode')}", flush=True)
    return report


def _ticket_reclaim_tick(tick: int, interval: int, pid: str, console) -> list:
    """SOF-163: interval-gated per-project check for orphaned in_progress tickets. Unlike the
    deploy-DB/GitHub reapers, this is ON by default (no separate arm env var) — reclaiming a
    ticket's own state back to `open` is a low-risk, purely-corrective action (unlike deleting a
    real Railway/GitHub resource), so it doesn't need the same disarmed-by-default caution.
    Returns the list of reclaimed ticket ids (empty if none, or if the interval hasn't come up)."""
    if interval <= 0 or tick <= 0 or tick % interval != 0:
        return []
    try:
        return console.reclaim_orphaned_tickets(pid)
    except Exception:
        return []


def _log_flush_tick(pid: str, log_path: str) -> None:
    """Upload project.log to Supabase Storage when new bytes have arrived since the last flush.
    Re-uploads the whole file (upsert, same key) — idempotent. No-op when storage is disabled."""
    from software_factory import storage
    if not storage.enabled() or not os.path.exists(log_path):
        return
    size = os.path.getsize(log_path)
    if size <= _log_offsets.get(pid, 0):
        return
    try:
        storage.put(pid, "logs/project.log", log_path)
        _log_offsets[pid] = size
    except Exception as e:
        print(f"[log-flush] {pid}: {e}", flush=True)


def _poll_transitions():
    """Background thread: auto-advance stages, enforce the per-project budget, narrate progress."""
    console = state.console
    tick = 0
    _reaper_interval = int(os.environ.get("SF_REAPER_INTERVAL_TICKS", "0") or "0")
    _gh_reaper_interval = int(os.environ.get("SF_GITHUB_REAPER_INTERVAL_TICKS", "0") or "0")
    _log_flush_interval = max(1, int(os.environ.get("SF_LOG_FLUSH_TICKS", "10") or "10"))
    # SOF-163: ~5 minutes at the default 3s base tick — the staleness bound this checks against is
    # hours, so there's no need to poll more often; on by default (see _ticket_reclaim_tick).
    _ticket_reclaim_interval = max(1, int(os.environ.get("SF_TICKET_RECLAIM_TICKS", "100") or "100"))
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
            _github_reaper_tick(tick, _gh_reaper_interval, console)
        except Exception:
            pass
        try:
            for project_info in console.list_projects():
                pid = project_info.get("id") or project_info.get("project_id", "")
                if not pid:
                    continue
                if project_info.get("held"):  # gated hold: nothing to advance/enforce/narrate
                    continue
                # #104: reap a claude orchestrator that declared itself done (terminal `result`)
                # but hung at remote-MCP teardown — its live handle would otherwise pin
                # stage_finished=False forever. Reaping BEFORE _auto_advance lets the run advance
                # this same tick once the process is gone.
                try:
                    _reaped = console.reap_completed_zombie(pid)
                    if _reaped:
                        _narrate(pid, "reap-%s" % _reaped,
                                 f"♻️ Stage process {_reaped} finished its work but hung at "
                                 "teardown — reaped so the run can continue.")
                except Exception:
                    pass
                _auto_advance(pid)
                st = console.status(pid)
                if tick % _log_flush_interval == 0:
                    try:
                        _log_flush_tick(pid, os.path.join(state.PROJECTS_DIR, pid, "project.log"))
                    except Exception:
                        pass
                try:
                    if not st.get("done") and console.enforce_budget(pid):
                        _narrate(pid, "budget-%d" % int(console._budget_ceiling(pid)),
                                 "⏸ Budget cap reached — stage stopped (state preserved). "
                                 "Raise the cap to continue.")
                    # SPEC §3 zero-touch: resume a crashed stage automatically (bounded).
                    # SOF-116: read the PERSISTED count (state.auto_resume_count via status()),
                    # not an in-process dict — survives console restarts.
                    resumes_so_far = st.get("auto_resume_count", 0)
                    auto_resume_max = _auto_resume_max()  # SOF-217: fresh, matches console.py
                    if not st.get("done") and resumes_so_far < auto_resume_max:
                        if console.auto_resume_dead_stage(pid):
                            n = console.status(pid).get("auto_resume_count", resumes_so_far + 1)
                            _narrate(pid, "resume-%d" % n,
                                     "⚠️ Stage process died mid-flight — auto-resumed "
                                     f"(attempt {n}/{auto_resume_max}).")
                    elif not st.get("done") and resumes_so_far >= auto_resume_max:
                        # Auto-resume cap exhausted — land in 'crashed' for Recovery-bar resume.
                        if console.mark_stage_crashed(pid):
                            _narrate(pid, "crashed-final",
                                     f"⛔ Stage crashed after {auto_resume_max} auto-resume "
                                     "attempts — paused for operator (use Resume to continue).")
                    # SOF-163: catches a single ticket orphaned WHILE the stage is still alive —
                    # distinct from the whole-stage recovery above, which only fires once the
                    # entire stage looks dead.
                    if not st.get("done"):
                        reclaimed = _ticket_reclaim_tick(tick, _ticket_reclaim_interval, pid, console)
                        if reclaimed:
                            _narrate(pid, "reclaim-%s" % ",".join(str(t) for t in reclaimed),
                                     f"♻️ Reclaimed stalled ticket(s) {reclaimed} back to open "
                                     "for re-dispatch.")
                    _narrate_project(pid, st)
                except Exception:
                    pass
                # SOF-164: graded silent-run classification — a PARALLEL noticing channel run AFTER
                # (and independent of) all the acting logic above. It never advances/kills/resumes;
                # it only narrates suspicious/critical and taps the SOF-165 recovery seam (a no-op
                # today). Gated to runs whose orchestrator should be streaming — a done/held/budget-
                # or credential-stopped run is intentionally quiet and must not flag.
                try:
                    if _run_is_silence_classifiable(st):
                        sil, idle = _silence_tick(os.path.join(state.PROJECTS_DIR, pid, "project.log"))
                        if sil == "suspicious":
                            _narrate(pid, "silence-suspicious",
                                     f"👀 Stage has been quiet ~{int(idle)}s — watching (no action taken).")
                        elif sil in ("critical", "no-log"):
                            detail = "hasn't written any output yet" if sil == "no-log" else f"silent for ~{int(idle)}s"
                            _narrate(pid, "silence-critical",
                                     f"🔴 Stage {detail} — flagged for review.")
                            _recovery_action_seam(pid, console, idle)   # SOF-165: acts iff alive
                except Exception:
                    pass
                # SOF-165: a run that reaches done RESOLVES its open recovery action(s) — a
                # self-recovered silent_run (transient silence that then completed) must not leave a
                # zombie-open row. Once per pid per server life; idempotent no-op if none open.
                if st.get("done") and pid not in _recovery_done_resolved:
                    _recovery_done_resolved.add(pid)
                    recovery.resolve_recovery_actions(pid, resolution="restored")
                if st.get("done") or st.get("phase") == "pending":
                    continue
                prev = state._project_stages.get(pid, 0)
                cur = st.get("stage", 1)
                if cur != prev:
                    state._project_stages[pid] = cur
                if st.get("done") and prev > 0:
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
    # the boot backfill only ever see real runs. `_org` is a second sanctioned non-project entry
    # (ingestion's codebase-discovery scratch, CBT-6 — org-level clones/logs live under
    # PROJECTS_DIR/_org/<org_id>/, the same writable volume the project runs use) — exempted by
    # name exactly like `_quarantine` itself, so a boot/redeploy never sweeps a live discovery run.
    try:
        from software_factory.constants import PROJECT_ID_RE
        qdir = os.path.join(state.PROJECTS_DIR, "_quarantine")
        for name in os.listdir(state.PROJECTS_DIR):
            p = os.path.join(state.PROJECTS_DIR, name)
            if os.path.isdir(p) and name not in ("_quarantine", "_org") and not PROJECT_ID_RE.fullmatch(name):
                os.makedirs(qdir, exist_ok=True)
                os.rename(p, os.path.join(qdir, f"{name}.{int(time.time())}"))
                print(f"[janitor] quarantined {name}", flush=True)
    except Exception as e:
        print(f"[janitor] FAILED: {e}", flush=True)
    # SOF-208: a console restart mid-discovery-run kills the in-process budget watcher thread
    # while the `claude -p` child keeps running uncapped. start()/status() reap this lazily on the
    # org's next interaction (SOF-205/#391); this boot-time sweep catches the org that never has one.
    try:
        from software_factory.ingestion.discovery import sweep_orphaned_discovery_runs
        reaped = sweep_orphaned_discovery_runs()
        if reaped:
            print(f"[discovery-sweep] reaped orphaned agents for org(s): {reaped}", flush=True)
    except Exception as e:
        print(f"[discovery-sweep] FAILED: {e}", flush=True)
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
    try:
        yield
    finally:
        # SOF-43: explicit flush at the PROCESS boundary (per-turn flush lives on the concierge
        # agent object itself) — closes the narrow window where a trace from a request right
        # before shutdown could be lost to the SDK's own background auto-flush interval never
        # getting a chance to fire. Best-effort; must never block shutdown. state._chat_runner is
        # None during the SOF-35 Concierge rebuild (T2.0-T2.2), so this is a no-op until T2.1
        # restores an agent object — safe either way via the getattr/None guards below.
        runner = getattr(state, "_chat_runner", None)
        client = getattr(runner, "_langfuse", None) if runner else None
        if client:
            try:
                client.flush()
            except Exception:
                pass
