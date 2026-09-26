"""OpenRouter support in the LLM layer: provider resolution, the anthropic-key
"sk-or-" auto-detect, the OpenRouter model-id mapping, and the headers/base_url
passed into the anthropic SDK client. No network calls — `anthropic.AsyncAnthropic`
is replaced with a recorder that captures its constructor kwargs.

Live behaviour (streaming, tool use, and whether OpenRouter accepts `cache_control`)
is exercised separately by a one-off smoke script against the real endpoint; see
task-openrouter-report.md for that result.
"""

import logging
from typing import Any

import pytest
from pydantic import SecretStr

from app.agent import llm as llm_module
from app.agent.fake import FakeLLM
from app.agent.llm import (
    OPENROUTER_BASE_URL,
    AnthropicLLM,
    make_llm,
    resolve_llm_mode,
    resolve_llm_model,
)
from app.config import Settings

OR_KEY = "sk-or-v1-" + "b" * 40
ANT_KEY = "sk-ant-" + "a" * 40


class _RecordingAsyncAnthropic:
    """Stand-in for anthropic.AsyncAnthropic: records constructor kwargs instead of
    opening a real client."""

    last_kwargs: dict[str, Any] | None = None

    def __init__(self, **kwargs: Any) -> None:
        _RecordingAsyncAnthropic.last_kwargs = kwargs


@pytest.fixture(autouse=True)
def _recording_client(monkeypatch: pytest.MonkeyPatch) -> None:
    _RecordingAsyncAnthropic.last_kwargs = None
    monkeypatch.setattr(llm_module.anthropic, "AsyncAnthropic", _RecordingAsyncAnthropic)


def _kwargs() -> dict[str, Any]:
    assert _RecordingAsyncAnthropic.last_kwargs is not None
    return _RecordingAsyncAnthropic.last_kwargs


# --- provider mapping -------------------------------------------------------


def test_explicit_openrouter_provider_resolves_and_constructs_anthropic_llm() -> None:
    settings = Settings(llm_provider="openrouter", openrouter_api_key=SecretStr(OR_KEY))
    assert resolve_llm_mode(settings) == "openrouter"
    llm = make_llm(settings)
    assert isinstance(llm, AnthropicLLM)
    assert _kwargs()["api_key"] is None
    assert _kwargs()["auth_token"] == OR_KEY
    assert _kwargs()["base_url"] == OPENROUTER_BASE_URL


def test_llm_base_url_override_is_respected() -> None:
    settings = Settings(
        llm_provider="openrouter",
        openrouter_api_key=SecretStr(OR_KEY),
        llm_base_url="https://gateway.internal/api",
    )
    make_llm(settings)
    assert _kwargs()["base_url"] == "https://gateway.internal/api"


def test_openrouter_provider_falls_back_to_anthropic_field_if_shaped_like_openrouter() -> None:
    settings = Settings(llm_provider="openrouter", anthropic_api_key=SecretStr(OR_KEY))
    assert resolve_llm_mode(settings) == "openrouter"
    make_llm(settings)
    assert _kwargs()["auth_token"] == OR_KEY


def test_openrouter_provider_does_not_fall_back_to_an_unrelated_anthropic_key() -> None:
    settings = Settings(llm_provider="openrouter", anthropic_api_key=SecretStr(ANT_KEY))
    assert resolve_llm_mode(settings) == "fake"


# --- auto-detect by prefix ---------------------------------------------------


def test_autodetect_openrouter_key_under_anthropic_provider_logs_warning_not_error(
    caplog: pytest.LogCaptureFixture,
) -> None:
    settings = Settings(llm_provider="anthropic", anthropic_api_key=SecretStr(OR_KEY))
    assert resolve_llm_mode(settings) == "openrouter"
    with caplog.at_level(logging.WARNING, logger="app.agent.llm"):
        llm = make_llm(settings)
    assert isinstance(llm, AnthropicLLM)
    assert _kwargs()["auth_token"] == OR_KEY
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert any("OpenRouter" in r.message for r in warnings)
    assert not any(OR_KEY in r.message for r in caplog.records)  # never leak the key
    assert not any(r.levelno == logging.ERROR for r in caplog.records)


