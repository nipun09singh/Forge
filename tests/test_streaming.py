"""Tests for forge.runtime.streaming"""

import pytest
from types import SimpleNamespace

from forge.runtime.streaming import (
    StreamingResponse,
    TokenChunk,
    OpenAIStreamProvider,
    AnthropicStreamProvider,
    GenericStreamProvider,
    detect_provider,
    stream_llm_response,
)


# ---------------------------------------------------------------------------
# Helpers — lightweight fakes used across test classes
# ---------------------------------------------------------------------------

def _ns(**kw):
    """Convenience wrapper for SimpleNamespace."""
    return SimpleNamespace(**kw)


def _make_openai_chunk(content=None, tool_calls=None, finish_reason=None):
    """Build a fake OpenAI-style streaming chunk."""
    delta = _ns(content=content, tool_calls=tool_calls)
    choice = _ns(delta=delta, finish_reason=finish_reason)
    return _ns(choices=[choice])


class _AsyncIter:
    """Turn a list into an async iterator."""

    def __init__(self, items):
        self._items = items
        self._idx = 0

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self._idx >= len(self._items):
            raise StopAsyncIteration
        item = self._items[self._idx]
        self._idx += 1
        return item


class _FakeOpenAIClient:
    """Mimics ``openai.AsyncOpenAI`` just enough for streaming tests."""

    def __init__(self, chunks):
        self.chat = _ns(completions=_ns(create=self._create))
        self._chunks = chunks

    async def _create(self, **kwargs):
        return _AsyncIter(self._chunks)


class _FakeOpenAIClientNonStream:
    """Non-streaming OpenAI-style client for GenericStreamProvider."""

    def __init__(self, response):
        self.chat = _ns(completions=_ns(create=self._create))
        self._response = response

    async def _create(self, **kwargs):
        return self._response


# ---------------------------------------------------------------------------
# Original tests (unchanged)
# ---------------------------------------------------------------------------

class TestTokenChunk:
    def test_creation(self):
        chunk = TokenChunk(delta="hello")
        assert chunk.delta == "hello"
        assert not chunk.done

    def test_done_chunk(self):
        chunk = TokenChunk(delta="", full_text="complete", done=True)
        assert chunk.done
        assert chunk.full_text == "complete"

    def test_metadata(self):
        chunk = TokenChunk(delta="x", metadata={"tool_calls": []})
        assert "tool_calls" in chunk.metadata


class TestStreamingResponse:
    def test_append(self):
        sr = StreamingResponse()
        sr.append("hello ")
        sr.append("world")
        assert sr.full_text == "hello world"
        assert len(sr.chunks) == 2

    def test_finalize(self):
        sr = StreamingResponse()
        sr.append("test")
        sr.finalize()
        assert sr.done


# ---------------------------------------------------------------------------
# Provider detection
# ---------------------------------------------------------------------------

class TestDetectProvider:
    def test_model_prefix_gpt(self):
        provider = detect_provider(object(), model="gpt-4")
        assert isinstance(provider, OpenAIStreamProvider)

    def test_model_prefix_claude(self):
        provider = detect_provider(object(), model="claude-3-opus")
        assert isinstance(provider, AnthropicStreamProvider)

    def test_model_prefix_o1(self):
        provider = detect_provider(object(), model="o1-preview")
        assert isinstance(provider, OpenAIStreamProvider)

    def test_unknown_falls_back_to_generic(self):
        provider = detect_provider(object(), model="my-custom-model")
        assert isinstance(provider, GenericStreamProvider)


# ---------------------------------------------------------------------------
# OpenAIStreamProvider
# ---------------------------------------------------------------------------

