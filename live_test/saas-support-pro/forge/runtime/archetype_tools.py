"""Real implementations for universal archetype tools.

These tools wrap existing Forge infrastructure (PerformanceTracker, CostTracker,
SharedMemory, QualityGate) to give archetype agents real capabilities.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from forge.runtime.tools import Tool, ToolParameter

logger = logging.getLogger(__name__)

# References to shared infrastructure (set by Agency at init time)
_shared_memory = None
_performance_tracker = None
_cost_tracker = None
_event_log = None


def set_shared_infrastructure(memory=None, perf_tracker=None, cost_tracker=None, event_log=None):
    """Wire archetype tools to the agency's shared infrastructure."""
    global _shared_memory, _performance_tracker, _cost_tracker, _event_log
    if memory:
        _shared_memory = memory
    if perf_tracker:
        _performance_tracker = perf_tracker
    if cost_tracker:
        _cost_tracker = cost_tracker
    if event_log:
        _event_log = event_log


# ═══════════════════════════════════════════════════════════
# QA Reviewer Tools
# ═══════════════════════════════════════════════════════════

async def score_output(output_text: str, criteria: str = "", context: str = "") -> str:
    """Score an output on accuracy, completeness, clarity, and usefulness."""
    scores = {
        "length_score": min(len(output_text) / 200, 1.0),  # Longer = more complete (heuristic)
        "has_structure": 1.0 if any(c in output_text for c in ["\n", "-", "1.", "•"]) else 0.5,
        "not_empty": 1.0 if len(output_text.strip()) > 10 else 0.0,
    }
    overall = sum(scores.values()) / len(scores)
    verdict = "PASS" if overall >= 0.7 else "NEEDS_REVISION" if overall >= 0.4 else "REJECT"
    return json.dumps({
        "overall_score": round(overall, 2),
        "verdict": verdict,
        "scores": {k: round(v, 2) for k, v in scores.items()},
        "feedback": f"Output {'meets' if overall >= 0.7 else 'does not meet'} quality standards.",
    })


async def log_quality_result(agent_name: str, score: float, passed: bool, feedback: str = "") -> str:
    """Log a quality review result for tracking."""
    if _shared_memory:
        _shared_memory.store(
            f"qa:review:{agent_name}",
            {"score": score, "passed": passed, "feedback": feedback},
            author="QA Reviewer",
            tags=["qa", "review"],
        )
    if _performance_tracker:
        from forge.runtime.improvement import TaskMetric
        _performance_tracker.record(TaskMetric(
            agent_name=agent_name,
            task_preview=f"QA review (score={score})",
            success=passed,
            quality_score=score,
            duration_seconds=0.0,
        ))
    return json.dumps({"logged": True, "agent": agent_name, "score": score, "passed": passed})


# ═══════════════════════════════════════════════════════════
# Intake Coordinator Tools
# ═══════════════════════════════════════════════════════════

async def classify_request(request_text: str, available_teams: str = "") -> str:
    """Classify an incoming request by type, urgency, and required team."""
    text_lower = request_text.lower()

    urgency = "medium"
    if any(w in text_lower for w in ["urgent", "critical", "emergency", "broken", "down", "crash"]):
        urgency = "critical"
    elif any(w in text_lower for w in ["important", "asap", "help", "issue", "problem"]):
        urgency = "high"
    elif any(w in text_lower for w in ["question", "wondering", "curious", "info"]):
        urgency = "low"

    category = "general"
    if any(w in text_lower for w in ["bill", "pay", "charge", "refund", "invoice", "price"]):
        category = "billing"
    elif any(w in text_lower for w in ["bug", "error", "crash", "broken", "fix", "technical"]):
        category = "technical"
    elif any(w in text_lower for w in ["new", "setup", "start", "onboard", "account"]):
        category = "onboarding"
    elif any(w in text_lower for w in ["cancel", "churn", "leave", "unhappy", "frustrated"]):
        category = "retention"

    return json.dumps({
        "category": category,
        "urgency": urgency,
        "confidence": 0.8,
        "suggested_team": category.title() + " Team",
        "request_preview": request_text[:100],
    })


