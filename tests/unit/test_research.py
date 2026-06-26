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


def test_to_prompt_block_contains_key_fields():
    profile = _make_profile()
    block = profile.to_prompt_block()
    assert "Acme Corp" in block
    assert "Manufacturing" in block
    assert "mid-market" in block
    assert "SAP" in block
    assert "Widget Pro" in block
    assert "RivalCo" in block
    assert "Acme raises" in block


def test_to_prompt_block_skips_none_fields():
    profile = _make_profile(industry=None, size_hint=None, sub_focus=None)
    block = profile.to_prompt_block()
    # None fields should not produce a broken "None" line
    assert "None" not in block


def test_to_prompt_block_empty_lists_omitted():
    profile = _make_profile(products=[], competitors=[], recent_news=[], connected_systems=[])
    block = profile.to_prompt_block()
    # empty lists produce no bullet lines
    assert "- " not in block


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
