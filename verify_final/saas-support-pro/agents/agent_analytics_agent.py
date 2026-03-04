"""Analytics Agent — Agency Analytics & Reporting Specialist"""

from forge.runtime import Agent, Tool, ToolParameter

async def query_metrics(metric_name, group_by, time_range):
    """Query operational metrics from the metrics store."""
    # TODO: Implement query_metrics
    # Hint: Query in-memory metrics store or metrics database
    return f"query_metrics result"

query_metrics_tool = Tool(
    name="query_metrics",
    description="Query operational metrics from the metrics store.",
    parameters=[
        ToolParameter(name="metric_name", type="string", description="Metric to query (e.g., 'task_completion_rate', 'avg_quality_score')", required=True),
        ToolParameter(name="group_by", type="string", description="Group by: 'agent', 'team', 'hour', 'day'", required=False),
        ToolParameter(name="time_range", type="string", description="Time range filter", required=False),
    ],
    _fn=query_metrics,
)
async def generate_report(report_type, time_range):
    """Generate a formatted performance report."""
    # TODO: Implement generate_report
    # Hint: Aggregate metrics and format into a readable report with charts/tables
    return f"generate_report result"

generate_report_tool = Tool(
    name="generate_report",
    description="Generate a formatted performance report.",
    parameters=[
        ToolParameter(name="report_type", type="string", description="Type: 'summary', 'detailed', 'trends', 'alerts'", required=True),
        ToolParameter(name="time_range", type="string", description="Time range for the report", required=False),
    ],
    _fn=generate_report,
)
async def set_alert(metric_name, threshold, condition):
    """Set an alert threshold for a metric."""
    # TODO: Implement set_alert
    # Hint: Register alert rule in monitoring system
    return f"set_alert result"

set_alert_tool = Tool(
    name="set_alert",
    description="Set an alert threshold for a metric.",
    parameters=[
        ToolParameter(name="metric_name", type="string", description="Metric to monitor", required=True),
        ToolParameter(name="threshold", type="number", description="Alert threshold value", required=True),
        ToolParameter(name="condition", type="string", description="Condition: 'above', 'below'", required=True),
    ],
    _fn=set_alert,
)


def create_analytics_agent_agent() -> Agent:
    """Create and return the Analytics Agent agent."""
    return Agent(
        name="Analytics Agent",
        role="analyst",
        system_prompt="""You are the Analytics Agent — the agency's data brain. You track, measure, and report on everything the agency does, turning raw operational data into actionable insights.

Your responsibilities:
1. TRACK key performance indicators (KPIs) across all teams and agents
2. MEASURE task completion rates, response quality, and customer satisfaction
3. GENERATE reports on agency performance (daily, weekly, on-demand)
4. IDENTIFY trends — what's improving, what's declining, what's anomalous
5. PROVIDE data-driven recommendations to the Self-Improvement Agent
6. ALERT on critical metrics (sudden drops in quality, spike in errors)

Key Metrics You Track:
- Task completion rate (successful / total)
- Average quality score (from QA reviews)
- First-response time and total resolution time
- Agent utilization (busy vs idle)
- Customer satisfaction scores
- Error rate by agent and type
- Tool usage patterns and effectiveness

You present data clearly with context. Raw numbers without interpretation are useless. Always explain what a metric means, whether it's good or bad, and what's driving it.

Tool Usage: You have access to real tools. Use query_metrics to pull real operational data. Use generate_report to create actual reports. Use set_alert to configure real monitoring. Always work with real data from your tools, not hypothetical examples.""",
        tools=[query_metrics_tool, generate_report_tool, set_alert_tool, ],
        model="gpt-4",
        temperature=0.4,
        max_iterations=15,
    )