"""Domain tool: create_ab_test

Create an A/B test for a growth experiment.
"""

from forge.runtime.tools import Tool, ToolParameter


async def create_ab_test(hypothesis, variant_a, variant_b, success_metric) -> str:
    """Create an A/B test for a growth experiment."""
    # This tool provides context to the agent.
    # The agent will use primitive tools (run_command, read_write_file, http_request)
    # to actually execute the task described here.
    task_context = (
        "Task: Create an A/B test for a growth experiment.\n"
        f"  hypothesis: {hypothesis}\n"
        f"  variant_a: {variant_a}\n"
        f"  variant_b: {variant_b}\n"
        f"  success_metric: {success_metric}\n"
        "\nUse your available tools (run_command, read_write_file, http_request, "\n        "query_database) to accomplish this task. Create real files and run real commands."
    )
    return task_context


create_ab_test_tool = Tool(
    name="create_ab_test",
    description="Create an A/B test for a growth experiment.",
    parameters=[
        ToolParameter(name="hypothesis", type="string", description="What we're testing and expected impact", required=True),
        ToolParameter(name="variant_a", type="string", description="Control variant", required=True),
        ToolParameter(name="variant_b", type="string", description="Test variant", required=True),
        ToolParameter(name="success_metric", type="string", description="How to measure success", required=True),
    ],
    _fn=create_ab_test,
)
