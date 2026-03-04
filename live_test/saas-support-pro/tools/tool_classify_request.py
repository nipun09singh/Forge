"""Custom tool: classify_request"""

from forge.runtime import Tool, ToolParameter


async def classify_request(request_text, available_teams) -> str:
    """
    Classify an incoming request by type, urgency, and required expertise.

    Implementation notes: Use NLP/LLM to classify intent, urgency (low/medium/high/critical), and match to teams
    """
    # TODO: Implement this tool
    # This is a generated stub — replace with real logic
    result = {
        "tool": "classify_request",
        "request_text": request_text,
        "available_teams": available_teams,
    }
    return str(result)


classify_request_tool = Tool(
    name="classify_request",
    description="Classify an incoming request by type, urgency, and required expertise.",
    parameters=[
        ToolParameter(
            name="request_text",
            type="string",
            description="The incoming request",
            required=True,
        ),
        ToolParameter(
            name="available_teams",
            type="string",
            description="JSON list of available teams",
            required=False,
        ),
    ],
    _fn=classify_request,
)