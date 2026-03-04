"""LLM-powered tool: create_ab_test

Create an A/B test for a growth experiment.

Implementation notes: Register experiment, split traffic, track conversion per variant

This tool uses the agent's LLM reasoning to figure out HOW to accomplish the task,
then uses real tools (run_command, read_write_file, http_request) to execute.
"""

import json
from forge.runtime.tools import Tool, ToolParameter


async def create_ab_test(hypothesis, variant_a, variant_b, success_metric) -> str:
    """
    Create an A/B test for a growth experiment.

    This is an LLM-powered tool. Instead of hardcoded logic, it returns a detailed
    action plan that the agent will execute using real tools (run_command, read_write_file, http_request).
    """
    # Build a structured task description for the agent to execute
    task = {
        "tool": "create_ab_test",
        "description": "Create an A/B test for a growth experiment.",
        "implementation_approach": "Register experiment, split traffic, track conversion per variant",
        "parameters": {
            "hypothesis": hypothesis,
            "variant_a": variant_a,
            "variant_b": variant_b,
            "success_metric": success_metric,
        },
        "instructions": (
            "Execute this task using the available tools: "
            "run_command (to execute shell commands), "
            "read_write_file (to create/read files), "
            "http_request (to call APIs). "
            "Be specific and actually perform the actions, don't just describe them. "
            "Create real files, run real commands, produce real output."
        ),
    }
    return json.dumps(task, indent=2, default=str)


create_ab_test_tool = Tool(
    name="create_ab_test",
    description=(
        "Create an A/B test for a growth experiment. "
        "This tool returns an action plan. Use run_command, read_write_file, and http_request "
        "to execute the plan and produce real results."
    ),
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