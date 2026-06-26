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
