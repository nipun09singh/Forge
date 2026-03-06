"""Tests for forge.runtime.build_loop."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from forge.runtime.build_loop import BuildLoop, BuildResult


class TestBuildLoopInit:
    """Tests for BuildLoop initialization."""

    def test_defaults(self):
        bl = BuildLoop()
        assert bl.max_attempts >= 1

    def test_custom_params(self):
        bl = BuildLoop(max_attempts=10, build_command="make", test_command="make test")
        assert bl.max_attempts == 10


class TestBuildResult:
    """Tests for BuildResult dataclass."""

    def test_creation(self):
        r = BuildResult(success=True, final_output="All tests passed", attempts=2)
        assert r.success is True
        assert r.attempts == 2

    def test_failure(self):
        r = BuildResult(success=False, final_output="Build failed", attempts=5)
        assert r.success is False


class TestCodeExtraction:
    """Tests for _extract_code_blocks."""

    def test_extract_file_block(self):
        bl = BuildLoop()
        text = "Here's the code:\n```main.py\nprint('hello')\n```\nDone."
        blocks = bl._extract_code_blocks(text)
        assert len(blocks) >= 1
        assert "main.py" in blocks

    def test_extract_multiple_blocks(self):
        bl = BuildLoop()
        text = "```app.py\nx = 1\n```\n\n```utils.py\ny = 2\n```"
        blocks = bl._extract_code_blocks(text)
        assert len(blocks) == 2

    def test_extract_no_blocks(self):
        bl = BuildLoop()
        blocks = bl._extract_code_blocks("Just plain text, no code here")
        assert isinstance(blocks, dict)
        assert len(blocks) == 0

    def test_skips_pure_language_blocks(self):
        bl = BuildLoop()
        text = "```python\nprint('hello')\n```"
        blocks = bl._extract_code_blocks(text)
        assert len(blocks) == 0
