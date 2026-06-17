"""Dependency disposition: how each required token is satisfied at the deps gate."""
from software_factory.deps import (
    classify_dep, default_dispositions, resolve_satisfied, extract_env_creds,
)


def test_classify_db_tokens_deploy_db_and_railway_nextauth_mcp():
    # DB/Supabase tokens are now factory-provided (deploy-db), NOT agent-provisioned via Supabase.
    for n in ["SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY", "DATABASE_URL"]:
        assert classify_dep(n) == "deploy-db", n
    for n in ["RAILWAY_TOKEN", "NEXTAUTH_SECRET", "NEXTAUTH_URL"]:
        assert classify_dep(n) == "mcp", n


def test_runner_llm_keys_never_classify_env(monkeypatch):
    # Operator rule: a built app must NEVER inherit the runner's own keys — there is no
    # 'env' disposition. LLM keys default to mock regardless of what the runner env holds.
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-x")
    assert classify_dep("OPENROUTER_API_KEY") == "mock"
    assert classify_dep("OPENAI_API_KEY") == "mock"
    assert classify_dep("ANTHROPIC_API_KEY") == "mock"


def test_classify_openrouter_never_auto_pauses(monkeypatch):
    # SPEC §3 zero-touch: OPENROUTER classifies mock — never auto-'provide'. 'provide'
    # only happens when the operator explicitly sets it at the gate.
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    assert classify_dep("OPENROUTER_API_KEY") == "mock"


def test_classify_external_integrations_default_to_mock():
    for n in ["ENTRA_CLIENT_ID", "ADP_CLIENT_SECRET", "ECLIPSE_API_KEY", "SENDGRID_API_KEY"]:
        assert classify_dep(n) == "mock", n


def test_default_dispositions_maps_every_required(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-x")
    d = default_dispositions(["OPENROUTER_API_KEY", "SUPABASE_URL", "ADP_CLIENT_ID", "NEXTAUTH_SECRET"])
    assert d == {"OPENROUTER_API_KEY": "mock", "SUPABASE_URL": "deploy-db",
                 "ADP_CLIENT_ID": "mock", "NEXTAUTH_SECRET": "mcp"}


def test_resolve_satisfied_mock_and_mcp_autosatisfy():
    req = ["SUPABASE_URL", "ADP_CLIENT_ID"]
    disp = {"SUPABASE_URL": "mcp", "ADP_CLIENT_ID": "mock"}
    assert resolve_satisfied(req, disp, provided_names=[]) is True


def test_stale_env_disposition_resolves_as_mock_not_runner_key(monkeypatch):
    # Runs persisted before 'env' was removed may still carry it; it must degrade to mock
    # (still satisfied — no re-pause) and never signal "use the runner's key".
    assert resolve_satisfied(["OPENAI_API_KEY"], {"OPENAI_API_KEY": "env"},
                             provided_names=[]) is True


def test_resolve_satisfied_provide_needs_a_value():
    req = ["OPENROUTER_API_KEY"]
    disp = {"OPENROUTER_API_KEY": "provide"}
    assert resolve_satisfied(req, disp, provided_names=[]) is False
    assert resolve_satisfied(req, disp, provided_names=["OPENROUTER_API_KEY"]) is True


def test_resolve_satisfied_uses_default_when_disposition_missing():
    # ADP defaults to mock → satisfied without a value or explicit disposition
    assert resolve_satisfied(["ADP_CLIENT_ID"], {}, provided_names=[]) is True


def test_extract_env_creds_handles_strings_and_dicts():
    deps = {
        "OPENROUTER_API_KEY": {"disposition": "provide", "value": "sk-or-x"},
        "ADP_CLIENT_ID": {"disposition": "mock"},          # no value → not in env
        "LEGACY_KEY": "rawvalue",                            # legacy string payload
        "BLANK": {"disposition": "provide", "value": ""},   # empty → skipped
    }
    assert extract_env_creds(deps) == {"OPENROUTER_API_KEY": "sk-or-x", "LEGACY_KEY": "rawvalue"}


def test_openrouter_absent_from_env_auto_classifies_mock(monkeypatch):
    # SPEC §3 (zero-touch): when the LLM key is NOT available, the app ships with a WORKING
    # mock (the SKILL's mock guidance) instead of pausing the pipeline for a human.
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    assert classify_dep("OPENROUTER_API_KEY") == "mock"


# ---------- deploy-db disposition (no agent Supabase access) ----------

def test_db_tokens_classify_as_deploy_db():
    from software_factory import deps
    for t in ("DATABASE_URL", "SUPABASE_URL", "SUPABASE_ANON_KEY", "SUPABASE_SERVICE_ROLE_KEY",
              "POSTGRES_PASSWORD", "DB_URL", "PG_HOST"):
        assert deps.classify_dep(t) == "deploy-db", t
    assert deps.classify_dep("NEXTAUTH_SECRET") == "mcp"
    assert deps.classify_dep("RAILWAY_TOKEN") == "mcp"
    assert deps.classify_dep("OPENROUTER_API_KEY") == "mock"


def test_deploy_db_is_auto_satisfied():
    from software_factory import deps
    assert deps.resolve_satisfied(["DATABASE_URL"], {"DATABASE_URL": "deploy-db"}, [])
