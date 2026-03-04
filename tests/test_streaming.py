"""Tests for forge.runtime.streaming"""

import pytest
from forge.runtime.streaming import StreamingResponse, TokenChunk


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
