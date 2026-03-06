"""Tests for forge.runtime.observability"""

import json
import os
import tempfile
import pytest
from forge.runtime.observability import (
    EventLog, Event, EventType, TraceContext, CostTracker,
    PersistentEventStore, OTLPExporter, get_metrics_summary,
)


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


class TestPersistentEventStore:
    @pytest.fixture
    def store(self, tmp_path):
        s = PersistentEventStore(db_path=tmp_path / "test_events.db")
        yield s
        s.close()

    def test_persist_and_query(self, store):
        event = Event(event_type=EventType.AGENT_START, agent_name="A", trace_id="t1")
        store.persist(event)
        rows = store.query_events(trace_id="t1")
        assert len(rows) == 1
        assert rows[0]["agent"] == "A"
        assert rows[0]["event_type"] == "agent_start"

    def test_query_by_agent(self, store):
        store.persist(Event(event_type=EventType.AGENT_START, agent_name="A"))
        store.persist(Event(event_type=EventType.AGENT_START, agent_name="B"))
        rows = store.query_events(agent_name="A")
        assert len(rows) == 1

    def test_query_by_type(self, store):
        store.persist(Event(event_type=EventType.AGENT_START, agent_name="A"))
        store.persist(Event(event_type=EventType.LLM_CALL, agent_name="A"))
        rows = store.query_events(event_type="llm_call")
        assert len(rows) == 1

    def test_count_by_type(self, store):
        store.persist(Event(event_type=EventType.AGENT_START))
        store.persist(Event(event_type=EventType.AGENT_START))
        store.persist(Event(event_type=EventType.LLM_CALL))
        counts = store.count_by_type()
        assert counts["agent_start"] == 2
        assert counts["llm_call"] == 1

    def test_total_cost(self, store):
        e = Event(event_type=EventType.LLM_RESPONSE, cost_usd=0.05)
        store.persist(e)
        assert store.total_cost() == pytest.approx(0.05)

    def test_query_limit(self, store):
        for i in range(10):
            store.persist(Event(event_type=EventType.AGENT_START, agent_name=f"A{i}"))
        rows = store.query_events(limit=3)
        assert len(rows) == 3


class TestEventLogWithPersistence:
    def test_emit_persists(self, tmp_path):
        store = PersistentEventStore(db_path=tmp_path / "test.db")
        log = EventLog(persistent_store=store)
        log.emit(Event(event_type=EventType.AGENT_START, agent_name="X", trace_id="t1"))
        rows = store.query_events(trace_id="t1")
        assert len(rows) == 1
        store.close()

    def test_query_events_delegates(self, tmp_path):
        store = PersistentEventStore(db_path=tmp_path / "test.db")
        log = EventLog(persistent_store=store)
        log.emit(Event(event_type=EventType.AGENT_START, agent_name="X"))
        result = log.query_events(agent_name="X")
        assert len(result) == 1
        store.close()

    def test_query_events_no_store_falls_back(self):
        log = EventLog()
        log.emit(Event(event_type=EventType.AGENT_START, agent_name="X", trace_id="t1"))
        result = log.query_events(trace_id="t1")
        assert len(result) == 1


class TestOTLPExporter:
    def test_disabled_without_env(self):
        exporter = OTLPExporter()
        assert not exporter.enabled

    def test_export_noop_when_disabled(self):
        exporter = OTLPExporter()
        event = Event(event_type=EventType.AGENT_START)
        exporter.export_event(event)  # should not raise


class TestGetMetricsSummary:
    def test_metrics_summary_basic(self):
        log = EventLog()
        log.emit(Event(event_type=EventType.AGENT_START, agent_name="A"))
        log.emit(Event(event_type=EventType.LLM_CALL, agent_name="A"))
        log.emit(Event(event_type=EventType.AGENT_START, agent_name="B"))
        summary = get_metrics_summary(log)
        assert summary["total_events"] == 3
        assert summary["agent_activity"]["A"] == 2
        assert summary["agent_activity"]["B"] == 1

    def test_metrics_summary_with_store(self, tmp_path):
        store = PersistentEventStore(db_path=tmp_path / "m.db")
        log = EventLog(persistent_store=store)
        log.emit(Event(event_type=EventType.AGENT_START, agent_name="X"))
        summary = get_metrics_summary(log, persistent_store=store)
        assert "persisted_event_counts" in summary
        assert summary["persisted_event_counts"]["agent_start"] == 1
        store.close()
