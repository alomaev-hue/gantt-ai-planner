import logging

from pydantic import SecretStr

from app.agent.fake import FakeLLM
from app.agent.llm import AnthropicLLM, make_llm, resolve_llm_mode
from app.config import Settings


def test_empty_key_falls_back_to_fake_llm_with_error_log(caplog):
    settings = Settings(llm_provider="anthropic", anthropic_api_key=SecretStr(""))
    assert resolve_llm_mode(settings) == "fake"
    with caplog.at_level(logging.ERROR, logger="app.agent.llm"):
        llm = make_llm(settings)
    assert isinstance(llm, FakeLLM)
    assert any(
        r.levelno == logging.ERROR and "ANTHROPIC_API_KEY" in r.message for r in caplog.records
    )


def test_whitespace_only_key_falls_back_to_fake_llm_with_error_log(caplog):
    settings = Settings(llm_provider="anthropic", anthropic_api_key=SecretStr("  \n"))
    assert resolve_llm_mode(settings) == "fake"
    with caplog.at_level(logging.ERROR, logger="app.agent.llm"):
        llm = make_llm(settings)
    assert isinstance(llm, FakeLLM)
    assert any(
        r.levelno == logging.ERROR and "ANTHROPIC_API_KEY" in r.message for r in caplog.records
    )


def test_missing_key_falls_back_to_fake_llm_with_error_log(caplog):
    settings = Settings(llm_provider="anthropic", anthropic_api_key=None)
    assert resolve_llm_mode(settings) == "fake"
    with caplog.at_level(logging.ERROR, logger="app.agent.llm"):
        llm = make_llm(settings)
    assert isinstance(llm, FakeLLM)
    assert any(
        r.levelno == logging.ERROR and "ANTHROPIC_API_KEY" in r.message for r in caplog.records
    )


def test_real_looking_key_with_anthropic_provider_constructs_anthropic_llm(caplog):
    settings = Settings(llm_provider="anthropic", anthropic_api_key=SecretStr("sk-ant-" + "a" * 40))
    assert resolve_llm_mode(settings) == "anthropic"
    with caplog.at_level(logging.ERROR, logger="app.agent.llm"):
        llm = make_llm(settings)
    assert isinstance(llm, AnthropicLLM)
    assert not any("ANTHROPIC_API_KEY" in r.message for r in caplog.records)


def test_fake_provider_uses_fake_llm_even_with_a_real_key_and_no_error_log(caplog):
    settings = Settings(llm_provider="fake", anthropic_api_key=SecretStr("sk-ant-" + "a" * 40))
    assert resolve_llm_mode(settings) == "fake"
    with caplog.at_level(logging.ERROR, logger="app.agent.llm"):
        llm = make_llm(settings)
    assert isinstance(llm, FakeLLM)
    assert not any("ANTHROPIC_API_KEY" in r.message for r in caplog.records)