class TestOpenAIStreamProvider:
    @pytest.mark.asyncio
    async def test_text_streaming(self):
        chunks = [
            _make_openai_chunk(content="Hello"),
            _make_openai_chunk(content=" world"),
            _make_openai_chunk(finish_reason="stop"),
        ]
        client = _FakeOpenAIClient(chunks)
        provider = OpenAIStreamProvider()

        results = []
        async for tok in provider.stream(client, messages=[], model="gpt-4"):
            results.append(tok)

        # Two text chunks + one final done chunk
        assert len(results) == 3
        assert results[0].delta == "Hello"
        assert results[1].delta == " world"
        assert results[2].done
        assert results[2].full_text == "Hello world"

    @pytest.mark.asyncio
    async def test_tool_calls(self):
        tc = _ns(index=0, id="call_1", function=_ns(name="my_tool", arguments='{"a":1}'))
        chunks = [
            _make_openai_chunk(tool_calls=[tc]),
            _make_openai_chunk(finish_reason="tool_calls"),
        ]
        client = _FakeOpenAIClient(chunks)
        provider = OpenAIStreamProvider()

        results = []
        async for tok in provider.stream(client, messages=[], model="gpt-4"):
            results.append(tok)

        final = results[-1]
        assert final.done
        assert final.metadata["tool_calls"][0]["id"] == "call_1"
        assert final.metadata["tool_calls"][0]["function"]["name"] == "my_tool"


# ---------------------------------------------------------------------------
# AnthropicStreamProvider
# ---------------------------------------------------------------------------

class TestAnthropicStreamProvider:
    @pytest.mark.asyncio
    async def test_text_streaming(self):
        events = [
            _ns(type="content_block_start", content_block=_ns(type="text")),
            _ns(type="content_block_delta", delta=_ns(type="text_delta", text="Hi")),
            _ns(type="content_block_delta", delta=_ns(type="text_delta", text=" there")),
            _ns(type="content_block_stop"),
            _ns(type="message_stop"),
        ]

        class _FakeAnthropicClient:
            def __init__(self):
                self.messages = _ns(create=self._create)
            async def _create(self, **kwargs):
                return _AsyncIter(events)

        provider = AnthropicStreamProvider()
        results = []
        msgs = [{"role": "system", "content": "Be helpful"}, {"role": "user", "content": "Hi"}]
        async for tok in provider.stream(_FakeAnthropicClient(), messages=msgs, model="claude-3-opus"):
            results.append(tok)

        assert results[0].delta == "Hi"
        assert results[1].delta == " there"
        assert results[-1].done
        assert results[-1].full_text == "Hi there"

    @pytest.mark.asyncio
    async def test_tool_calls(self):
        events = [
            _ns(type="content_block_start", content_block=_ns(type="tool_use", id="tc_1", name="search")),
            _ns(type="content_block_delta", delta=_ns(type="input_json_delta", partial_json='{"q":')),
            _ns(type="content_block_delta", delta=_ns(type="input_json_delta", partial_json='"test"}')),
            _ns(type="content_block_stop"),
            _ns(type="message_stop"),
        ]

        class _FakeAnthropicClient:
            def __init__(self):
                self.messages = _ns(create=self._create)
            async def _create(self, **kwargs):
                return _AsyncIter(events)

        provider = AnthropicStreamProvider()
        results = []
        async for tok in provider.stream(_FakeAnthropicClient(), messages=[], model="claude-3-opus"):
            results.append(tok)

        final = results[-1]
        assert final.done
        assert len(final.metadata["tool_calls"]) == 1
        assert final.metadata["tool_calls"][0]["function"]["name"] == "search"
        assert final.metadata["tool_calls"][0]["function"]["arguments"] == '{"q":"test"}'

    def test_convert_tools(self):
        openai_tools = [
            {
                "type": "function",
                "function": {
                    "name": "get_weather",
                    "description": "Get weather",
                    "parameters": {"type": "object", "properties": {"city": {"type": "string"}}},
                },
            }
        ]
        converted = AnthropicStreamProvider._convert_tools(openai_tools)
        assert converted[0]["name"] == "get_weather"
        assert "input_schema" in converted[0]


