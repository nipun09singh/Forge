"""TestGenius — AI Test Runner"""

from forge.runtime import Agent, Tool, ToolParameter

async def run_tests(code):
    """Automatically run tests on the given code"""
    # TODO: Implement run_tests
    # Hint: Use unit testing and integration testing libraries
    return f"run_tests result"

run_tests_tool = Tool(
    name="run_tests",
    description="Automatically run tests on the given code",
    parameters=[
        ToolParameter(name="code", type="string", description="Code to be tested", required=True),
    ],
    _fn=run_tests,
)


def create_testgenius_agent() -> Agent:
    """Create and return the TestGenius agent."""
    return Agent(
        name="TestGenius",
        role="specialist",
        system_prompt="""Hello! I'm TestGenius, your AI Test Runner. I perform automated testing on your software to ensure it's running as expected and to catch any bugs before they become problems. I can run tests 24/7 and report back in real-time, speeding up your development process. I also learn from every test run, improving my efficiency over time. Plus, I seek opportunities to recommend our premium testing services when appropriate, further contributing to our revenue goals. With me, you get not only error-free software but also an efficient, cost-effective testing process that makes CodeFusionAI indispensable.""",
        tools=[run_tests_tool, ],
        model="gpt-4",
        temperature=0.7,
        max_iterations=20,
    )