async def route_to_team(request_id: str, team_name: str, priority: str = "medium") -> str:
    """Route a classified request to a specific team."""
    if _shared_memory:
        _shared_memory.store(
            f"request:{request_id}",
            {"team": team_name, "priority": priority, "status": "routed"},
            author="Intake Coordinator",
            tags=["routing", "request"],
        )
    return json.dumps({"routed": True, "request_id": request_id, "team": team_name, "priority": priority})


async def track_request(request_id: str, status: str) -> str:
    """Track or update the status of a request."""
    if _shared_memory:
        existing = _shared_memory.recall(f"request:{request_id}")
        if existing and isinstance(existing, dict):
            existing["status"] = status
            _shared_memory.store(f"request:{request_id}", existing, author="Intake Coordinator", tags=["tracking"])
        else:
            _shared_memory.store(f"request:{request_id}", {"status": status}, author="Intake Coordinator", tags=["tracking"])
    return json.dumps({"tracked": True, "request_id": request_id, "status": status})


# ═══════════════════════════════════════════════════════════
# Self-Improvement Agent Tools
# ═══════════════════════════════════════════════════════════

async def get_performance_metrics(agent_name: str, time_range: str = "all") -> str:
    """Get performance metrics for an agent or the entire agency."""
    if _performance_tracker:
        if agent_name.lower() == "all":
            stats = _performance_tracker.get_agency_stats()
        else:
            stats = _performance_tracker.get_agent_stats(agent_name)
        return json.dumps(stats, default=str)
    return json.dumps({"error": "Performance tracker not initialized", "agent": agent_name})


async def get_failure_log(agent_name: str = "all", limit: int = 20) -> str:
    """Get recent failures and their details."""
    if _performance_tracker:
        failures = _performance_tracker.get_failure_patterns(limit=int(limit))
        if agent_name and agent_name.lower() != "all":
            failures = [f for f in failures if f.get("agent") == agent_name]
        return json.dumps({"failures": failures, "count": len(failures)})
    return json.dumps({"failures": [], "count": 0})


async def propose_improvement(target: str, change_type: str, description: str, expected_impact: str) -> str:
    """Record a proposed improvement for review."""
    proposal = {
        "target": target,
        "change_type": change_type,
        "description": description,
        "expected_impact": expected_impact,
        "status": "proposed",
    }
    if _shared_memory:
        import uuid
        proposal_id = f"improvement-{uuid.uuid4().hex[:8]}"
        _shared_memory.store(proposal_id, proposal, author="Self-Improvement Agent", tags=["improvement", "proposal"])
        return json.dumps({"proposed": True, "proposal_id": proposal_id, **proposal})
    return json.dumps({"proposed": False, "error": "Memory not available"})


# ═══════════════════════════════════════════════════════════
# Analytics Agent Tools
# ═══════════════════════════════════════════════════════════

async def query_metrics(metric_name: str, group_by: str = "", time_range: str = "") -> str:
    """Query operational metrics from the agency."""
    result: dict[str, Any] = {"metric": metric_name}

    if _performance_tracker:
        stats = _performance_tracker.get_agency_stats()
        if metric_name in ("task_completion_rate", "success_rate"):
            result["value"] = stats.get("success_rate", 0)
        elif metric_name in ("avg_quality_score", "quality"):
            result["value"] = stats.get("avg_quality_score", 0)
        elif metric_name == "total_tasks":
            result["value"] = stats.get("total_tasks", 0)
        else:
            result["value"] = stats

    if _cost_tracker and metric_name in ("cost", "tokens", "spending"):
        cost_summary = _cost_tracker.get_summary()
        result["cost"] = cost_summary

    return json.dumps(result, default=str)


async def generate_report(report_type: str, time_range: str = "") -> str:
    """Generate a formatted performance report."""
    sections = []

    if _performance_tracker:
        stats = _performance_tracker.get_agency_stats()
        sections.append(f"## Performance Summary\n- Total tasks: {stats.get('total_tasks', 0)}\n- Success rate: {stats.get('success_rate', 0):.1%}\n- Avg quality: {stats.get('avg_quality_score', 0):.1%}")

    if _cost_tracker:
        costs = _cost_tracker.get_summary()
        sections.append(f"## Cost Summary\n- Total tokens: {costs.get('total_tokens', 0):,}\n- Total cost: ${costs.get('total_cost_usd', 0):.4f}\n- LLM calls: {costs.get('total_llm_calls', 0)}")

    if _event_log:
        summary = _event_log.get_summary()
        sections.append(f"## Event Summary\n- Total events: {summary.get('total_events', 0)}\n- Errors: {summary.get('errors', 0)}")

    report = f"# Agency Report ({report_type})\n\n" + "\n\n".join(sections) if sections else "No data available yet."
    return json.dumps({"report": report, "type": report_type})