def test_real_anthropic_key_is_not_mistaken_for_openrouter() -> None:
    settings = Settings(llm_provider="anthropic", anthropic_api_key=SecretStr(ANT_KEY))
    assert resolve_llm_mode(settings) == "anthropic"


# --- model mapping ------------------------------------------------------------


def test_model_mapping_adds_anthropic_namespace_for_openrouter() -> None:
    settings = Settings(
        llm_provider="openrouter", openrouter_api_key=SecretStr(OR_KEY), llm_model="claude-sonnet-5"
    )
    assert resolve_llm_model(settings) == "anthropic/claude-sonnet-5"


def test_model_mapping_leaves_an_already_namespaced_model_alone() -> None:
    settings = Settings(
        llm_provider="openrouter", openrouter_api_key=SecretStr(OR_KEY), llm_model="openai/gpt-4o"
    )
    assert resolve_llm_model(settings) == "openai/gpt-4o"


def test_model_mapping_is_unchanged_for_the_anthropic_provider() -> None:
    settings = Settings(
        llm_provider="anthropic", anthropic_api_key=SecretStr(ANT_KEY), llm_model="claude-sonnet-5"
    )
    assert resolve_llm_model(settings) == "claude-sonnet-5"


def test_make_llm_requests_the_mapped_model() -> None:
    settings = Settings(
        llm_provider="openrouter", openrouter_api_key=SecretStr(OR_KEY), llm_model="claude-sonnet-5"
    )
    llm = make_llm(settings)
    assert isinstance(llm, AnthropicLLM)
    assert llm._model == "anthropic/claude-sonnet-5"


# --- blank key -> fake ---------------------------------------------------------


def test_blank_openrouter_key_falls_back_to_fake_llm_with_error_log(
    caplog: pytest.LogCaptureFixture,
) -> None:
    settings = Settings(llm_provider="openrouter", openrouter_api_key=SecretStr(""))
    assert resolve_llm_mode(settings) == "fake"
    with caplog.at_level(logging.ERROR, logger="app.agent.llm"):
        llm = make_llm(settings)
    assert isinstance(llm, FakeLLM)
    assert any(
        r.levelno == logging.ERROR and "OPENROUTER_API_KEY" in r.message for r in caplog.records
    )


def test_missing_openrouter_key_falls_back_to_fake_llm() -> None:
    settings = Settings(llm_provider="openrouter", openrouter_api_key=None)
    assert resolve_llm_mode(settings) == "fake"
    assert isinstance(make_llm(settings), FakeLLM)


# --- headers passed --------------------------------------------------------


def test_headers_include_referer_and_title() -> None:
    settings = Settings(
        llm_provider="openrouter",
        openrouter_api_key=SecretStr(OR_KEY),
        public_origin="https://gantt-ai-planner.duckdns.org",
    )
    make_llm(settings)
    assert _kwargs()["default_headers"] == {
        "HTTP-Referer": "https://gantt-ai-planner.duckdns.org",
        "X-Title": "Gantt AI Planner",
    }


def test_anthropic_provider_gets_no_openrouter_headers() -> None:
    settings = Settings(llm_provider="anthropic", anthropic_api_key=SecretStr(ANT_KEY))
    make_llm(settings)
    assert _kwargs()["default_headers"] is None
    assert _kwargs()["auth_token"] is None
    assert _kwargs()["api_key"] == ANT_KEY


# --- cache_control (verified live not to be rejected by OpenRouter) ------------


def test_cache_control_stays_enabled_for_openrouter_by_default() -> None:
    settings = Settings(llm_provider="openrouter", openrouter_api_key=SecretStr(OR_KEY))
    llm = make_llm(settings)
    assert isinstance(llm, AnthropicLLM)
    assert llm._supports_cache_control is True


def test_cache_control_can_be_disabled_explicitly() -> None:
    llm = AnthropicLLM(None, "anthropic/claude-sonnet-5", 512, supports_cache_control=False)
    assert llm._supports_cache_control is False
