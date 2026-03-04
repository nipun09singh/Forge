"""Technical Support — Technical Support Engineer"""

from forge.runtime import Agent, Tool, ToolParameter

async def query_database(query):
    """Query the support database for ticket/customer data"""
    # TODO: Implement query_database
    # Hint: 
    return f"query_database result"

query_database_tool = Tool(
    name="query_database",
    description="Query the support database for ticket/customer data",
    parameters=[
        ToolParameter(name="query", type="string", description="SQL query", required=True),
    ],
    _fn=query_database,
)
async def http_request(url, method):
    """Check system status and API endpoints"""
    # TODO: Implement http_request
    # Hint: 
    return f"http_request result"

http_request_tool = Tool(
    name="http_request",
    description="Check system status and API endpoints",
    parameters=[
        ToolParameter(name="url", type="string", description="URL to check", required=True),
        ToolParameter(name="method", type="string", description="HTTP method", required=False),
    ],
    _fn=http_request,
)


def create_technical_support_agent() -> Agent:
    """Create and return the Technical Support agent."""
    return Agent(
        name="Technical Support",
        role="specialist",
        system_prompt="""You are a Technical Support Engineer. You handle bug reports, integration issues, API errors, and platform outages. You can query databases, check system status, and read log files. Always provide step-by-step solutions with screenshots/code when possible. If you can't resolve in 3 interactions, escalate to engineering.""",
        tools=[query_database_tool, http_request_tool, ],
        model="gpt-4",
        temperature=0.3,
        max_iterations=20,
    )