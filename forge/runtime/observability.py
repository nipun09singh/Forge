"""Observability — structured event logging, tracing, and cost tracking."""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import threading
import time
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

try:
    from opentelemetry import trace as otel_trace
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
    _HAS_OTEL = True
except ImportError:
    _HAS_OTEL = False


class EventType(str, Enum):
    """Types of observable events."""
    LLM_CALL = "llm_call"
    LLM_RESPONSE = "llm_response"
    TOOL_USE = "tool_use"
    TOOL_RESULT = "tool_result"
    AGENT_START = "agent_start"
    AGENT_COMPLETE = "agent_complete"
    AGENT_ERROR = "agent_error"
    TEAM_DISPATCH = "team_dispatch"
    PLAN_CREATED = "plan_created"
    STEP_EXECUTED = "step_executed"
    QUALITY_CHECK = "quality_check"
    REFLECTION = "reflection"
    HUMAN_APPROVAL = "human_approval"
    MEMORY_STORE = "memory_store"
    COST_TRACKED = "cost_tracked"


@dataclass
class Event:
    """A single observable event."""
    event_type: EventType
    agent_name: str = ""
    trace_id: str = ""
    span_id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    data: dict[str, Any] = field(default_factory=dict)
    tokens: int = 0
    cost_usd: float = 0.0
    duration_ms: float = 0.0
    parent_span_id: str = ""
    level: str = "info"  # info, warning, error

    def to_dict(self) -> dict[str, Any]:
        """Convert the event to a dictionary."""
        d = asdict(self)
        d["event_type"] = self.event_type.value
        return d

    def to_json(self) -> str:
        """Serialize the event to a JSON string."""
        return json.dumps(self.to_dict(), default=str)


class TraceContext:
    """
    Manages trace IDs for correlating events across agents, teams, and plans.
    
    A single user request gets one trace_id. Every sub-operation gets a span_id.
    This allows tracing a request through: Agency → Planner → Team → Agent → Tools.

    All span stack operations are protected by a threading.Lock for safe use
    in async and multi-threaded environments.
    """

    def __init__(self, trace_id: str | None = None):
        self.trace_id = trace_id or f"trace-{uuid.uuid4().hex[:12]}"
        self._span_stack: list[str] = []
        self._lock = threading.Lock()

    def new_span(self) -> str:
        """Create a new span within this trace."""
        span_id = f"span-{uuid.uuid4().hex[:8]}"
        with self._lock:
            self._span_stack.append(span_id)
        return span_id

    def current_span(self) -> str:
        """Get the current span ID."""
        with self._lock:
            return self._span_stack[-1] if self._span_stack else ""

    def end_span(self) -> str | None:
        """End the current span."""
        with self._lock:
            return self._span_stack.pop() if self._span_stack else None

    def child(self) -> TraceContext:
        """Create a child trace context sharing the same trace_id."""
        with self._lock:
            child_ctx = TraceContext(trace_id=self.trace_id)
            child_ctx._span_stack = list(self._span_stack)
        return child_ctx


# Approximate cost per 1K tokens (configurable)
MODEL_COSTS = {
    # OpenAI models (per 1K tokens)
    "gpt-4": {"input": 0.03, "output": 0.06},
    "gpt-4-turbo": {"input": 0.01, "output": 0.03},
    "gpt-4o": {"input": 0.005, "output": 0.015},
    "gpt-4o-mini": {"input": 0.00015, "output": 0.0006},
    "gpt-3.5-turbo": {"input": 0.0005, "output": 0.0015},
    "o1": {"input": 0.015, "output": 0.06},
    "o1-mini": {"input": 0.003, "output": 0.012},
    "o3-mini": {"input": 0.0011, "output": 0.0044},
    # Anthropic Claude models (per 1K tokens)
    "claude-3-opus": {"input": 0.015, "output": 0.075},
    "claude-3-sonnet": {"input": 0.003, "output": 0.015},
    "claude-3-haiku": {"input": 0.00025, "output": 0.00125},
    "claude-3.5-sonnet": {"input": 0.003, "output": 0.015},
    "claude-3.5-haiku": {"input": 0.0008, "output": 0.004},
}