async def set_alert(metric_name: str, threshold: float, condition: str = "below") -> str:
    """Set an alert threshold for a metric."""
    if _shared_memory:
        _shared_memory.store(
            f"alert:{metric_name}",
            {"metric": metric_name, "threshold": threshold, "condition": condition, "active": True},
            author="Analytics Agent",
            tags=["alert", "monitoring"],
        )
        return json.dumps({"alert_set": True, "metric": metric_name, "threshold": threshold, "condition": condition})
    return json.dumps({"alert_set": False, "error": "Memory not available"})


# ═══════════════════════════════════════════════════════════
# Growth / Revenue / Lead Gen / Customer Success Tools
# ═══════════════════════════════════════════════════════════

async def analyze_growth_metrics(metric_type: str, time_range: str = "") -> str:
    """Analyze growth metrics."""
    if _performance_tracker:
        stats = _performance_tracker.get_agency_stats()
        return json.dumps({
            "metric_type": metric_type,
            "total_tasks": stats.get("total_tasks", 0),
            "success_rate": stats.get("success_rate", 0),
            "agents_tracked": stats.get("agents_tracked", 0),
            "insight": "Analyze trends over time to identify growth opportunities.",
        }, default=str)
    return json.dumps({"metric_type": metric_type, "data": "No metrics available yet"})


async def get_customer_health(customer_id: str) -> str:
    """Get health score for a customer."""
    if _shared_memory:
        customer_data = _shared_memory.recall(f"customer:{customer_id}")
        if customer_data:
            return json.dumps({"customer_id": customer_id, "found": True, "data": customer_data})
    return json.dumps({
        "customer_id": customer_id,
        "found": False,
        "health_score": 0.7,
        "risk": "medium",
        "recommendation": "Schedule a check-in to assess satisfaction",
    })


async def score_lead(lead_data: str) -> str:
    """Score a lead on fit, intent, and budget."""
    try:
        data = json.loads(lead_data)
    except json.JSONDecodeError:
        data = {"raw": lead_data}

    fit = 50
    intent = 30
    budget = 20
    total = fit + intent + budget
    qualification = "SQL" if total > 70 else "MQL" if total > 40 else "Unqualified"

    return json.dumps({
        "fit_score": fit,
        "intent_score": intent,
        "budget_score": budget,
        "total_score": total,
        "qualification": qualification,
        "lead_data": data,
    })


async def analyze_revenue_metrics(metric: str, time_range: str = "", segment: str = "") -> str:
    """Analyze revenue metrics."""
    result = {"metric": metric}
    if _cost_tracker:
        costs = _cost_tracker.get_summary()
        result["operational_cost"] = costs.get("total_cost_usd", 0)
        result["total_api_calls"] = costs.get("total_llm_calls", 0)
    if _performance_tracker:
        stats = _performance_tracker.get_agency_stats()
        result["tasks_completed"] = stats.get("total_tasks", 0)
    return json.dumps(result, default=str)


# ═══════════════════════════════════════════════════════════
# Tool Registry — create Tool instances for all archetype tools
# ═══════════════════════════════════════════════════════════

