from dataclasses import asdict
from software_factory.research import CompanyProfile, ResearchError


def _make_profile(**overrides) -> CompanyProfile:
    defaults = dict(
        name="Acme Corp",
        website="https://acme.com",
        industry="Manufacturing",
        size_hint="mid-market",
        sub_focus="Industrial Widgets",
        connected_systems=["SAP", "Salesforce"],
        description="Acme Corp makes widgets.",
        products=["Widget Pro", "Widget Lite"],
        competitors=[{"name": "RivalCo", "url": "https://rivalco.com", "description": "Also makes widgets"}],
        recent_news=["Acme raises $50M Series C"],
        sources=["https://acme.com/about"],
        mode="quick",
    )
    defaults.update(overrides)
    return CompanyProfile(**defaults)


def test_research_error_is_exception():
    e = ResearchError("boom")
    assert isinstance(e, Exception)
    assert str(e) == "boom"


def test_to_dict_is_json_serialisable():
    import json
    profile = _make_profile()
    d = profile.to_dict()
    # must not raise
    json.dumps(d)
    assert d["name"] == "Acme Corp"
    assert d["connected_systems"] == ["SAP", "Salesforce"]


import json
from unittest.mock import patch, MagicMock
from software_factory.research import _exa_search, ResearchError


def _mock_exa_response(results: list[dict]):
    """Build a mock httpx.Response for Exa search."""
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = {"results": results}
    resp.raise_for_status = MagicMock()
    return resp


_EXA_RESULTS = [
    {
        "title": "Acme Corp — Widget Manufacturer",
        "url": "https://acme.com/about",
        "text": "Acme Corp is a mid-market industrial widget manufacturer founded in 2005. "
                "They sell Widget Pro and Widget Lite. Key competitor: RivalCo.",
    },
    {
        "title": "Acme Corp raises $50M Series C",
        "url": "https://techcrunch.com/acme",
        "text": "Acme Corp announced a $50M Series C funding round to expand globally.",
    },
]


def test_exa_search_returns_company_profile():
    with patch("software_factory.research.httpx.post", return_value=_mock_exa_response(_EXA_RESULTS)):
        profile = _exa_search("Acme Corp", "https://acme.com", None, "fake-key")
    assert profile.name == "Acme Corp"
    assert profile.website == "https://acme.com"
    assert profile.mode == "quick"
    assert len(profile.sources) > 0
    assert profile.description  # non-empty


def test_exa_search_uses_provided_website_as_source():
    with patch("software_factory.research.httpx.post", return_value=_mock_exa_response(_EXA_RESULTS)):
        profile = _exa_search("Acme Corp", "https://acme.com", None, "fake-key")
    assert "https://acme.com" in profile.sources


def test_exa_search_raises_on_http_error():
    resp = MagicMock()
    resp.status_code = 401
    resp.raise_for_status.side_effect = Exception("401 Unauthorized")
    with patch("software_factory.research.httpx.post", return_value=resp):
        try:
            _exa_search("Acme Corp", None, None, "bad-key")
            assert False, "expected ResearchError"
        except ResearchError as e:
            assert "Exa" in str(e)


def test_exa_search_handles_empty_results():
    with patch("software_factory.research.httpx.post", return_value=_mock_exa_response([])):
        profile = _exa_search("NoSuchCorp", None, None, "fake-key")
    assert profile.name == "NoSuchCorp"
    assert profile.description == ""
    assert profile.products == []


# Fusion research tests
from software_factory.research import _fusion_research


_FUSION_PROFILE_JSON = json.dumps({
    "name": "Acme Corp",
    "website": "https://acme.com",
    "industry": "Manufacturing",
    "size_hint": "mid-market",
    "sub_focus": "Industrial Widgets",
    "connected_systems": ["SAP", "Salesforce"],
    "description": "Acme Corp is a leading widget manufacturer.",
    "products": ["Widget Pro", "Widget Lite"],
    "competitors": [{"name": "RivalCo", "url": "https://rivalco.com", "description": "Competitor"}],
    "recent_news": ["Acme raises $50M Series C"],
    "sources": ["https://acme.com", "https://techcrunch.com/acme"],
})


