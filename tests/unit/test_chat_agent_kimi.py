"""Concierge model selection (gpt-4o vs Kimi via OpenRouter).

SOF-35: the malformed-tool-args degradation tests that lived here depended on the removed
ChatAgentRunner/make_tools (OpenAI Agents SDK) — deleted, not ported; the LangChain rebuild
(T2.1/T2.2) ships its own tests against the new architecture."""
from software_factory.chat_agent import select_chat_model, chat_model_label


def test_default_is_gpt5_4_when_openai_key_present(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-x")
    monkeypatch.delenv("SF_CHAT_MODEL", raising=False)
    assert select_chat_model() == "gpt-5.4"          # default bumped from gpt-4o
    assert chat_model_label() == "gpt-5.4"


def test_sf_chat_model_passes_through_an_explicit_openai_id(monkeypatch):
    # The no-redeploy rollback lever: any non-kimi SF_CHAT_MODEL is used verbatim as the OpenAI id.
    monkeypatch.setenv("OPENAI_API_KEY", "sk-x")
    monkeypatch.setenv("SF_CHAT_MODEL", "gpt-4o")
    assert select_chat_model() == "gpt-4o" and chat_model_label() == "gpt-4o"


def test_kimi_when_only_openrouter_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("SF_CHAT_MODEL", raising=False)
    monkeypatch.setenv("OPENROUTER_API_KEY", "or-x")
    m = select_chat_model()
    assert m != "gpt-4o" and m.model == "moonshotai/kimi-k2.7-code"


def test_sf_chat_model_kimi_forces_kimi_even_with_openai_key(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-x")
    monkeypatch.setenv("OPENROUTER_API_KEY", "or-x")
    monkeypatch.setenv("SF_CHAT_MODEL", "kimi")
    assert select_chat_model().model == "moonshotai/kimi-k2.7-code"


def test_sf_chat_model_gpt4o_is_the_rollback(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "or-x")
    monkeypatch.setenv("SF_CHAT_MODEL", "gpt-4o")
    assert select_chat_model() == "gpt-4o"
