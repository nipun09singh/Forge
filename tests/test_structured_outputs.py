"""Tests for forge.runtime.structured_outputs."""

import json

import pytest
from forge.runtime.structured_outputs import (
    TaskStatus, AgentResponse, ProjectCompletion,
    parse_agent_response, parse_completion_signal,
)


class TestTaskStatus:
    """Tests for TaskStatus enum."""

    def test_values(self):
        assert TaskStatus.IN_PROGRESS == "in_progress"
        assert TaskStatus.COMPLETED == "completed"
        assert TaskStatus.FAILED == "failed"
        assert TaskStatus.BLOCKED == "blocked"

    def test_string_comparison(self):
        assert TaskStatus.COMPLETED == "completed"
        assert TaskStatus("in_progress") == TaskStatus.IN_PROGRESS


class TestAgentResponse:
    """Tests for AgentResponse model."""

    def test_defaults(self):
        r = AgentResponse()
        assert r.status == TaskStatus.IN_PROGRESS
        assert r.content == ""
        assert r.completion_score == 0.0

    def test_from_dict(self):
        r = AgentResponse.model_validate({
            "status": "completed",
            "content": "Done!",
            "completion_score": 1.0,
        })
        assert r.status == TaskStatus.COMPLETED
        assert r.content == "Done!"

    def test_completion_score_bounds(self):
        """Score must be between 0 and 1."""
        with pytest.raises(Exception):
            AgentResponse(completion_score=1.5)
        with pytest.raises(Exception):
            AgentResponse(completion_score=-0.1)

    def test_valid_score_edges(self):
        r0 = AgentResponse(completion_score=0.0)
        r1 = AgentResponse(completion_score=1.0)
        assert r0.completion_score == 0.0
        assert r1.completion_score == 1.0


class TestProjectCompletion:
    """Tests for ProjectCompletion model."""

    def test_defaults(self):
        pc = ProjectCompletion()
        assert pc.status == "DONE"
        assert pc.summary == ""

    def test_from_json(self):
        data = {"status": "DONE", "summary": "Built an API", "files_created": 5}
        pc = ProjectCompletion.model_validate_json(json.dumps(data))
        assert pc.summary == "Built an API"
        assert pc.files_created == 5


class TestParseAgentResponse:
    """Tests for parse_agent_response function."""

    def test_valid_json(self):
        text = '{"status": "completed", "content": "All done", "completion_score": 0.9}'
        r = parse_agent_response(text)
        assert r is not None
        assert r.status == TaskStatus.COMPLETED
        assert r.content == "All done"

    def test_invalid_json(self):
        assert parse_agent_response("not json at all") is None

    def test_empty_string(self):
        assert parse_agent_response("") is None

    def test_none_input(self):
        assert parse_agent_response(None) is None

    def test_whitespace_only(self):
        assert parse_agent_response("   ") is None

    def test_json_with_extra_whitespace(self):
        text = '  {"status": "in_progress", "content": "working"} '
        r = parse_agent_response(text)
        assert r is not None
        assert r.status == TaskStatus.IN_PROGRESS

    def test_non_dict_json(self):
        """JSON arrays/strings should return None."""
        assert parse_agent_response("[1,2,3]") is None
        assert parse_agent_response('"just a string"') is None

    def test_partial_fields(self):
        """Response with only some fields should work (rest default)."""
        r = parse_agent_response('{"content": "hello"}')
        assert r is not None
        assert r.content == "hello"
        assert r.status == TaskStatus.IN_PROGRESS  # default


class TestParseCompletionSignal:
    """Tests for parse_completion_signal function."""

    # ── Structured JSON detection ──
    def test_json_done(self):
        text = '{"status": "DONE", "summary": "Built it", "files_created": 5}'
        c = parse_completion_signal(text)
        assert c is not None
        assert c.status == "DONE"
        assert c.summary == "Built it"
        assert c.files_created == 5

    def test_json_completed(self):
        text = '{"status": "completed", "summary": "All good"}'
        c = parse_completion_signal(text)
        assert c is not None

    def test_json_not_done(self):
        text = '{"status": "in_progress"}'
        c = parse_completion_signal(text)
        assert c is None

    # ── String fallback detection ──
    def test_bare_done(self):
        c = parse_completion_signal("DONE")
        assert c is not None
        assert c.status == "DONE"
        assert isinstance(c.summary, str)

    def test_done_period(self):
        c = parse_completion_signal("DONE.")
        assert c is not None
        assert c.status == "DONE"

    def test_done_with_newline(self):
        c = parse_completion_signal("DONE\nSome extra text")
        assert c is not None
        assert c.status == "DONE"
        assert "DONE" in c.summary

    def test_trailing_done(self):
        c = parse_completion_signal("All work complete\nDONE")
        assert c is not None
        assert c.status == "DONE"

    def test_project_is_complete(self):
        c = parse_completion_signal("The PROJECT IS COMPLETE and ready.")
        assert c is not None
        assert c.status == "DONE"
        assert len(c.summary) > 0

    def test_done_in_middle(self):
        c = parse_completion_signal("First line\nDONE\nLast line")
        assert c is not None
        assert c.status == "DONE"

    def test_case_insensitive(self):
        for variant in ["done", "Done", "DONE", "dOnE"]:
            c = parse_completion_signal(variant)
            assert c is not None, f"Failed for variant: {variant}"
            assert c.status == "DONE"

    # ── Negative cases ──
    def test_empty(self):
        assert parse_completion_signal("") is None

    def test_none(self):
        assert parse_completion_signal(None) is None

    def test_not_done(self):
        assert parse_completion_signal("I'm still working on it") is None

    def test_done_as_substring(self):
        """'DONE' embedded in other words should NOT match."""
        result = parse_completion_signal("I ABANDONED this")
        assert result is None

    def test_whitespace(self):
        assert parse_completion_signal("  DONE  ") is not None