def _mock_fusion_response(content: str):
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = {"choices": [{"message": {"content": content}}]}
    resp.raise_for_status = MagicMock()
    return resp


def test_fusion_research_returns_full_company_profile():
    with patch("software_factory.research.httpx.post", return_value=_mock_fusion_response(_FUSION_PROFILE_JSON)):
        profile = _fusion_research("Acme Corp", "https://acme.com", None, "fake-key")
    assert profile.name == "Acme Corp"
    assert profile.industry == "Manufacturing"
    assert profile.size_hint == "mid-market"
    assert profile.sub_focus == "Industrial Widgets"
    assert profile.connected_systems == ["SAP", "Salesforce"]
    assert profile.mode == "deep"
    assert len(profile.competitors) == 1


def test_fusion_research_raises_on_http_error():
    resp = MagicMock()
    resp.raise_for_status.side_effect = Exception("403 Forbidden")
    with patch("software_factory.research.httpx.post", return_value=resp):
        try:
            _fusion_research("Acme Corp", None, None, "bad-key")
            assert False, "expected ResearchError"
        except ResearchError as e:
            assert "Fusion" in str(e)


def test_fusion_research_raises_on_invalid_json():
    with patch("software_factory.research.httpx.post",
               return_value=_mock_fusion_response("not json at all")):
        try:
            _fusion_research("Acme Corp", None, None, "fake-key")
            assert False, "expected ResearchError"
        except ResearchError as e:
            assert "parse" in str(e).lower() or "json" in str(e).lower()


def test_fusion_research_falls_back_on_missing_fields():
    """Fusion response missing optional fields → defaults applied, no KeyError."""
    minimal = json.dumps({"name": "Acme Corp"})
    with patch("software_factory.research.httpx.post",
               return_value=_mock_fusion_response(minimal)):
        profile = _fusion_research("Acme Corp", None, None, "fake-key")
    assert profile.name == "Acme Corp"
    assert profile.industry is None
    assert profile.products == []
    assert profile.connected_systems == []


# Task 4: research_company entry point tests
import os
from software_factory.research import research_company


def test_research_company_quick_dispatches_to_exa(monkeypatch):
    monkeypatch.setenv("EXA_API_KEY", "exa-test-key")
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    with patch("software_factory.research._exa_search",
               return_value=_make_profile(mode="quick")) as mock_exa:
        profile = research_company("Acme Corp", mode="quick")
    mock_exa.assert_called_once_with("Acme Corp", None, None, "exa-test-key")
    assert profile.mode == "quick"


def test_research_company_deep_dispatches_to_fusion(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "or-test-key")
    monkeypatch.delenv("EXA_API_KEY", raising=False)
    with patch("software_factory.research._fusion_research",
               return_value=_make_profile(mode="deep")) as mock_fusion:
        profile = research_company("Acme Corp", mode="deep")
    mock_fusion.assert_called_once_with("Acme Corp", None, None, "or-test-key")
    assert profile.mode == "deep"


def test_research_company_passes_website_and_extra(monkeypatch):
    monkeypatch.setenv("EXA_API_KEY", "exa-test-key")
    with patch("software_factory.research._exa_search",
               return_value=_make_profile()) as mock_exa:
        research_company("Acme Corp", website="https://acme.com", extra="SaaS company", mode="quick")
    mock_exa.assert_called_once_with("Acme Corp", "https://acme.com", "SaaS company", "exa-test-key")


def test_research_company_raises_when_exa_key_missing(monkeypatch):
    monkeypatch.delenv("EXA_API_KEY", raising=False)
    try:
        research_company("Acme Corp", mode="quick")
        assert False, "expected ResearchError"
    except ResearchError as e:
        assert "EXA_API_KEY" in str(e)


