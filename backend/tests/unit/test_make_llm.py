import logging

from pydantic import SecretStr

from app.agent.fake import FakeLLM
from app.agent.llm import AnthropicLLM, make_llm
from app.config import Settings


def test_empty_key_falls_back_to_fake_llm_with_warning(caplog):
    settings = Settings(llm_provider="anthropic", anthropic_api_key=SecretStr(""))
    with caplog.at_level(logging.WARNING, logger="app.agent.llm"):
        llm = make_llm(settings)
    assert isinstance(llm, FakeLLM)
    assert any("ANTHROPIC_API_KEY" in r.message for r in caplog.records)


def test_whitespace_only_key_falls_back_to_fake_llm_with_warning(caplog):
    settings = Settings(llm_provider="anthropic", anthropic_api_key=SecretStr("  \n"))
    with caplog.at_level(logging.WARNING, logger="app.agent.llm"):
        llm = make_llm(settings)
    assert isinstance(llm, FakeLLM)
    assert any("ANTHROPIC_API_KEY" in r.message for r in caplog.records)


def test_missing_key_falls_back_to_fake_llm_with_warning(caplog):
    settings = Settings(llm_provider="anthropic", anthropic_api_key=None)
    with caplog.at_level(logging.WARNING, logger="app.agent.llm"):
        llm = make_llm(settings)
    assert isinstance(llm, FakeLLM)
    assert any("ANTHROPIC_API_KEY" in r.message for r in caplog.records)


def test_real_looking_key_with_anthropic_provider_constructs_anthropic_llm(caplog):
    settings = Settings(llm_provider="anthropic", anthropic_api_key=SecretStr("sk-ant-" + "a" * 40))
    with caplog.at_level(logging.WARNING, logger="app.agent.llm"):
        llm = make_llm(settings)
    assert isinstance(llm, AnthropicLLM)
    assert not any("ANTHROPIC_API_KEY" in r.message for r in caplog.records)


def test_fake_provider_uses_fake_llm_even_with_a_real_key_and_no_warning(caplog):
    settings = Settings(llm_provider="fake", anthropic_api_key=SecretStr("sk-ant-" + "a" * 40))
    with caplog.at_level(logging.WARNING, logger="app.agent.llm"):
        llm = make_llm(settings)
    assert isinstance(llm, FakeLLM)
    assert not any("ANTHROPIC_API_KEY" in r.message for r in caplog.records)
