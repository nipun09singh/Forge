"""LLM client wrapper for Forge meta-agents and generated agencies."""

from __future__ import annotations

import asyncio
import json
import os
import logging
import time
from typing import Any

from openai import AsyncOpenAI
from pydantic import BaseModel

logger = logging.getLogger(__name__)


async def _retry_with_backoff(
    coro_factory,
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 30.0,
    retryable_errors: tuple = (),
):
    """Retry an async operation with exponential backoff."""
    last_error = None
    for attempt in range(max_retries + 1):
        try:
            return await coro_factory()
        except Exception as e:
            last_error = e
            error_str = str(e).lower()
            status_code = getattr(e, 'status_code', None)

            # Determine if retryable
            is_rate_limit = status_code == 429 or "rate limit" in error_str or "rate_limit" in error_str
            is_timeout = "timeout" in error_str or "timed out" in error_str
            is_connection = "connection" in error_str or "connect" in error_str
            is_server_error = status_code and 500 <= status_code < 600
            is_retryable = is_rate_limit or is_timeout or is_connection or is_server_error

            if not is_retryable or attempt >= max_retries:
                raise

            delay = min(base_delay * (2 ** attempt), max_delay)
            if is_rate_limit:
                # Rate limits often have retry-after headers
                retry_after = getattr(e, 'retry_after', None)
                if retry_after:
                    delay = max(delay, float(retry_after))

            logger.warning(
                f"LLM call failed (attempt {attempt + 1}/{max_retries + 1}): {e}. "
                f"Retrying in {delay:.1f}s..."
            )
            await asyncio.sleep(delay)

    raise last_error


class LLMClient:
    """
    Wrapper around OpenAI-compatible LLM APIs.
    
    Features:
    - Configurable provider (OpenAI, Azure, local, etc.)
    - Structured output via JSON mode
    - Automatic retry with backoff
    - Token usage tracking
    """

    def __init__(
        self,
        model: str | None = None,
        api_key: str | None = None,
        base_url: str | None = None,
        temperature: float = 0.7,
        max_retries: int = 3,
    ):
        self.model = model or os.getenv("FORGE_MODEL", "gpt-4")
        self.temperature = temperature
        self.max_retries = max_retries
        self.total_tokens_used = 0

        client_kwargs: dict[str, Any] = {"max_retries": max_retries}
        if api_key:
            client_kwargs["api_key"] = api_key
        elif os.getenv("OPENAI_API_KEY"):
            client_kwargs["api_key"] = os.getenv("OPENAI_API_KEY")
        if base_url:
            client_kwargs["base_url"] = base_url
        elif os.getenv("OPENAI_BASE_URL"):
            client_kwargs["base_url"] = os.getenv("OPENAI_BASE_URL")

        self.client = AsyncOpenAI(**client_kwargs)

    async def complete(
        self,
        messages: list[dict[str, str]],
        temperature: float | None = None,
        max_tokens: int | None = None,
        model: str | None = None,
    ) -> str:
        """Simple completion — returns text response."""
        kwargs: dict[str, Any] = {
            "model": model or self.model,
            "messages": messages,
            "temperature": temperature if temperature is not None else self.temperature,
        }
        if max_tokens:
            kwargs["max_tokens"] = max_tokens

        response = await _retry_with_backoff(
            lambda: self.client.chat.completions.create(**kwargs),
            max_retries=self.max_retries,
        )
        self._track_usage(response)
        if not response.choices:
            return ""
        return response.choices[0].message.content or ""

    async def complete_structured(
        self,
        messages: list[dict[str, str]],
        response_model: type[BaseModel],
        temperature: float | None = None,
        model: str | None = None,
    ) -> BaseModel:
        """
        Structured completion — returns a Pydantic model instance.
        
        Uses JSON mode and instructs the LLM to produce valid JSON
        matching the schema.
        """
        schema = response_model.model_json_schema()
        schema_str = json.dumps(schema, indent=2)

        # Append schema instruction to messages
        enhanced_messages = list(messages)
        enhanced_messages.append({
            "role": "user",
            "content": (
                f"Respond with valid JSON matching this schema:\n"
                f"```json\n{schema_str}\n```\n"
                f"Return ONLY the JSON object, no other text."
            ),
        })

        kwargs: dict[str, Any] = {
            "model": model or self.model,
            "messages": enhanced_messages,
            "temperature": temperature if temperature is not None else self.temperature,
        }

        # Try with JSON mode first, fall back without it for models that don't support it
        try:
            kwargs["response_format"] = {"type": "json_object"}
            response = await _retry_with_backoff(
                lambda: self.client.chat.completions.create(**kwargs),
                max_retries=self.max_retries,
            )
        except Exception as e:
            if "response_format" in str(e) or "json_object" in str(e):
                logger.warning(f"Model doesn't support JSON mode, retrying without response_format")
                kwargs.pop("response_format", None)
                response = await _retry_with_backoff(
                    lambda: self.client.chat.completions.create(**kwargs),
                    max_retries=self.max_retries,
                )
            else:
                raise
        self._track_usage(response)
        if not response.choices:
            raise ValueError("LLM returned empty choices array — content may have been filtered")
        content = response.choices[0].message.content or "{}"

        # Parse and validate
        try:
            # Strip markdown code fences if present
            content_clean = content.strip()
            if content_clean.startswith("```"):
                content_clean = content_clean.split("\n", 1)[1] if "\n" in content_clean else content_clean[3:]
                if content_clean.endswith("```"):
                    content_clean = content_clean[:-3]
                content_clean = content_clean.strip()
            data = json.loads(content_clean)
            return response_model.model_validate(data)
        except (json.JSONDecodeError, Exception) as e:
            logger.error(f"Failed to parse structured response: {e}\nContent: {content[:500]}")
            raise ValueError(f"LLM returned invalid structured output: {e}") from e

    async def complete_with_tools(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        temperature: float | None = None,
        model: str | None = None,
    ) -> dict[str, Any]:
        """Completion with function/tool calling."""
        kwargs: dict[str, Any] = {
            "model": model or self.model,
            "messages": messages,
            "temperature": temperature if temperature is not None else self.temperature,
        }
        if tools:
            kwargs["tools"] = tools

        response = await _retry_with_backoff(
            lambda: self.client.chat.completions.create(**kwargs),
            max_retries=self.max_retries,
        )
        self._track_usage(response)
        if not response.choices:
            return {"content": None}
        choice = response.choices[0]

        result: dict[str, Any] = {"content": choice.message.content}
        if choice.message.tool_calls:
            result["tool_calls"] = [
                {
                    "id": tc.id,
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    },
                }
                for tc in choice.message.tool_calls
            ]
        return result

    def _track_usage(self, response: Any) -> None:
        """Track token usage."""
        if hasattr(response, "usage") and response.usage:
            self.total_tokens_used += response.usage.total_tokens
            logger.debug(
                f"Tokens used: {response.usage.total_tokens} "
                f"(prompt: {response.usage.prompt_tokens}, "
                f"completion: {response.usage.completion_tokens})"
            )

    def get_async_client(self) -> AsyncOpenAI:
        """Get the underlying AsyncOpenAI client for direct use."""
        return self.client