def test_research_company_raises_when_openrouter_key_missing(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    try:
        research_company("Acme Corp", mode="deep")
        assert False, "expected ResearchError"
    except ResearchError as e:
        assert "OPENROUTER_API_KEY" in str(e)


def test_research_company_raises_on_invalid_mode(monkeypatch):
    monkeypatch.setenv("EXA_API_KEY", "x")
    try:
        research_company("Acme Corp", mode="turbo")
        assert False, "expected ResearchError"
    except ResearchError as e:
        assert "mode" in str(e).lower()


# ---------------------------------------------------------------------------------------------
# SOF-79: Fusion returns MARKDOWN, not JSON — verified live against the real OpenRouter API
# 2026-07-02 (one real "Stripe" call via `railway run`, ~165s, $0.084, full output examined by
# hand). This fixture reproduces the REAL shape observed (trimmed for test size, not invented):
# "## Panel responses" with three "### <model>" sections (bare JSON — no fencing in the real
# response), then "## Analysis" with **Consensus**/**Contradictions**/**Blind spots**, then a
# final unlabeled top-level JSON object (the cross-model synthesis) nested inside a
# `competitors` list entry near its own end — the exact shape that caught a real bug in this
# session's first parser draft (a naive `rfind("{")` grabbed that nested competitor object
# instead of the outer synthesis, silently returning "Paystack" as the company name for a
# "Stripe" query).
# ---------------------------------------------------------------------------------------------
from software_factory.research import (
    _split_fusion_markdown, _extract_json_block, _synthesized_profile,
    _top_level_json_objects, _extract_bold_section, fusion_research,
)

_REALISTIC_FUSION_MARKDOWN = """\
## Panel responses

### google/gemini-2.5-flash

{
  "name": "Stripe",
  "industry": "Financial Services, SaaS",
  "competitors": [{"name": "PayPal", "url": "https://paypal.com", "description": "Payments"}]
}

### moonshotai/kimi-k2.6

  {
  "name": "Stripe",
  "industry": "Financial Technology",
  "competitors": [{"name": "Adyen", "url": "https://adyen.com", "description": "Payments"}]
  }

### deepseek/deepseek-chat-v3-0324

{
  "name": "Stripe",
  "industry": "Financial Technology",
  "competitors": [{"name": "Block", "url": "https://block.xyz", "description": "Payments"}]
}

## Analysis

**Consensus**

- Stripe is a financial technology company.
- Stripe's website is https://stripe.com.

**Contradictions**

- **Industry**
  - google/gemini-2.5-flash: Financial Services, SaaS
  - moonshotai/kimi-k2.6: Financial Technology

**Blind spots**

- Stripe's exact founding year.

{
  "name": "Stripe",
  "industry": "Financial Technology",
  "competitors": [
    {"name": "PayPal", "url": "https://paypal.com", "description": "Payments"},
    {"name": "Paystack", "url": "https://paystack.com", "description": "African payments"}
  ],
  "sources": ["https://stripe.com"]
}"""


class TestSplitFusionMarkdown:
    def test_finds_all_three_panels_by_model_name(self):
        panels, _analysis = _split_fusion_markdown(_REALISTIC_FUSION_MARKDOWN)
        assert set(panels.keys()) == {
            "google/gemini-2.5-flash", "moonshotai/kimi-k2.6", "deepseek/deepseek-chat-v3-0324"}

    def test_analysis_section_captured(self):
        _panels, analysis = _split_fusion_markdown(_REALISTIC_FUSION_MARKDOWN)
        assert "**Consensus**" in analysis
        assert "**Contradictions**" in analysis

    def test_no_analysis_section_gives_empty_string(self):
        _panels, analysis = _split_fusion_markdown("## Panel responses\n\n### m\n{}")
        assert analysis == ""

    def test_no_panel_section_gives_empty_dict(self):
        panels, _analysis = _split_fusion_markdown("## Analysis\n\n**Consensus**\ntext")
        assert panels == {}


class TestExtractJsonBlock:
    def test_bare_json_indented_panel_still_parses(self):
        # kimi's panel above is indented with a leading two-space "  {" — real observed formatting.
        panels, _ = _split_fusion_markdown(_REALISTIC_FUSION_MARKDOWN)
        parsed = _extract_json_block(panels["moonshotai/kimi-k2.6"])
        assert parsed["name"] == "Stripe"

    def test_fenced_json_panel_parses(self):
        text = "some prose\n```json\n{\"name\": \"Acme\"}\n```\nmore prose"
        assert _extract_json_block(text) == {"name": "Acme"}

    def test_no_json_returns_none(self):
        assert _extract_json_block("just prose, no braces at all") is None

    def test_malformed_json_returns_none_not_raise(self):
        assert _extract_json_block('{"name": "Acme", broken}') is None


class TestTopLevelJsonObjects:
    def test_nested_object_is_not_mistaken_for_a_second_top_level_object(self):
        # Regression for the real bug: a naive rfind("{") on this exact text finds the
        # Paystack competitor's opening brace, not the outer object's.
        text = _split_fusion_markdown(_REALISTIC_FUSION_MARKDOWN)[1]
        objs = _top_level_json_objects(text)
        # Exactly the analysis-section trailing object — nothing nested counted separately.
        assert len(objs) == 1
        assert objs[0]["name"] == "Stripe"
        assert objs[0]["sources"] == ["https://stripe.com"]

    def test_empty_text_returns_empty_list(self):
        assert _top_level_json_objects("") == []


class TestSynthesizedProfile:
    def test_finds_the_real_outer_object_not_the_nested_competitor(self):
        _panels, analysis = _split_fusion_markdown(_REALISTIC_FUSION_MARKDOWN)
        synth = _synthesized_profile(analysis)
        assert synth["name"] == "Stripe"
        assert synth["competitors"][1]["name"] == "Paystack"  # nested data preserved, not lost

    def test_none_when_analysis_has_no_trailing_json(self):
        assert _synthesized_profile("**Consensus**\njust prose, no object") is None


class TestExtractBoldSection:
    def test_extracts_text_up_to_next_bold_heading(self):
        _panels, analysis = _split_fusion_markdown(_REALISTIC_FUSION_MARKDOWN)
        consensus = _extract_bold_section(analysis, "Consensus")
        assert "financial technology company" in consensus
        assert "Contradictions" not in consensus  # didn't swallow the next section

    def test_missing_heading_returns_empty_string(self):
        assert _extract_bold_section("no bold headings here", "Consensus") == ""


class TestFusionResearchPrefersSynthesisOverAnyPanel:
    def test_full_fusion_research_call_uses_the_real_response_shape(self):
        with patch("software_factory.research._fusion_post",
                   return_value=(_REALISTIC_FUSION_MARKDOWN, 0.084)):
            profile = _fusion_research("Stripe", "stripe.com", None, "fake-key")
        assert profile.name == "Stripe"
        assert profile.mode == "deep"
        # The synthesis's 2-competitor list, not any single panel's 1-competitor list.
        assert len(profile.competitors) == 2


class TestGeneralFusionResearchHelper:
    def test_returns_panels_consensus_contradictions_and_cost(self):
        with patch("software_factory.research._fusion_post",
                   return_value=(_REALISTIC_FUSION_MARKDOWN, 0.084)):
            result = fusion_research("What does Stripe do?", api_key="fake-key")
        assert set(result["panels"].keys()) == {
            "google/gemini-2.5-flash", "moonshotai/kimi-k2.6", "deepseek/deepseek-chat-v3-0324"}
        assert "financial technology company" in result["consensus"]
        assert "Industry" in result["contradictions"]
        assert result["cost_usd"] == 0.084

    def test_panel_text_is_raw_not_json_parsed(self):
        """General questions have no reason to produce structured per-panel JSON — panels are
        kept as the model's raw reply text, unlike the company-profile path."""
        with patch("software_factory.research._fusion_post",
                   return_value=(_REALISTIC_FUSION_MARKDOWN, 0.084)):
            result = fusion_research("What does Stripe do?", api_key="fake-key")
        assert isinstance(result["panels"]["google/gemini-2.5-flash"], str)

    def test_raises_when_api_key_missing(self, monkeypatch):
        monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
        try:
            fusion_research("some question")
            assert False, "expected ResearchError"
        except ResearchError as e:
            assert "OPENROUTER_API_KEY" in str(e)