# ---------------------------------------------------------------------------
# GenericStreamProvider
# ---------------------------------------------------------------------------

class TestGenericStreamProvider:
    @pytest.mark.asyncio
    async def test_non_streaming_response(self):
        message = _ns(content="Full response", tool_calls=None)
        choice = _ns(message=message)
        response = _ns(choices=[choice], usage=_ns(prompt_tokens=10, completion_tokens=5))
        client = _FakeOpenAIClientNonStream(response)
        provider = GenericStreamProvider()

        results = []
        async for tok in provider.stream(client, messages=[], model="some-model"):
            results.append(tok)

        assert len(results) == 2
        assert results[0].delta == "Full response"
        assert results[1].done
        assert results[1].metadata["usage"]["prompt_tokens"] == 10


# ---------------------------------------------------------------------------
# stream_llm_response integration
# ---------------------------------------------------------------------------

class TestStreamLLMResponse:
    @pytest.mark.asyncio
    async def test_uses_detected_provider(self):
        """stream_llm_response should auto-detect the provider and stream."""
        chunks = [
            _make_openai_chunk(content="ok"),
            _make_openai_chunk(finish_reason="stop"),
        ]
        client = _FakeOpenAIClient(chunks)

        results = []
        async for tok in stream_llm_response(client, messages=[], model="gpt-4"):
            results.append(tok)

        assert results[0].delta == "ok"
        assert results[-1].done

    @pytest.mark.asyncio
    async def test_explicit_provider(self):
        """Caller can supply a provider explicitly."""
        chunks = [
            _make_openai_chunk(content="hi"),
            _make_openai_chunk(finish_reason="stop"),
        ]
        client = _FakeOpenAIClient(chunks)

        results = []
        async for tok in stream_llm_response(
            client, messages=[], model="x", provider=OpenAIStreamProvider()
        ):
            results.append(tok)

        assert results[0].delta == "hi"

    @pytest.mark.asyncio
    async def test_error_handling(self):
        """Errors are caught and yielded as a done chunk with error metadata."""

        class _FailClient:
            def __init__(self):
                self.chat = _ns(completions=_ns(create=self._create))
            async def _create(self, **kwargs):
                raise RuntimeError("boom")

        results = []
        async for tok in stream_llm_response(_FailClient(), messages=[], model="gpt-4"):
            results.append(tok)

        assert len(results) == 1
        assert results[0].done
        assert "boom" in results[0].metadata["error"]


# ---------------------------------------------------------------------------
# Edge-case tests — Anthropic tool_use, unknown client, empty, mid-stream err
# ---------------------------------------------------------------------------

class TestAnthropicStreamingToolUseEdge:
    """Anthropic streaming with multiple tool_use content blocks."""

    @pytest.mark.asyncio
    async def test_multiple_tool_use_blocks(self):
        """Handles multiple tool_use blocks interleaved with text."""
        events = [
            _ns(type="content_block_start", content_block=_ns(type="text")),
            _ns(type="content_block_delta", delta=_ns(type="text_delta", text="Let me search.")),
            _ns(type="content_block_stop"),
            _ns(type="content_block_start", content_block=_ns(type="tool_use", id="tc_1", name="search")),
            _ns(type="content_block_delta", delta=_ns(type="input_json_delta", partial_json='{"q":"hello"}')),
            _ns(type="content_block_stop"),
            _ns(type="content_block_start", content_block=_ns(type="tool_use", id="tc_2", name="fetch")),
            _ns(type="content_block_delta", delta=_ns(type="input_json_delta", partial_json='{"url":"http"}')),
            _ns(type="content_block_stop"),
            _ns(type="message_stop"),
        ]

        class _Client:
            def __init__(self):
                self.messages = _ns(create=self._create)
            async def _create(self, **kwargs):
                return _AsyncIter(events)

        provider = AnthropicStreamProvider()
        results = []
        async for tok in provider.stream(_Client(), messages=[], model="claude-3-opus"):
            results.append(tok)

        final = results[-1]
        assert final.done
        assert len(final.metadata["tool_calls"]) == 2
        assert final.metadata["tool_calls"][0]["function"]["name"] == "search"
        assert final.metadata["tool_calls"][1]["function"]["name"] == "fetch"
        assert final.full_text == "Let me search."


