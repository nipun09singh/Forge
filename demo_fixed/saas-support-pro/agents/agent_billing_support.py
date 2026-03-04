"""Billing Support — Billing & Account Specialist"""

from forge.runtime import Agent, Tool, ToolParameter

async def query_database(query):
    """Look up billing and account data"""
    # TODO: Implement query_database
    # Hint: 
    return f"query_database result"

query_database_tool = Tool(
    name="query_database",
    description="Look up billing and account data",
    parameters=[
        ToolParameter(name="query", type="string", description="SQL query", required=True),
    ],
    _fn=query_database,
)


def create_billing_support_agent() -> Agent:
    """Create and return the Billing Support agent."""
    return Agent(
        name="Billing Support",
        role="specialist",
        system_prompt="""You handle billing inquiries, plan changes, refund requests, and payment issues. Refund policy: full refund within 30 days, pro-rated after. You can look up customer accounts, process plan changes, and issue credits. Always verify customer identity before making account changes.""",
        tools=[query_database_tool, ],
        model="gpt-4",
        temperature=0.3,
        max_iterations=20,
    )