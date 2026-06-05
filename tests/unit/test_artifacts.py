"""Pipeline-1 completeness gate: the mechanical teeth behind "the orchestrator must not consider
part 1 done before a validated PRD + architecture." No human approval — a code check the
orchestrator can't fake past, same spirit as merge_if_green for tickets.
"""
from software_factory import artifacts


def test_verify_passes_when_all_paths_exist_and_nonempty(tmp_path):
    (tmp_path / "PRD.md").write_text("real prd")
    (tmp_path / "architecture.svg").write_text("<svg/>")
    ok, missing = artifacts.verify(str(tmp_path), ["PRD.md", "architecture.svg"])
    assert ok is True and missing == []


def test_verify_flags_missing_and_empty(tmp_path):
    (tmp_path / "PRD.md").write_text("real prd")
    (tmp_path / "architecture.md").write_text("")          # exists but empty -> not real
    ok, missing = artifacts.verify(str(tmp_path), ["PRD.md", "architecture.md", "architecture.svg"])
    assert ok is False
    assert set(missing) == {"architecture.md", "architecture.svg"}


GOOD_PRD = """# PRD
## Competitor landscape
- Acme — https://acme.com — does X
- Beta — https://beta.io — does Y
- Gamma — https://gamma.dev — does Z
## Acceptance criteria
- Given a visitor, when they submit a name, then it appears in the list (verify: Playwright)
## Ticket seeds
- seed: guestbook form
"""


def test_prd_is_complete_accepts_a_real_prd():
    ok, reasons = artifacts.prd_is_complete(GOOD_PRD)
    assert ok is True, reasons


def test_prd_is_complete_rejects_too_few_sources():
    text = GOOD_PRD.replace("- Beta — https://beta.io — does Y\n", "").replace("- Gamma — https://gamma.dev — does Z\n", "")
    ok, reasons = artifacts.prd_is_complete(text)
    assert ok is False
    assert any("product" in r.lower() or "url" in r.lower() or "source" in r.lower() for r in reasons)


def test_prd_is_complete_requires_acceptance_and_ticket_seeds():
    text = "# PRD\nhttps://a.com https://b.com https://c.com\n(no acceptance, no tickets)"
    ok, reasons = artifacts.prd_is_complete(text)
    assert ok is False
    assert any("acceptance" in r.lower() for r in reasons)
    assert any("ticket" in r.lower() for r in reasons)


ARCH_WITH_TOKENS = """\
# Architecture

## Required Tokens

- `RAILWAY_TOKEN` — deploy to Railway
- `SUPABASE_URL` — Supabase project URL
- `SUPABASE_KEY` — Supabase anon key
- `OPENAI_API_KEY` — LLM calls

## Data Model
...
"""


def test_parse_required_tokens_extracts_all():
    tokens = artifacts.parse_required_tokens(ARCH_WITH_TOKENS)
    names = [t["name"] for t in tokens]
    assert "RAILWAY_TOKEN" in names
    assert "SUPABASE_URL" in names
    assert "SUPABASE_KEY" in names
    assert "OPENAI_API_KEY" in names
    assert len(tokens) == 4


def test_parse_required_tokens_provider_from_prefix():
    tokens = artifacts.parse_required_tokens(ARCH_WITH_TOKENS)
    by_name = {t["name"]: t for t in tokens}
    assert by_name["RAILWAY_TOKEN"]["provider"] == "Railway"
    assert by_name["SUPABASE_URL"]["provider"] == "Supabase"


def test_parse_required_tokens_empty_input():
    assert artifacts.parse_required_tokens("") == []
    assert artifacts.parse_required_tokens(None) == []


def test_parse_required_tokens_no_section():
    text = "# Architecture\n## Data Model\nSOME_TOKEN_KEY in prose"
    assert artifacts.parse_required_tokens(text) == []


def test_parse_required_tokens_deduplicates():
    text = "## Required Tokens\n- RAILWAY_TOKEN\n- RAILWAY_TOKEN again\n"
    tokens = artifacts.parse_required_tokens(text)
    assert len(tokens) == 1


def test_parse_required_tokens_dependencies_heading():
    text = "## Dependencies\n- STRIPE_SECRET_KEY for payments\n## Next\n"
    tokens = artifacts.parse_required_tokens(text)
    assert len(tokens) == 1
    assert tokens[0]["name"] == "STRIPE_SECRET_KEY"
