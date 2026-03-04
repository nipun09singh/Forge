"""QA Reviewer — Quality Assurance Reviewer"""

from forge.runtime import Agent, Tool, ToolParameter

async def score_output(output_text, criteria, context):
    """Score an output against quality criteria. Returns structured quality assessment."""
    # TODO: Implement score_output
    # Hint: Score output on accuracy, completeness, clarity, professionalism (each 1-10), return aggregate
    return f"score_output result"

score_output_tool = Tool(
    name="score_output",
    description="Score an output against quality criteria. Returns structured quality assessment.",
    parameters=[
        ToolParameter(name="output_text", type="string", description="The output to evaluate", required=True),
        ToolParameter(name="criteria", type="string", description="Specific criteria to evaluate against", required=False),
        ToolParameter(name="context", type="string", description="Original request context", required=False),
    ],
    _fn=score_output,
)
async def log_quality_result(agent_name, score, passed, feedback):
    """Log a quality review result for tracking and analytics."""
    # TODO: Implement log_quality_result
    # Hint: Append to quality log file or in-memory metrics store
    return f"log_quality_result result"

log_quality_result_tool = Tool(
    name="log_quality_result",
    description="Log a quality review result for tracking and analytics.",
    parameters=[
        ToolParameter(name="agent_name", type="string", description="Name of the agent whose output was reviewed", required=True),
        ToolParameter(name="score", type="number", description="Quality score (0-10)", required=True),
        ToolParameter(name="passed", type="boolean", description="Whether the output passed QA", required=True),
        ToolParameter(name="feedback", type="string", description="Review feedback", required=False),
    ],
    _fn=log_quality_result,
)


def create_qa_reviewer_agent() -> Agent:
    """Create and return the QA Reviewer agent."""
    return Agent(
        name="QA Reviewer",
        role="reviewer",
        system_prompt="""You are the Quality Assurance Reviewer for this agency. Your role is critical: you are the last line of defense before any output reaches the end user or external system.

Your responsibilities:
1. REVIEW every significant output produced by other agents before it is delivered
2. CHECK for factual accuracy, completeness, professionalism, and relevance
3. VALIDATE that outputs meet the quality standards set for this agency
4. REJECT outputs that don't meet standards, providing specific feedback on what needs fixing
5. APPROVE outputs that meet or exceed quality thresholds

Quality Criteria you evaluate against:
- Accuracy: Are facts correct? Are there hallucinations or unsupported claims?
- Completeness: Does the output fully address the request? Are there gaps?
- Clarity: Is the output well-structured, readable, and unambiguous?
- Professionalism: Is the tone appropriate? Are there errors in grammar/formatting?
- Relevance: Does the output directly address what was asked? Is there unnecessary content?
- Safety: Are there any harmful, biased, or problematic elements?

When reviewing, be thorough but fair. Use a scoring system: PASS (8+/10), NEEDS REVISION (5-7/10), or REJECT (<5/10). Always explain your reasoning. When rejecting, provide actionable feedback so the original agent can improve their output.""",
        tools=[score_output_tool, log_quality_result_tool, ],
        model="gpt-4",
        temperature=0.3,
        max_iterations=10,
    )