class CostTracker:
    """Tracks token usage and estimated costs across all LLM calls."""

    def __init__(self) -> None:
        self.total_tokens: int = 0
        self.total_prompt_tokens: int = 0
        self.total_completion_tokens: int = 0
        self.total_cost_usd: float = 0.0
        self._per_agent: dict[str, dict[str, float]] = {}
        self._call_count: int = 0

    def __repr__(self) -> str:
        return f"CostTracker(calls={self._call_count}, tokens={self.total_tokens}, cost=${self.total_cost_usd:.4f})"

    def record(
        self,
        model: str,
        prompt_tokens: int,
        completion_tokens: int,
        agent_name: str = "",
    ) -> float:
        """Record a single LLM call. Returns estimated cost in USD."""
        total = prompt_tokens + completion_tokens
        self.total_tokens += total
        self.total_prompt_tokens += prompt_tokens
        self.total_completion_tokens += completion_tokens
        self._call_count += 1

        # Estimate cost
        costs = MODEL_COSTS.get(model, MODEL_COSTS.get("gpt-4", {"input": 0.03, "output": 0.06}))
        cost = (prompt_tokens / 1000 * costs["input"]) + (completion_tokens / 1000 * costs["output"])
        self.total_cost_usd += cost

        # Per-agent tracking
        if agent_name:
            if agent_name not in self._per_agent:
                self._per_agent[agent_name] = {"tokens": 0, "cost_usd": 0.0, "calls": 0}
            self._per_agent[agent_name]["tokens"] += total
            self._per_agent[agent_name]["cost_usd"] += cost
            self._per_agent[agent_name]["calls"] += 1

        return cost

    def get_summary(self) -> dict[str, Any]:
        """Get a cost summary."""
        return {
            "total_tokens": self.total_tokens,
            "total_prompt_tokens": self.total_prompt_tokens,
            "total_completion_tokens": self.total_completion_tokens,
            "total_cost_usd": round(self.total_cost_usd, 4),
            "total_llm_calls": self._call_count,
            "per_agent": dict(self._per_agent),
        }


