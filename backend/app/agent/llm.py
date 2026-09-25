import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any, Protocol

import anthropic

from app.config import Settings

UNAVAILABLE = "LLM временно недоступна, попробуйте позже"

logger = logging.getLogger("app.agent.llm")


@dataclass(frozen=True)
class LLMToolCall:
    id: str
    name: str
    input: dict[str, Any]


@dataclass(frozen=True)
class LLMTurnResult:
    text: str
    tool_calls: list[LLMToolCall]
    stop_reason: str
    content: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True)
class TextDelta:
    text: str


@dataclass(frozen=True)
class Completed:
    result: LLMTurnResult


LLMEvent = TextDelta | Completed


class LLMError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class LLM(Protocol):
    def stream(
        self,
        *,
        system: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        messages: list[dict[str, Any]],
    ) -> AsyncIterator[LLMEvent]: ...


class AnthropicLLM:
    def __init__(self, api_key: str, model: str, max_tokens: int) -> None:
        self._client = anthropic.AsyncAnthropic(
            api_key=api_key, max_retries=2, timeout=anthropic.Timeout(60.0, connect=5.0)
        )
        self._model = model
        self._max_tokens = max_tokens

    async def stream(
        self,
        *,
        system: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        messages: list[dict[str, Any]],
    ) -> AsyncIterator[LLMEvent]:
        cached = (
            [*tools[:-1], {**tools[-1], "cache_control": {"type": "ephemeral"}}] if tools else []
        )
        try:
            async with self._client.messages.stream(
                model=self._model,
                max_tokens=self._max_tokens,
                system=system,  # type: ignore[arg-type]
                tools=cached,  # type: ignore[arg-type]
                messages=messages,  # type: ignore[arg-type]
            ) as stream:
                async for event in stream:
                    if event.type == "text":
                        yield TextDelta(event.text)
                final = await stream.get_final_message()
        except anthropic.RateLimitError as exc:
            raise LLMError(
                "llm_rate_limited", "Превышен лимит запросов к LLM, попробуйте через минуту"
            ) from exc
        except (
            anthropic.APITimeoutError,
            anthropic.APIConnectionError,
            anthropic.APIStatusError,
        ) as exc:
            raise LLMError("llm_unavailable", UNAVAILABLE) from exc
        content = [block.model_dump(exclude_none=True) for block in final.content]
        calls = [
            LLMToolCall(b.id, b.name, dict(b.input)) for b in final.content if b.type == "tool_use"
        ]
        text = "".join(b.text for b in final.content if b.type == "text")
        yield Completed(
            LLMTurnResult(
                text=text, tool_calls=calls, stop_reason=final.stop_reason or "", content=content
            )
        )


def make_llm(settings: Settings) -> LLM:
    key = settings.anthropic_api_key
    key_value = key.get_secret_value() if key is not None else ""
    if settings.llm_provider == "anthropic" and key_value.strip():
        return AnthropicLLM(key_value, settings.llm_model, settings.llm_max_tokens)
    if settings.llm_provider == "anthropic":
        # The production secret file is created empty by bootstrap.sh until the owner
        # fills it in — never log the key value itself, just that it's missing.
        logger.warning("ANTHROPIC_API_KEY не задан, используется демо-режим без LLM")

    from app.agent.fake import FakeLLM

    return FakeLLM()
