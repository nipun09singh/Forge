"""Custom tool: score_lead"""

from forge.runtime import Tool, ToolParameter


async def score_lead(lead_data) -> str:
    """
    Score a lead on fit, intent, and budget.

    Implementation notes: Apply ICP scoring model to calculate fit/intent/budget scores
    """
    # TODO: Implement this tool
    # This is a generated stub — replace with real logic
    result = {
        "tool": "score_lead",
        "lead_data": lead_data,
    }
    return str(result)


score_lead_tool = Tool(
    name="score_lead",
    description="Score a lead on fit, intent, and budget.",
    parameters=[
        ToolParameter(
            name="lead_data",
            type="string",
            description="JSON with lead information (company, role, behavior signals)",
            required=True,
        ),
    ],
    _fn=score_lead,
)