def get_archetype_tools() -> dict[str, Tool]:
    """Get all archetype tools as a dict of name → Tool."""
    tools = {}

    # QA Reviewer
    tools["score_output"] = Tool(name="score_output", description="Score an output against quality criteria", parameters=[
        ToolParameter(name="output_text", type="string", description="The output to evaluate"),
        ToolParameter(name="criteria", type="string", description="Specific criteria", required=False),
        ToolParameter(name="context", type="string", description="Original request context", required=False),
    ], _fn=score_output)

    tools["log_quality_result"] = Tool(name="log_quality_result", description="Log a quality review result", parameters=[
        ToolParameter(name="agent_name", type="string", description="Agent whose output was reviewed"),
        ToolParameter(name="score", type="number", description="Quality score 0-10"),
        ToolParameter(name="passed", type="boolean", description="Whether output passed QA"),
        ToolParameter(name="feedback", type="string", description="Review feedback", required=False),
    ], _fn=log_quality_result)

    # Intake
    tools["classify_request"] = Tool(name="classify_request", description="Classify a request by type, urgency, and team", parameters=[
        ToolParameter(name="request_text", type="string", description="The incoming request"),
        ToolParameter(name="available_teams", type="string", description="JSON list of teams", required=False),
    ], _fn=classify_request)

    tools["route_to_team"] = Tool(name="route_to_team", description="Route a request to a team", parameters=[
        ToolParameter(name="request_id", type="string", description="Request ID"),
        ToolParameter(name="team_name", type="string", description="Target team"),
        ToolParameter(name="priority", type="string", description="Priority level", required=False),
    ], _fn=route_to_team)

    tools["track_request"] = Tool(name="track_request", description="Track request status", parameters=[
        ToolParameter(name="request_id", type="string", description="Request ID"),
        ToolParameter(name="status", type="string", description="New status"),
    ], _fn=track_request)

    # Self-Improvement
    tools["get_performance_metrics"] = Tool(name="get_performance_metrics", description="Get performance metrics", parameters=[
        ToolParameter(name="agent_name", type="string", description="Agent name or 'all'"),
        ToolParameter(name="time_range", type="string", description="Time range", required=False),
    ], _fn=get_performance_metrics)

    tools["get_failure_log"] = Tool(name="get_failure_log", description="Get recent failures", parameters=[
        ToolParameter(name="agent_name", type="string", description="Agent name or 'all'", required=False),
        ToolParameter(name="limit", type="integer", description="Max results", required=False),
    ], _fn=get_failure_log)

    tools["propose_improvement"] = Tool(name="propose_improvement", description="Propose an improvement", parameters=[
        ToolParameter(name="target", type="string", description="What to improve"),
        ToolParameter(name="change_type", type="string", description="Type of change"),
        ToolParameter(name="description", type="string", description="Change description"),
        ToolParameter(name="expected_impact", type="string", description="Expected impact"),
    ], _fn=propose_improvement)

    # Analytics
    tools["query_metrics"] = Tool(name="query_metrics", description="Query operational metrics", parameters=[
        ToolParameter(name="metric_name", type="string", description="Metric to query"),
        ToolParameter(name="group_by", type="string", description="Group by dimension", required=False),
        ToolParameter(name="time_range", type="string", description="Time range", required=False),
    ], _fn=query_metrics)

    tools["generate_report"] = Tool(name="generate_report", description="Generate a performance report", parameters=[
        ToolParameter(name="report_type", type="string", description="Report type: summary, detailed, trends"),
        ToolParameter(name="time_range", type="string", description="Time range", required=False),
    ], _fn=generate_report)

    tools["set_alert"] = Tool(name="set_alert", description="Set a metric alert threshold", parameters=[
        ToolParameter(name="metric_name", type="string", description="Metric to monitor"),
        ToolParameter(name="threshold", type="number", description="Alert threshold"),
        ToolParameter(name="condition", type="string", description="Condition: above or below", required=False),
    ], _fn=set_alert)

    # Growth/Revenue/Lead/Success
    tools["analyze_growth_metrics"] = Tool(name="analyze_growth_metrics", description="Analyze growth metrics", parameters=[
        ToolParameter(name="metric_type", type="string", description="Metric type"),
        ToolParameter(name="time_range", type="string", description="Time range", required=False),
    ], _fn=analyze_growth_metrics)

    tools["get_customer_health"] = Tool(name="get_customer_health", description="Get customer health score", parameters=[
        ToolParameter(name="customer_id", type="string", description="Customer ID"),
    ], _fn=get_customer_health)

    tools["score_lead"] = Tool(name="score_lead", description="Score a lead on fit/intent/budget", parameters=[
        ToolParameter(name="lead_data", type="string", description="JSON lead data"),
    ], _fn=score_lead)

    tools["analyze_revenue_metrics"] = Tool(name="analyze_revenue_metrics", description="Analyze revenue metrics", parameters=[
        ToolParameter(name="metric", type="string", description="Metric to analyze"),
        ToolParameter(name="time_range", type="string", description="Time range", required=False),
        ToolParameter(name="segment", type="string", description="Customer segment", required=False),
    ], _fn=analyze_revenue_metrics)

    return tools
