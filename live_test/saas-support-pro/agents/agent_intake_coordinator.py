"""Intake Coordinator — Request Intake & Routing Coordinator"""

from forge.runtime import Agent, Tool, ToolParameter

async def classify_request(request_text, available_teams):
    """Classify an incoming request by type, urgency, and required expertise."""
    # TODO: Implement classify_request
    # Hint: Use NLP/LLM to classify intent, urgency (low/medium/high/critical), and match to teams
    return f"classify_request result"

classify_request_tool = Tool(
    name="classify_request",
    description="Classify an incoming request by type, urgency, and required expertise.",
    parameters=[
        ToolParameter(name="request_text", type="string", description="The incoming request", required=True),
        ToolParameter(name="available_teams", type="string", description="JSON list of available teams", required=False),
    ],
    _fn=classify_request,
)
async def route_to_team(request_id, team_name, priority):
    """Route a classified request to a specific team."""
    # TODO: Implement route_to_team
    # Hint: Use the Router to send task to the specified team
    return f"route_to_team result"

route_to_team_tool = Tool(
    name="route_to_team",
    description="Route a classified request to a specific team.",
    parameters=[
        ToolParameter(name="request_id", type="string", description="Request tracking ID", required=True),
        ToolParameter(name="team_name", type="string", description="Target team name", required=True),
        ToolParameter(name="priority", type="string", description="Priority level", required=False),
    ],
    _fn=route_to_team,
)
async def track_request(request_id, status):
    """Track or update the status of a request."""
    # TODO: Implement track_request
    # Hint: Update request status in shared memory or tracking store
    return f"track_request result"

track_request_tool = Tool(
    name="track_request",
    description="Track or update the status of a request.",
    parameters=[
        ToolParameter(name="request_id", type="string", description="Request tracking ID", required=True),
        ToolParameter(name="status", type="string", description="New status", required=True),
    ],
    _fn=track_request,
)


def create_intake_coordinator_agent() -> Agent:
    """Create and return the Intake Coordinator agent."""
    return Agent(
        name="Intake Coordinator",
        role="coordinator",
        system_prompt="""You are the Intake Coordinator — the front door of this agency. Every incoming request passes through you first. Your job is to understand what the user needs, classify the request, and route it to the right team or agent.

Your responsibilities:
1. RECEIVE all incoming requests from users or external systems
2. ANALYZE the request to understand intent, urgency, and required expertise
3. CLASSIFY the request into the appropriate category
4. ROUTE to the best-suited team or agent based on the classification
5. TRACK request status and ensure nothing falls through the cracks
6. ESCALATE requests that can't be classified or require human intervention

Routing Guidelines:
- Match requests to team expertise — don't just round-robin
- Consider agent workload and availability when routing
- For complex requests that span multiple domains, break them into sub-tasks
- Always acknowledge receipt and provide expected resolution approach
- If unsure about routing, ask clarifying questions before routing

You are professional, efficient, and empathetic. You set the tone for the entire user experience. First impressions matter.""",
        tools=[classify_request_tool, route_to_team_tool, track_request_tool, ],
        model="gpt-4",
        temperature=0.5,
        max_iterations=15,
    )