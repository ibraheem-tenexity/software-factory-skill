"""Dependency disposition: how each required token is satisfied at the deps gate."""
from software_factory.deps import (
    classify_dep, default_dispositions, resolve_satisfied, extract_env_creds,
)


def test_classify_supabase_and_db_and_railway_and_nextauth_are_mcp():
    for n in ["SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY", "DATABASE_URL",
              "RAILWAY_TOKEN", "NEXTAUTH_SECRET", "NEXTAUTH_URL"]:
        assert classify_dep(n) == "mcp", n


def test_classify_runner_llm_keys_are_env():
    assert classify_dep("OPENAI_API_KEY") == "env"
    assert classify_dep("ANTHROPIC_API_KEY") == "env"


def test_classify_openrouter_is_env_aware(monkeypatch):
    # SPEC §3 zero-touch: present in the runner env -> inherit (env); absent -> working mock.
    # 'provide' must never become a hidden manual pause on the default path.
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-x")
    assert classify_dep("OPENROUTER_API_KEY") == "env"
    monkeypatch.delenv("OPENROUTER_API_KEY")
    assert classify_dep("OPENROUTER_API_KEY") == "mock"


def test_classify_external_integrations_default_to_mock():
    for n in ["ENTRA_CLIENT_ID", "ADP_CLIENT_SECRET", "ECLIPSE_API_KEY", "SENDGRID_API_KEY"]:
        assert classify_dep(n) == "mock", n


def test_default_dispositions_maps_every_required(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-x")
    d = default_dispositions(["OPENROUTER_API_KEY", "SUPABASE_URL", "ADP_CLIENT_ID"])
    assert d == {"OPENROUTER_API_KEY": "env", "SUPABASE_URL": "mcp", "ADP_CLIENT_ID": "mock"}


def test_resolve_satisfied_mock_mcp_env_autosatisfy():
    req = ["SUPABASE_URL", "ADP_CLIENT_ID", "OPENAI_API_KEY"]
    disp = {"SUPABASE_URL": "mcp", "ADP_CLIENT_ID": "mock", "OPENAI_API_KEY": "env"}
    assert resolve_satisfied(req, disp, provided_names=[]) is True


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
