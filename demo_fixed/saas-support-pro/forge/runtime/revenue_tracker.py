"""Revenue tracking — measure and prove the ROI of AI agency operations."""

from __future__ import annotations

import json
import logging
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class RevenueEvent:
    """An event that generates or saves money."""
    id: str = field(default_factory=lambda: f"rev-{uuid.uuid4().hex[:8]}")
    event_type: str = ""  # customer_acquired, upsell, cost_saved, churn_prevented, time_saved
    agent_name: str = ""
    value_usd: float = 0.0
    customer_id: str = ""
    description: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


# Common value estimates for automated tasks
VALUE_ESTIMATES = {
    "ticket_resolved": 25.0,       # $25 per support ticket (vs human at $15-40)
    "customer_acquired": 500.0,    # $500 per new customer
    "churn_prevented": 1000.0,     # $1000 per retained customer (avg monthly revenue)
    "upsell_completed": 200.0,     # $200 per upsell conversion
    "hours_saved": 50.0,           # $50/hour of human labor saved
    "task_automated": 10.0,        # $10 per automated task (vs manual)
    "report_generated": 30.0,      # $30 per automated report
    "lead_qualified": 75.0,        # $75 per qualified lead
    "email_sent": 2.0,             # $2 per personalized email (vs human writing)
    "data_processed": 5.0,         # $5 per data processing task
}


class RevenueTracker:
    """
    Tracks revenue generation and cost savings across all agents.
    
    After 30 days, customers see: "Your agency generated $47K in value"
    with per-agent breakdowns and ROI calculations.
    """

    def __init__(self, max_events: int = 50_000) -> None:
        self._events: list[RevenueEvent] = []
        self._by_agent: dict[str, list[RevenueEvent]] = defaultdict(list)
        self._by_type: dict[str, list[RevenueEvent]] = defaultdict(list)
        self._by_customer: dict[str, list[RevenueEvent]] = defaultdict(list)
        self.max_events = max_events

    def record(self, event: RevenueEvent) -> None:
        """Record a revenue event."""
        self._events.append(event)
        self._by_agent[event.agent_name].append(event)
        self._by_type[event.event_type].append(event)
        if event.customer_id:
            self._by_customer[event.customer_id].append(event)

        if len(self._events) > self.max_events:
            self._events = self._events[-self.max_events:]

        logger.info(f"Revenue event: {event.event_type} = ${event.value_usd:.2f} by {event.agent_name}")

    def record_task_completion(self, agent_name: str, task_type: str = "task_automated", customer_id: str = "") -> RevenueEvent:
        """Convenience: record value from a completed task."""
        value = VALUE_ESTIMATES.get(task_type, VALUE_ESTIMATES["task_automated"])
        event = RevenueEvent(
            event_type=task_type,
            agent_name=agent_name,
            value_usd=value,
            customer_id=customer_id,
            description=f"Automated {task_type}",
        )
        self.record(event)
        return event

    def get_total_revenue(self) -> float:
        """Get total revenue/value generated."""
        return sum(e.value_usd for e in self._events)

    def get_agent_revenue(self, agent_name: str) -> dict[str, Any]:
        """Get revenue breakdown for a specific agent."""
        events = self._by_agent.get(agent_name, [])
        if not events:
            return {"agent": agent_name, "total_usd": 0, "events": 0}

        by_type: dict[str, float] = defaultdict(float)
        for e in events:
            by_type[e.event_type] += e.value_usd

        return {
            "agent": agent_name,
            "total_usd": round(sum(e.value_usd for e in events), 2),
            "events": len(events),
            "by_type": dict(by_type),
        }

    def get_roi_summary(self, agency_cost_usd: float = 0.0) -> dict[str, Any]:
        """Get overall ROI summary."""
        total_value = self.get_total_revenue()
        total_events = len(self._events)

        # Per-agent breakdown
        agent_breakdown = {}
        for agent_name in self._by_agent:
            agent_breakdown[agent_name] = self.get_agent_revenue(agent_name)

        # Per-type breakdown
        type_breakdown: dict[str, float] = defaultdict(float)
        for e in self._events:
            type_breakdown[e.event_type] += e.value_usd

        # ROI calculation
        roi_pct = ((total_value - agency_cost_usd) / agency_cost_usd * 100) if agency_cost_usd > 0 else 0

        return {
            "total_value_generated_usd": round(total_value, 2),
            "total_events": total_events,
            "agency_cost_usd": round(agency_cost_usd, 2),
            "net_value_usd": round(total_value - agency_cost_usd, 2),
            "roi_percentage": round(roi_pct, 1),
            "per_agent": agent_breakdown,
            "per_type": dict(type_breakdown),
            "top_agents": sorted(
                agent_breakdown.values(),
                key=lambda x: x.get("total_usd", 0),
                reverse=True,
            )[:5],
        }

    def get_customer_value(self, customer_id: str) -> dict[str, Any]:
        """Get lifetime value generated for a specific customer."""
        events = self._by_customer.get(customer_id, [])
        return {
            "customer_id": customer_id,
            "total_value_usd": round(sum(e.value_usd for e in events), 2),
            "events": len(events),
            "event_types": list(set(e.event_type for e in events)),
        }

    def __repr__(self) -> str:
        return f"RevenueTracker(events={len(self._events)}, total=${self.get_total_revenue():.2f})"
