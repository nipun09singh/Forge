"""Custom tool: score_output"""

from forge.runtime import Tool, ToolParameter


async def score_output(output_text, criteria, context) -> str:
    """
    Score an output against quality criteria. Returns structured quality assessment.

    Implementation notes: Score output on accuracy, completeness, clarity, professionalism (each 1-10), return aggregate
    """
    # TODO: Implement this tool
    # This is a generated stub — replace with real logic
    result = {
        "tool": "score_output",
        "output_text": output_text,
        "criteria": criteria,
        "context": context,
    }
    return str(result)


score_output_tool = Tool(
    name="score_output",
    description="Score an output against quality criteria. Returns structured quality assessment.",
    parameters=[
        ToolParameter(
            name="output_text",
            type="string",
            description="The output to evaluate",
            required=True,
        ),
        ToolParameter(
            name="criteria",
            type="string",
            description="Specific criteria to evaluate against",
            required=False,
        ),
        ToolParameter(
            name="context",
            type="string",
            description="Original request context",
            required=False,
        ),
    ],
    _fn=score_output,
)