class PersistentEventStore:
    """SQLite-backed event persistence layer.

    Writes every event to a local SQLite database so that data survives
    process restarts.  The database file is created automatically.
    """

    _DDL = """
        CREATE TABLE IF NOT EXISTS events (
            id TEXT PRIMARY KEY,
            timestamp TEXT NOT NULL,
            event_type TEXT NOT NULL,
            agent TEXT NOT NULL DEFAULT '',
            data JSON,
            trace_id TEXT NOT NULL DEFAULT '',
            span_id TEXT NOT NULL DEFAULT '',
            parent_span_id TEXT NOT NULL DEFAULT '',
            tokens INTEGER NOT NULL DEFAULT 0,
            cost_usd REAL NOT NULL DEFAULT 0.0,
            duration_ms REAL NOT NULL DEFAULT 0.0,
            level TEXT NOT NULL DEFAULT 'info'
        );
        CREATE INDEX IF NOT EXISTS idx_events_trace ON events(trace_id);
        CREATE INDEX IF NOT EXISTS idx_events_type  ON events(event_type);
        CREATE INDEX IF NOT EXISTS idx_events_agent ON events(agent);
        CREATE INDEX IF NOT EXISTS idx_events_ts    ON events(timestamp);
    """

    def __init__(self, db_path: str | Path | None = None) -> None:
        if db_path is None:
            db_path = os.environ.get("FORGE_EVENTS_DB", str(Path.home() / ".forge" / "events.db"))
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn: sqlite3.Connection | None = None
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA journal_mode=WAL")
        return self._conn

    def _init_db(self) -> None:
        with self._lock:
            conn = self._get_conn()
            conn.executescript(self._DDL)
            conn.commit()

    def persist(self, event: Event) -> None:
        """Write a single event to SQLite."""
        with self._lock:
            conn = self._get_conn()
            if conn is None:
                logger.warning("PersistentEventStore: database connection not initialized")
                return
            conn.execute(
                "INSERT OR REPLACE INTO events "
                "(id, timestamp, event_type, agent, data, trace_id, span_id, "
                "parent_span_id, tokens, cost_usd, duration_ms, level) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    event.span_id,
                    event.timestamp,
                    event.event_type.value,
                    event.agent_name,
                    json.dumps(event.data, default=str),
                    event.trace_id,
                    event.span_id,
                    event.parent_span_id,
                    event.tokens,
                    event.cost_usd,
                    event.duration_ms,
                    event.level,
                ),
            )
            conn.commit()

    def query_events(
        self,
        *,
        trace_id: str | None = None,
        agent_name: str | None = None,
        event_type: str | None = None,
        level: str | None = None,
        since: str | None = None,
        until: str | None = None,
        limit: int = 500,
    ) -> list[dict[str, Any]]:
        """Query persisted events with optional filters.

        All filter parameters are optional.  ``since`` / ``until`` accept
        ISO-8601 timestamp strings.
        """
        clauses: list[str] = []
        params: list[Any] = []
        if trace_id:
            clauses.append("trace_id = ?")
            params.append(trace_id)
        if agent_name:
            clauses.append("agent = ?")
            params.append(agent_name)
        if event_type:
            clauses.append("event_type = ?")
            params.append(event_type)
        if level:
            clauses.append("level = ?")
            params.append(level)
        if since:
            clauses.append("timestamp >= ?")
            params.append(since)
        if until:
            clauses.append("timestamp <= ?")
            params.append(until)
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        sql = f"SELECT * FROM events{where} ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)
        with self._lock:
            conn = self._get_conn()
            rows = conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]

    def count_by_type(self) -> dict[str, int]:
        """Return event counts grouped by event_type."""
        with self._lock:
            conn = self._get_conn()
            rows = conn.execute(
                "SELECT event_type, COUNT(*) as cnt FROM events GROUP BY event_type"
            ).fetchall()
        return {r["event_type"]: r["cnt"] for r in rows}

    def total_cost(self) -> float:
        """Return total tracked cost across all persisted events."""
        with self._lock:
            conn = self._get_conn()
            row = conn.execute("SELECT COALESCE(SUM(cost_usd), 0) AS total FROM events").fetchone()
        return float(row["total"])

    def close(self) -> None:
        with self._lock:
            if self._conn:
                self._conn.close()
                self._conn = None


class OTLPExporter:
    """Optional OpenTelemetry exporter.

    Activated only when:
      1. The ``opentelemetry`` packages are installed, **and**
      2. ``OTEL_EXPORTER_OTLP_ENDPOINT`` is set in the environment.

    If either condition is not met the exporter silently no-ops.
    """

    def __init__(self, endpoint: str | None = None) -> None:
        self._enabled = False
        self._tracer: Any = None
        endpoint = endpoint or os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT")
        if not endpoint or not _HAS_OTEL:
            return
        try:
            provider = TracerProvider()
            exporter = OTLPSpanExporter(endpoint=endpoint, insecure=True)
            provider.add_span_processor(BatchSpanProcessor(exporter))
            self._tracer = provider.get_tracer("forge.observability")
            self._enabled = True
            logger.info("OTLP exporter enabled → %s", endpoint)
        except Exception:
            logger.warning("Failed to initialise OTLP exporter", exc_info=True)

    @property
    def enabled(self) -> bool:
        return self._enabled

    def export_event(self, event: Event) -> None:
        """Map a Forge event to an OpenTelemetry span and export it."""
        if not self._enabled or self._tracer is None:
            return
        try:
            with self._tracer.start_as_current_span(
                name=event.event_type.value,
                attributes={
                    "forge.agent": event.agent_name,
                    "forge.trace_id": event.trace_id,
                    "forge.span_id": event.span_id,
                    "forge.level": event.level,
                    "forge.tokens": event.tokens,
                    "forge.cost_usd": event.cost_usd,
                    "forge.duration_ms": event.duration_ms,
                },
            ):
                pass  # span auto-ended by context manager
        except Exception:
            logger.debug("OTLP export failed for event %s", event.span_id, exc_info=True)


