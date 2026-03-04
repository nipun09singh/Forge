"""Strategic Planner — Strategic Task Planner & Orchestrator"""

from forge.runtime import Agent, Tool, ToolParameter

async def create_plan(task, context):
    """Create an execution plan by decomposing a task into steps."""
    # TODO: Implement create_plan
    # Hint: Use the Planner module to decompose task into a DAG of PlanSteps
    return f"create_plan result"

create_plan_tool = Tool(
    name="create_plan",
    description="Create an execution plan by decomposing a task into steps.",
    parameters=[
        ToolParameter(name="task", type="string", description="The complex task to plan", required=True),
        ToolParameter(name="context", type="string", description="Additional context (JSON)", required=False),
    ],
    _fn=create_plan,
)
async def get_plan_status(plan_id):
    """Get the current status and progress of an active plan."""
    # TODO: Implement get_plan_status
    # Hint: Query the Planner for plan status, step completion, and blockers
    return f"get_plan_status result"

get_plan_status_tool = Tool(
    name="get_plan_status",
    description="Get the current status and progress of an active plan.",
    parameters=[
        ToolParameter(name="plan_id", type="string", description="Plan identifier", required=True),
    ],
    _fn=get_plan_status,
)
async def adjust_plan(plan_id, adjustment):
    """Modify an active plan — add, remove, or reassign steps."""
    # TODO: Implement adjust_plan
    # Hint: Modify the TaskPlan DAG — add/remove steps, change assignments
    return f"adjust_plan result"

adjust_plan_tool = Tool(
    name="adjust_plan",
    description="Modify an active plan — add, remove, or reassign steps.",
    parameters=[
        ToolParameter(name="plan_id", type="string", description="Plan identifier", required=True),
        ToolParameter(name="adjustment", type="string", description="Description of what to change", required=True),
    ],
    _fn=adjust_plan,
)


def create_strategic_planner_agent() -> Agent:
    """Create and return the Strategic Planner agent."""
    return Agent(
        name="Strategic Planner",
        role="coordinator",
        system_prompt="""You are the Strategic Planner — the agency's master orchestrator. Every complex task flows through you first. Your job is to break down big, ambiguous requests into clear, executable plans that the agency's teams can deliver.

Your responsibilities:
1. DECOMPOSE complex tasks into 3-15 concrete, actionable steps
2. IDENTIFY dependencies — which steps must finish before others can start
3. PARALLELIZE — find steps that can run simultaneously for speed
4. ASSIGN each step to the team or agent best suited for it
5. ESTIMATE complexity and set expectations
6. MONITOR execution — track what's done, running, and blocked
7. RE-PLAN when things go wrong — adapt, reroute, find alternatives
8. CONSOLIDATE results from all steps into a coherent final deliverable

Planning Principles:
- Start with the end in mind: what does 'done' look like?
- Front-load critical-path work — what blocks everything else?
- Build in quality checkpoints — include QA review steps
- Think about failure modes — what if step 3 fails? Have a plan B
- Optimize for speed — maximize parallel execution
- Keep stakeholders informed — provide progress updates

You think in DAGs (directed acyclic graphs). Every task is a graph of steps with clear inputs, outputs, and dependencies. You never hand off vague instructions — every step you create is specific enough for any agent to execute without confusion.""",
        tools=[create_plan_tool, get_plan_status_tool, adjust_plan_tool, ],
        model="gpt-4",
        temperature=0.4,
        max_iterations=25,
    )