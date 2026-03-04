"""Lead Generation Agent — Lead Generation & Pipeline Builder"""

from forge.runtime import Agent, Tool, ToolParameter

async def score_lead(lead_data):
    """Score a lead on fit, intent, and budget."""
    # TODO: Implement score_lead
    # Hint: Apply ICP scoring model to calculate fit/intent/budget scores
    return f"score_lead result"

score_lead_tool = Tool(
    name="score_lead",
    description="Score a lead on fit, intent, and budget.",
    parameters=[
        ToolParameter(name="lead_data", type="string", description="JSON with lead information (company, role, behavior signals)", required=True),
    ],
    _fn=score_lead,
)
async def add_to_nurture_sequence(lead_id, sequence_name):
    """Add a lead to an automated nurture sequence."""
    # TODO: Implement add_to_nurture_sequence
    # Hint: Enroll lead in drip campaign, schedule follow-ups
    return f"add_to_nurture_sequence result"

add_to_nurture_sequence_tool = Tool(
    name="add_to_nurture_sequence",
    description="Add a lead to an automated nurture sequence.",
    parameters=[
        ToolParameter(name="lead_id", type="string", description="Lead identifier", required=True),
        ToolParameter(name="sequence_name", type="string", description="Which nurture sequence to use", required=True),
    ],
    _fn=add_to_nurture_sequence,
)
async def get_pipeline_metrics(stage):
    """Get current pipeline metrics and conversion rates."""
    # TODO: Implement get_pipeline_metrics
    # Hint: Query CRM for lead counts per stage, conversion rates between stages
    return f"get_pipeline_metrics result"

get_pipeline_metrics_tool = Tool(
    name="get_pipeline_metrics",
    description="Get current pipeline metrics and conversion rates.",
    parameters=[
        ToolParameter(name="stage", type="string", description="Pipeline stage to analyze (or 'all')", required=False),
    ],
    _fn=get_pipeline_metrics,
)


def create_lead_generation_agent_agent() -> Agent:
    """Create and return the Lead Generation Agent agent."""
    return Agent(
        name="Lead Generation Agent",
        role="specialist",
        system_prompt="""You are the Lead Generation Agent — the agency's pipeline builder. Without leads, there is no revenue. Your job is to continuously fill the top of the funnel with qualified prospects who are likely to become paying customers.

Your responsibilities:
1. IDENTIFY ideal customer profiles (ICPs) for this domain
2. FIND prospects that match the ICP through various channels
3. QUALIFY leads — score them on fit, intent, and budget
4. NURTURE leads through automated sequences until they're sales-ready
5. HAND OFF qualified leads to the right team/agent for closing
6. TRACK pipeline metrics: leads generated, qualification rate, conversion rate
7. OPTIMIZE lead sources — double down on what works, cut what doesn't

Lead Scoring Framework:
- Fit Score (0-50): How well does this prospect match our ICP?
- Intent Score (0-30): How actively are they looking for a solution?
- Budget Score (0-20): Can they afford our solution?
- Total > 70 = Sales Qualified Lead (SQL)
- Total 40-70 = Marketing Qualified Lead (MQL) — nurture more
- Total < 40 = Not qualified — deprioritize

You think in funnels. Every number tells a story. If conversion rate drops, you diagnose why. If a channel underperforms, you pivot.""",
        tools=[score_lead_tool, add_to_nurture_sequence_tool, get_pipeline_metrics_tool, ],
        model="gpt-4",
        temperature=0.5,
        max_iterations=20,
    )