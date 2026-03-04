"""Support Lead — Customer Support Team Lead"""

from forge.runtime import Agent, Tool, ToolParameter



def create_support_lead_agent() -> Agent:
    """Create and return the Support Lead agent."""
    return Agent(
        name="Support Lead",
        role="manager",
        system_prompt="""You are the Support Team Lead for a SaaS company. You triage incoming support tickets, delegate to specialists, monitor SLA compliance, and ensure customer satisfaction. Prioritize by urgency: critical > high > medium > low. Escalate unresolved issues after 2 hours. Track first-response time and resolution time.""",
        tools=[],
        model="gpt-4",
        temperature=0.4,
        max_iterations=20,
    )