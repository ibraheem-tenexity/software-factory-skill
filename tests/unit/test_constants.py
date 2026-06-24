"""constants.py — single source of truth for cross-module constants."""
from software_factory import constants
from software_factory.db import _PROJECT_ID_RE          # alias must survive move
from software_factory.console import PROJECT_ID_RE       # re-exported from constants


def test_both_project_id_regexes_exported():
    assert constants.PROJECT_ID_RE is not None
    assert constants.PROJECT_ID_STRICT_RE is not None


def test_strict_regex_is_strict():
    # 8-hex canonical form
    assert constants.PROJECT_ID_STRICT_RE.fullmatch("project-ab12cd34")
    # 16-hex (widened format)
    assert constants.PROJECT_ID_STRICT_RE.fullmatch("project-ab12cd34ef56ab12")
    # 7-hex must fail
    assert not constants.PROJECT_ID_STRICT_RE.fullmatch("project-ab12cd3")
    # uppercase must fail
    assert not constants.PROJECT_ID_STRICT_RE.fullmatch("project-AB12CD34")


def test_loose_regex_is_loose():
    assert constants.PROJECT_ID_RE.fullmatch("project-ab12cd34")
    assert constants.PROJECT_ID_RE.fullmatch("project-test-abc")
    assert not constants.PROJECT_ID_RE.fullmatch("not-a-project")


def test_backward_compat_aliases():
    # Modules that imported the private names directly must still resolve them.
    assert _PROJECT_ID_RE is constants.PROJECT_ID_STRICT_RE
    assert PROJECT_ID_RE is constants.PROJECT_ID_RE


def test_stage_model_has_all_three_stages():
    sm = constants.STAGE_MODEL
    assert sm[1] == "claude-opus-4-8"
    assert sm[2] == "claude-opus-4-8"
    assert sm[3] == "claude-sonnet-4-6"


def test_pipeline_is_union_of_stages():
    assert constants.PIPELINE == constants.STAGE_1 + constants.STAGE_2 + constants.STAGE_3
    assert len(constants.PIPELINE) == 9


def test_runner_keys_covers_both_runtimes():
    assert "claude" in constants.RUNNER_KEYS
    assert "opencode" in constants.RUNNER_KEYS
    assert constants.RUNNER_KEYS["claude"] == "ANTHROPIC_API_KEY"
    assert constants.RUNNER_KEYS["opencode"] == "OPENROUTER_API_KEY"


def test_deploy_db_max_attempts_is_positive_int():
    assert isinstance(constants.DEPLOY_DB_MAX_ATTEMPTS, int)
    assert constants.DEPLOY_DB_MAX_ATTEMPTS > 0
