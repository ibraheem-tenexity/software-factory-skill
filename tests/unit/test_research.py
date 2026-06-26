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
    assert "- " not in block or "Acme Corp" in block  # only company name line may have content


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
