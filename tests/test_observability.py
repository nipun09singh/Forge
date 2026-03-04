"""Tests for forge.runtime.observability"""

import json
import pytest
from forge.runtime.observability import EventLog, Event, EventType, TraceContext, CostTracker


class TestEventLog:
    def test_emit_event(self, event_log):
        event_log.emit(Event(event_type=EventType.AGENT_START, agent_name="test"))
        assert len(event_log.events) == 1

    def test_emit_llm_call(self, event_log):
        event_log.emit_llm_call("Agent1", "gpt-4", 5, 2, trace_id="t1")
        assert len(event_log.events) == 1
        assert event_log.events[0].event_type == EventType.LLM_CALL

    def test_emit_llm_response_tracks_cost(self, event_log):
        event_log.emit_llm_response("Agent1", "gpt-4", 100, 50, False, 500.0, trace_id="t1")
        assert event_log.cost_tracker.total_tokens == 150
        assert event_log.cost_tracker.total_cost_usd > 0

    def test_filter_by_trace(self, event_log):
        event_log.emit(Event(event_type=EventType.AGENT_START, trace_id="t1"))
        event_log.emit(Event(event_type=EventType.AGENT_START, trace_id="t2"))
        assert len(event_log.filter(trace_id="t1")) == 1

    def test_filter_by_agent(self, event_log):
        event_log.emit(Event(event_type=EventType.AGENT_START, agent_name="A"))
        event_log.emit(Event(event_type=EventType.AGENT_START, agent_name="B"))
        assert len(event_log.filter(agent_name="A")) == 1

    def test_get_errors(self, event_log):
        event_log.emit(Event(event_type=EventType.AGENT_ERROR, level="error"))
        event_log.emit(Event(event_type=EventType.AGENT_START, level="info"))
        assert len(event_log.get_errors()) == 1

    def test_export_json(self, event_log):
        event_log.emit(Event(event_type=EventType.AGENT_START))
        exported = event_log.export_json()
        data = json.loads(exported)
        assert len(data) == 1

    def test_summary(self, event_log):
        event_log.emit_llm_call("A", "gpt-4", 1, 0)
        event_log.emit_llm_response("A", "gpt-4", 10, 5, False, 100.0)
        summary = event_log.get_summary()
        assert summary["total_events"] == 2
        assert "costs" in summary


class TestTraceContext:
    def test_trace_id_generation(self):
        ctx = TraceContext()
        assert ctx.trace_id.startswith("trace-")

    def test_span_management(self):
        ctx = TraceContext()
        span = ctx.new_span()
        assert span.startswith("span-")
        assert ctx.current_span() == span
        ended = ctx.end_span()
        assert ended == span

    def test_child_context(self):
        parent = TraceContext()
        child = parent.child()
        assert child.trace_id == parent.trace_id


class TestCostTracker:
    def test_record_cost(self):
        tracker = CostTracker()
        cost = tracker.record("gpt-4", 1000, 500, "Agent1")
        assert cost > 0
        assert tracker.total_tokens == 1500
        assert tracker._call_count == 1

    def test_per_agent_tracking(self):
        tracker = CostTracker()
        tracker.record("gpt-4", 100, 50, "A")
        tracker.record("gpt-4", 200, 100, "B")
        summary = tracker.get_summary()
        assert "A" in summary["per_agent"]
        assert "B" in summary["per_agent"]
