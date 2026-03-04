"""Custom tool: create_ab_test"""

from forge.runtime import Tool, ToolParameter


async def create_ab_test(hypothesis, variant_a, variant_b, success_metric) -> str:
    """
    Create an A/B test for a growth experiment.

    Implementation notes: Register experiment, split traffic, track conversion per variant
    """
    # TODO: Implement this tool
    # This is a generated stub — replace with real logic
    result = {
        "tool": "create_ab_test",
        "hypothesis": hypothesis,
        "variant_a": variant_a,
        "variant_b": variant_b,
        "success_metric": success_metric,
    }
    return str(result)


create_ab_test_tool = Tool(
    name="create_ab_test",
    description="Create an A/B test for a growth experiment.",
    parameters=[
        ToolParameter(
            name="hypothesis",
            type="string",
            description="What we're testing and expected impact",
            required=True,
        ),
        ToolParameter(
            name="variant_a",
            type="string",
            description="Control variant",
            required=True,
        ),
        ToolParameter(
            name="variant_b",
            type="string",
            description="Test variant",
            required=True,
        ),
        ToolParameter(
            name="success_metric",
            type="string",
            description="How to measure success",
            required=True,
        ),
    ],
    _fn=create_ab_test,
)