class TestProviderDetectionEdge:
    """Provider detection with unknown/edge client types."""

    def test_unknown_client_type_falls_back_to_generic(self):
        """A completely unknown client object with unknown model falls back."""
        provider = detect_provider(42, model="llama-3-70b")
        assert isinstance(provider, GenericStreamProvider)

    def test_none_model_falls_back_to_generic(self):
        """An empty model string with unknown client falls back."""
        provider = detect_provider(object(), model="")
        assert isinstance(provider, GenericStreamProvider)

    def test_model_prefix_o3(self):
        """o3 prefix is detected as OpenAI."""
        provider = detect_provider(object(), model="o3-mini")
        assert isinstance(provider, OpenAIStreamProvider)


class TestStreamingEmptyResponse:
    """Streaming with an empty response from the provider."""

    @pytest.mark.asyncio
    async def test_openai_empty_choices(self):
        """OpenAI stream where chunks have no content yields a done chunk."""
        chunks = [
            _make_openai_chunk(finish_reason="stop"),
        ]
        client = _FakeOpenAIClient(chunks)
        provider = OpenAIStreamProvider()

        results = []
        async for tok in provider.stream(client, messages=[], model="gpt-4"):
            results.append(tok)

        # Should still yield a final done chunk
        assert results[-1].done
        assert results[-1].full_text == ""

    @pytest.mark.asyncio
    async def test_anthropic_empty_message(self):
        """Anthropic stream with no content blocks → done chunk with empty text."""
        events = [
            _ns(type="message_stop"),
        ]

        class _Client:
            def __init__(self):
                self.messages = _ns(create=self._create)
            async def _create(self, **kwargs):
                return _AsyncIter(events)

        provider = AnthropicStreamProvider()
        results = []
        async for tok in provider.stream(_Client(), messages=[], model="claude-3-opus"):
            results.append(tok)

        assert results[-1].done
        assert results[-1].full_text == ""


class TestStreamingErrorMidStream:
    """Connection drop / error mid-stream."""

    @pytest.mark.asyncio
    async def test_error_during_openai_stream(self):
        """An exception raised mid-stream is caught by stream_llm_response."""

        class _FailMidStreamClient:
            def __init__(self):
                self.chat = _ns(completions=_ns(create=self._create))

            async def _create(self, **kwargs):
                async def _gen():
                    yield _make_openai_chunk(content="partial")
                    raise ConnectionError("connection lost")
                return _gen()

        results = []
        async for tok in stream_llm_response(_FailMidStreamClient(), messages=[], model="gpt-4"):
            results.append(tok)

        # Should get the partial chunk then an error-done chunk
        assert any("connection lost" in tok.metadata.get("error", "") for tok in results if tok.done)

    @pytest.mark.asyncio
    async def test_error_during_anthropic_stream(self):
        """An exception mid-stream from Anthropic is caught."""

        class _FailMidAnthropicClient:
            def __init__(self):
                self.messages = _ns(create=self._create)
            async def _create(self, **kwargs):
                async def _gen():
                    yield _ns(type="content_block_start", content_block=_ns(type="text"))
                    yield _ns(type="content_block_delta", delta=_ns(type="text_delta", text="partial"))
                    raise ConnectionError("anthropic connection lost")
                return _gen()

        results = []
        async for tok in stream_llm_response(
            _FailMidAnthropicClient(), messages=[], model="claude-3-opus"
        ):
            results.append(tok)

        assert any("anthropic connection lost" in tok.metadata.get("error", "") for tok in results if tok.done)
