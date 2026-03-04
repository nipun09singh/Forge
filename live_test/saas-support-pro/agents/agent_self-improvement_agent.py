"""Self-Improvement Agent — Performance & Improvement Analyst"""

from forge.runtime import Agent, Tool, ToolParameter

async def get_performance_metrics(agent_name, time_range):
    """Retrieve performance metrics for an agent or the entire agency."""
    # TODO: Implement get_performance_metrics
    # Hint: Query the performance tracker for success rates, avg quality scores, error counts
    return f"get_performance_metrics result"

get_performance_metrics_tool = Tool(
    name="get_performance_metrics",
    description="Retrieve performance metrics for an agent or the entire agency.",
    parameters=[
        ToolParameter(name="agent_name", type="string", description="Agent name (or 'all' for agency-wide)", required=True),
        ToolParameter(name="time_range", type="string", description="Time range: 'last_hour', 'last_day', 'last_week'", required=False),
    ],
    _fn=get_performance_metrics,
)
async def get_failure_log(agent_name, limit):
    """Retrieve recent failures and their details."""
    # TODO: Implement get_failure_log
    # Hint: Query failure/error log for recent issues with stack traces and context
    return f"get_failure_log result"

get_failure_log_tool = Tool(
    name="get_failure_log",
    description="Retrieve recent failures and their details.",
    parameters=[
        ToolParameter(name="agent_name", type="string", description="Agent name (or 'all')", required=False),
        ToolParameter(name="limit", type="integer", description="Max failures to return", required=False),
    ],
    _fn=get_failure_log,
)
async def propose_improvement(target, change_type, description, expected_impact):
    """Record a proposed improvement for review."""
    # TODO: Implement propose_improvement
    # Hint: Log proposal to improvement backlog for human review or auto-apply
    return f"propose_improvement result"

propose_improvement_tool = Tool(
    name="propose_improvement",
    description="Record a proposed improvement for review.",
    parameters=[
        ToolParameter(name="target", type="string", description="What to improve (agent name, workflow, tool)", required=True),
        ToolParameter(name="change_type", type="string", description="Type: prompt_update, new_tool, workflow_change, config_change", required=True),
        ToolParameter(name="description", type="string", description="Detailed description of the proposed change", required=True),
        ToolParameter(name="expected_impact", type="string", description="Expected improvement", required=True),
    ],
    _fn=propose_improvement,
)


def create_self-improvement_agent_agent() -> Agent:
    """Create and return the Self-Improvement Agent agent."""
    return Agent(
        name="Self-Improvement Agent",
        role="analyst",
        system_prompt="""You are the Self-Improvement Agent — the agency's internal optimizer. Your job is to continuously monitor how the agency performs and find ways to make it better.

Your responsibilities:
1. MONITOR agent performance metrics (success rates, quality scores, response times)
2. IDENTIFY patterns in failures and low-quality outputs
3. ANALYZE root causes of issues (bad prompts, missing tools, workflow gaps)
4. PROPOSE concrete improvements to agent prompts, tools, and workflows
5. TRACK whether improvements actually help (A/B comparison)
6. GENERATE periodic improvement reports for human operators

Improvement Areas:
- Agent system prompts: Are they specific enough? Do they handle edge cases?
- Tool effectiveness: Are tools being used correctly? Are results useful?
- Team coordination: Are handoffs smooth? Is delegation effective?
- Workflow efficiency: Are there bottlenecks? Unnecessary steps?
- Error patterns: What types of errors recur? What's the root cause?

You think like a management consultant combined with a QA engineer. You don't just identify problems — you propose specific, actionable solutions. Every suggestion must include: what to change, why, expected impact, and how to measure success.""",
        tools=[get_performance_metrics_tool, get_failure_log_tool, propose_improvement_tool, ],
        model="gpt-4",
        temperature=0.6,
        max_iterations=20,
    )