def get_metrics_summary(
    event_log: "EventLog",
    persistent_store: PersistentEventStore | None = None,
) -> dict[str, Any]:
    """Build an aggregate metrics summary suitable for dashboards / API.

    Combines in-memory hot data from *event_log* with optional historical
    data from *persistent_store*.
    """
    summary = event_log.get_summary()

    agent_activity: dict[str, int] = {}
    for e in event_log._events:
        if e.agent_name:
            agent_activity[e.agent_name] = agent_activity.get(e.agent_name, 0) + 1

    summary["agent_activity"] = agent_activity

    if persistent_store is not None:
        summary["persisted_event_counts"] = persistent_store.count_by_type()
        summary["persisted_total_cost_usd"] = round(persistent_store.total_cost(), 6)

    return summary


class EventLog:
    """
    Append-only structured event log.
    
    Stores all observable events with filtering, export, and analysis capabilities.
    This is the core observability primitive — everything flows through here.

    Optionally backs events to SQLite (``persistent_store``) and/or exports
    them via OTLP (``otlp_exporter``).  Both are disabled by default so that
    existing call-sites remain zero-config.
    """

    def __init__(
        self,
        cost_tracker: CostTracker | None = None,
        max_events: int = 10_000,
        max_age_hours: float = 24.0,
        persistent_store: PersistentEventStore | None = None,
        otlp_exporter: OTLPExporter | None = None,
    ) -> None:
        self._events: list[Event] = []
        self._max_events = max_events
        self.max_age_hours = max_age_hours
        self.cost_tracker = cost_tracker or CostTracker()
        self.persistent_store = persistent_store
        self.otlp_exporter = otlp_exporter

    def __repr__(self) -> str:
        return f"EventLog(events={len(self._events)}, cost=${self.cost_tracker.total_cost_usd:.4f})"

    def emit(self, event: Event) -> None:
        """Record an event."""
        self._events.append(event)
        # Periodic cleanup (every 1000 events)
        if len(self._events) % 1000 == 0:
            self.cleanup_old_events()
        # Prevent unbounded memory growth
        if len(self._events) > self._max_events:
            self._events = self._events[-self._max_events:]
        # Log to Python logger for real-time visibility
        log_msg = f"[{event.event_type.value}] {event.agent_name}: {json.dumps(event.data, default=str)[:200]}"
        if event.level == "error":
            logger.error(log_msg)
        elif event.level == "warning":
            logger.warning(log_msg)
        else:
            logger.debug(log_msg)
        # Persist to SQLite if configured
        if self.persistent_store is not None:
            try:
                self.persistent_store.persist(event)
            except Exception:
                logger.debug("Failed to persist event", exc_info=True)
        # Export via OTLP if configured
        if self.otlp_exporter is not None:
            self.otlp_exporter.export_event(event)

    def cleanup_old_events(self) -> int:
        """Remove events older than max_age_hours. Returns count of removed events."""
        if not self.max_age_hours or self.max_age_hours <= 0:
            return 0
        from datetime import timedelta
        cutoff_dt = datetime.now(timezone.utc) - timedelta(hours=self.max_age_hours)
        cutoff_str = cutoff_dt.isoformat()
        before = len(self._events)
        self._events = [e for e in self._events if e.timestamp >= cutoff_str]
        removed = before - len(self._events)
        if removed > 0:
            logger.debug(f"Cleaned up {removed} old events (older than {self.max_age_hours}h)")
        return removed

    def emit_llm_call(
        self,
        agent_name: str,
        model: str,
        messages_count: int,
        tools_count: int,
        trace_id: str = "",
        span_id: str = "",
    ) -> Event:
        """Convenience: emit an LLM call event."""
        event = Event(
            event_type=EventType.LLM_CALL,
            agent_name=agent_name,
            trace_id=trace_id,
            span_id=span_id,
            data={"model": model, "messages": messages_count, "tools": tools_count},
        )
        self.emit(event)
        return event

    def emit_llm_response(
        self,
        agent_name: str,
        model: str,
        prompt_tokens: int,
        completion_tokens: int,
        has_tool_calls: bool,
        duration_ms: float,
        trace_id: str = "",
        span_id: str = "",
    ) -> Event:
        """Convenience: emit an LLM response event with cost tracking."""
        cost = self.cost_tracker.record(model, prompt_tokens, completion_tokens, agent_name)
        event = Event(
            event_type=EventType.LLM_RESPONSE,
            agent_name=agent_name,
            trace_id=trace_id,
            span_id=span_id,
            tokens=prompt_tokens + completion_tokens,
            cost_usd=cost,
            duration_ms=duration_ms,
            data={
                "model": model,
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "has_tool_calls": has_tool_calls,
            },
        )
        self.emit(event)
        return event

    def emit_tool_use(
        self,
        agent_name: str,
        tool_name: str,
        args: dict,
        trace_id: str = "",
    ) -> Event:
        """Convenience: emit a tool use event."""
        event = Event(
            event_type=EventType.TOOL_USE,
            agent_name=agent_name,
            trace_id=trace_id,
            data={"tool": tool_name, "args": {k: str(v)[:100] for k, v in args.items()}},
        )
        self.emit(event)
        return event

    def emit_tool_result(
        self,
        agent_name: str,
        tool_name: str,
        success: bool,
        output_preview: str,
        duration_ms: float,
        trace_id: str = "",
    ) -> Event:
        """Convenience: emit a tool result event."""
        event = Event(
            event_type=EventType.TOOL_RESULT,
            agent_name=agent_name,
            trace_id=trace_id,
            duration_ms=duration_ms,
            level="info" if success else "warning",
            data={"tool": tool_name, "success": success, "output_preview": output_preview[:200]},
        )
        self.emit(event)
        return event

    # ─── Querying ─────────────────────────────────────────

    def filter(
        self,
        trace_id: str | None = None,
        agent_name: str | None = None,
        event_type: EventType | None = None,
        level: str | None = None,
    ) -> list[Event]:
        """Filter events by criteria."""
        results = self._events
        if trace_id:
            results = [e for e in results if e.trace_id == trace_id]
        if agent_name:
            results = [e for e in results if e.agent_name == agent_name]
        if event_type:
            results = [e for e in results if e.event_type == event_type]
        if level:
            results = [e for e in results if e.level == level]
        return results

    def query_events(self, **filters: Any) -> list[dict[str, Any]]:
        """Query persisted (historical) events.

        Delegates to the ``PersistentEventStore`` if one is attached.
        Accepts the same keyword arguments as
        ``PersistentEventStore.query_events``.
        """
        if self.persistent_store is None:
            return [e.to_dict() for e in self.filter(
                trace_id=filters.get("trace_id"),
                agent_name=filters.get("agent_name"),
                event_type=(
                    EventType(filters["event_type"]) if filters.get("event_type") else None
                ),
                level=filters.get("level"),
            )]
        return self.persistent_store.query_events(**filters)

    def get_trace(self, trace_id: str) -> list[Event]:
        """Get all events for a specific trace (one user request end-to-end)."""
        return self.filter(trace_id=trace_id)

    def get_errors(self) -> list[Event]:
        """Get all error events."""
        return self.filter(level="error")

    def export_json(self, trace_id: str | None = None) -> str:
        """Export events as JSON (for audit logs, debugging)."""
        events = self.filter(trace_id=trace_id) if trace_id else self._events
        return json.dumps([e.to_dict() for e in events], indent=2, default=str)

    def get_summary(self) -> dict[str, Any]:
        """Get a summary of all events."""
        type_counts: dict[str, int] = {}
        for e in self._events:
            type_counts[e.event_type.value] = type_counts.get(e.event_type.value, 0) + 1

        return {
            "total_events": len(self._events),
            "event_types": type_counts,
            "unique_traces": len(set(e.trace_id for e in self._events if e.trace_id)),
            "unique_agents": len(set(e.agent_name for e in self._events if e.agent_name)),
            "errors": len(self.get_errors()),
            "costs": self.cost_tracker.get_summary(),
        }

    @property
    def events(self) -> list[Event]:
        return list(self._events)
