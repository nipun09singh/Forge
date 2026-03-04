# Forge API Reference

## Table of Contents

- [Core — Forge Engine](#core)
- [Runtime — Agent](#agent)
- [Runtime — Agency](#agency)
- [Runtime — Team](#team)
- [Runtime — Planner](#planner)
- [Runtime — Tools](#tools)
- [Runtime — Memory](#memory)
- [Runtime — Observability](#observability)
- [Runtime — Quality & Improvement](#quality)
- [Runtime — Human Approval](#human-approval)
- [Runtime — Integrations](#integrations)
- [Blueprints](#blueprints)
- [Configuration](#configuration)
- [Generated Agency API Endpoints](#api-endpoints)

---

## Core

### ForgeEngine

The meta-agency that generates complete AI agencies from domain descriptions. Operates an internal 5-phase pipeline: analyze domain → inject archetypes → critique/refine → generate code → package runtime.

```python
from forge.core.engine import ForgeEngine

engine = ForgeEngine(
    model="gpt-4",                 # LLM model (default: from env or gpt-4)
    api_key="sk-...",              # OpenAI API key (default: from OPENAI_API_KEY)
    base_url=None,                 # Custom API endpoint
    output_dir=Path("generated"),  # Where to write generated agencies
)
```

#### Methods

| Method | Returns | Description |
|--------|---------|-------------|
| `await create_agency(domain, overwrite=False)` | `(AgencyBlueprint, Path)` | Generate a complete agency from a domain description. Runs 5-phase pipeline: analyze → inject archetypes → critique/refine → generate → package. |
| `await list_generated()` | `list[dict]` | List all previously generated agencies in the output directory. |

#### Example

```python
blueprint, path = await engine.create_agency(
    "e-commerce customer support with upselling and retention"
)
print(f"Generated at {path} with {len(blueprint.all_agents)} agents")
```

---

## Agent

The base AI agent — an autonomous employee in an AI agency. Each agent has a role, persona (system prompt), access to tools, shared memory, and the ability to spawn sub-agents for delegation.

```python
from forge.runtime.agent import Agent

agent = Agent(
    name="Support Specialist",
    role="specialist",
    system_prompt="You are a helpful support specialist...",
    tools=[my_tool],          # Optional list of Tool instances
    model="gpt-4",            # LLM model
    temperature=0.7,          # LLM temperature (0-2)
    max_iterations=20,        # Max reasoning loop iterations
    enable_reflection=True,   # Enable self-critique loop
    quality_threshold=0.8,    # Min quality score for reflection
    max_reflections=5,        # Max self-critique iterations
)
```

#### Key Methods

| Method | Returns | Description |
|--------|---------|-------------|
| `await execute(task, context=None)` | `TaskResult` | Execute a task using the agent's reasoning loop. Calls LLM, uses tools, iterates until done or `max_iterations` reached. |
| `await spawn_sub_agent(name, role, system_prompt, task)` | `TaskResult` | Create a sub-agent to handle a delegated task. The sub-agent shares the parent's LLM client and memory. |
| `set_llm_client(client)` | `None` | Inject the `AsyncOpenAI` client (called by Agency during setup). |
| `set_memory(memory)` | `None` | Share a `SharedMemory` store with this agent. |
| `set_quality_gate(gate)` | `None` | Set quality gate for output validation. Also creates an internal `ReflectionEngine`. |
| `set_event_log(log)` | `None` | Set event log for observability. |
| `set_trace_context(ctx)` | `None` | Set trace context for distributed tracing. |
| `set_approval_gate(gate)` | `None` | Set human approval gate (enables approval checks before tool execution). |
| `set_performance_tracker(tracker)` | `None` | Set performance tracker for metrics recording. |

#### TaskResult

```python
@dataclass
class TaskResult:
    success: bool               # Whether the task completed successfully
    output: str                 # The agent's response text
    data: dict[str, Any] = {}   # Additional structured data
    sub_tasks: list[str] = []   # Sub-task descriptions (if any)
```

#### AgentStatus

```python
class AgentStatus(str, Enum):
    IDLE = "idle"
    WORKING = "working"
    WAITING = "waiting"
    COMPLETED = "completed"
    ERROR = "error"
```

#### Example

```python
agent.set_llm_client(openai_client)
result = await agent.execute("Help customer with billing issue")
print(result.output)
```

---

## Agency

Top-level container managing all agents, teams, and shared resources. Provides LLM client injection, shared memory, task routing, and dynamic agent spawning.

```python
from forge.runtime.agency import Agency

agency = Agency(
    name="My Agency",
    description="AI-powered customer support",
    model="gpt-4",
    api_key="sk-...",
    base_url=None,
)
```

#### Key Methods

| Method | Returns | Description |
|--------|---------|-------------|
| `add_team(team)` | `None` | Add a team (wires LLM client, memory, and router for all agents in the team). |
| `add_agent(agent, team_name=None)` | `None` | Add a standalone agent or assign to an existing team. |
| `spawn_agent(name, role, system_prompt, team_name=None)` | `Agent` | Dynamically create and register a new agent (unlimited scaling). |
| `await execute(task, team_name=None, context=None, use_planner=False)` | `TaskResult` | Execute a task. Routes to planner (if `use_planner`), named team, first team, or standalone agent. |
| `await execute_parallel(tasks)` | `list[TaskResult]` | Execute multiple tasks in parallel. Each task is a dict with `task`, optional `team`, and optional `context`. |
| `await plan(task, context=None)` | `dict` | Plan a complex task without executing. Returns `plan_id`, `summary`, and step count. |
| `get_status()` | `dict` | Get agency status snapshot including teams, agents, statuses, and memory entry count. |

#### Example

```python
agency = Agency(name="Support", model="gpt-4", api_key="sk-...")
agency.add_team(support_team)
result = await agency.execute("Handle billing inquiry", team_name="Support Team")
```

---

## Team

A team of agents that collaborate on tasks. Supports two execution modes: led execution (team lead delegates to members) and parallel execution (all agents work independently).

```python
from forge.runtime.team import Team

team = Team(
    name="Support Team",
    lead=lead_agent,         # Team lead (delegates to members)
    agents=[agent1, agent2], # Team members
    shared_memory=memory,    # Optional shared memory
)
```

#### Key Methods

| Method | Returns | Description |
|--------|---------|-------------|
| `add_agent(agent)` | `None` | Add an agent to the team (shares team memory). |
| `remove_agent(agent_id)` | `None` | Remove an agent by ID. |
| `await execute(task, context=None)` | `TaskResult` | Execute a task. If lead exists, uses led execution; otherwise parallel execution. |

#### Execution Modes

- **Led execution:** The lead agent receives the task along with a roster of team members. It gets two auto-injected tools:
  - `delegate_to_agent(agent_name, subtask)` — Delegate a subtask to a specific team member.
  - `delegate_parallel(tasks_json)` — Delegate multiple subtasks in parallel (JSON list of `{agent_name, subtask}`).
- **Parallel execution:** All agents work on the task independently in parallel. Results are combined with agent name prefixes.

---

## Planner

Strategic task planner — decomposes complex tasks into executable DAGs (directed acyclic graphs) using LLM-based analysis.

```python
from forge.runtime.planner import Planner

planner = Planner(
    teams=agency.teams,    # Available teams
    model="gpt-4",         # LLM model for planning
    max_replans=3,         # Max re-planning attempts on failure
)
planner.set_llm_client(llm_client)
```

#### Key Methods

| Method | Returns | Description |
|--------|---------|-------------|
| `await plan(task, context=None)` | `TaskPlan` | Decompose a task into steps with dependencies and team assignments. Uses LLM analysis. |
| `await execute_plan(plan)` | `dict` | Execute a plan respecting dependency order. Runs independent steps in parallel. Re-plans on failure. |
| `await plan_and_execute(task, context=None)` | `dict` | Plan + execute in one call. |
| `set_llm_client(client)` | `None` | Set the LLM client for planning. |
| `set_teams(teams)` | `None` | Update available teams. |
| `set_agents(agents)` | `None` | Update available standalone agents. |
| `get_active_plans()` | `list[dict]` | Get status of all currently active plans. |
| `get_plan_history(limit=20)` | `list[dict]` | Get recent plan execution history. |

#### TaskPlan

```python
@dataclass
class TaskPlan:
    id: str                     # Unique plan ID
    task: str                   # Original task description
    steps: list[PlanStep]       # Ordered steps
    status: str                 # "pending", "executing", "completed", "failed"

plan.progress               # float (0.0 - 1.0) — completion ratio
plan.completed_steps        # list[PlanStep] — steps that finished
plan.failed_steps           # list[PlanStep] — steps that failed
plan.pending_steps          # list[PlanStep] — steps not yet started
plan.running_steps          # list[PlanStep] — currently executing steps
plan.get_ready_steps()      # Steps whose dependencies are satisfied
plan.get_step(step_id)      # Get a step by ID
plan.to_summary()           # Human-readable plan summary with status icons
```

#### PlanStep

```python
@dataclass
class PlanStep:
    id: str                          # Step identifier
    description: str                 # What this step does
    assigned_team: str = ""          # Team to execute this step
    assigned_agent: str = ""         # Specific agent (if applicable)
    depends_on: list[str] = []       # IDs of steps that must complete first
    status: StepStatus = PENDING     # pending, ready, running, completed, failed, skipped
    estimated_complexity: str = "medium"  # low, medium, high
    max_retries: int = 2             # Max retry attempts
    can_retry: bool                  # Property: True if retry_count < max_retries
```

---

## Tools

Tool system for agent capabilities. Tools wrap callable functions with metadata for LLM function calling.

```python
from forge.runtime.tools import Tool, ToolParameter, tool, ToolRegistry

# Method 1: Dataclass construction
my_tool = Tool(
    name="search",
    description="Search the database",
    parameters=[
        ToolParameter(
            name="query",
            type="string",
            description="Search query",
            required=True,
        ),
    ],
    _fn=my_search_function,
)

# Method 2: Decorator (auto-infers parameters from function signature)
@tool(name="greet", description="Greet someone")
async def greet(name: str) -> str:
    return f"Hello {name}!"
```

#### Tool

| Method | Returns | Description |
|--------|---------|-------------|
| `await run(**kwargs)` | `Any` | Execute the tool. Validates required parameters. Supports both sync and async functions. |
| `to_openai_schema()` | `dict` | Convert to OpenAI function calling schema format. |

#### ToolParameter

```python
@dataclass
class ToolParameter:
    name: str             # Parameter name
    type: str             # "string", "integer", "number", "boolean", "array", "object"
    description: str      # Parameter description
    required: bool = True # Whether the parameter is required
    enum: list[str] | None = None  # Allowed values
    default: Any = None   # Default value
```

#### ToolRegistry

| Method | Returns | Description |
|--------|---------|-------------|
| `register(tool)` | `None` | Register a tool. |
| `get(name)` | `Tool \| None` | Get a tool by name. |
| `list_tools()` | `list[Tool]` | List all registered tools. |
| `get_openai_tools_schema()` | `list[dict]` | Get all tools in OpenAI function calling format. |

---

## Memory

Shared memory with pluggable persistence backends. Thread-safe via asyncio Lock.

```python
from forge.runtime.memory import SharedMemory

# In-memory (default)
mem = SharedMemory()

# Persistent (SQLite)
mem = SharedMemory.persistent("agency_memory.db")

# Custom backend
mem = SharedMemory.with_backend(my_backend)
```

#### Key Methods

| Method | Returns | Description |
|--------|---------|-------------|
| `store(key, value, author="", tags=None)` | `None` | Store a value (sync). |
| `await astore(key, value, author="", tags=None)` | `None` | Store a value (async, thread-safe). |
| `recall(key)` | `Any \| None` | Retrieve a value by key. Falls back to persistent backend. |
| `await arecall(key)` | `Any \| None` | Retrieve a value by key (async). |
| `search(tag=None, author=None)` | `list[MemoryEntry]` | Search memories by tag or author. |
| `search_keyword(keyword, limit=20)` | `list[dict]` | Full-text keyword search (uses persistent backend). |
| `get_context_summary(max_entries=20)` | `str` | Get a summary of recent memory for agent context injection. |
| `clear()` | `None` | Clear all memory (in-memory and backend). |

#### MemoryEntry

```python
@dataclass
class MemoryEntry:
    key: str             # Storage key
    value: Any           # Stored value
    author: str = ""     # Who stored this
    timestamp: str       # ISO 8601 UTC timestamp
    tags: list[str] = [] # Searchable tags
```

#### Example

```python
mem = SharedMemory.persistent("agency_memory.db")
mem.store("customer:123", {"name": "Alice"}, author="intake_agent", tags=["customer", "vip"])
value = mem.recall("customer:123")
results = mem.search(tag="vip")
results = mem.search_keyword("Alice")
```

---

## Observability

Structured event logging, distributed tracing, and cost tracking.

### EventLog

Append-only structured event log with filtering, export, and analysis capabilities.

```python
from forge.runtime.observability import EventLog, TraceContext, CostTracker, EventType, Event

event_log = EventLog()
```

#### Key Methods

| Method | Returns | Description |
|--------|---------|-------------|
| `emit(event)` | `None` | Record an event. Also logs to Python logger. |
| `emit_llm_call(agent_name, model, messages_count, tools_count, ...)` | `Event` | Convenience: emit an LLM call event. |
| `emit_llm_response(agent_name, model, prompt_tokens, completion_tokens, has_tool_calls, duration_ms, ...)` | `Event` | Convenience: emit LLM response with automatic cost tracking. |
| `emit_tool_use(agent_name, tool_name, args, ...)` | `Event` | Convenience: emit a tool invocation event. |
| `emit_tool_result(agent_name, tool_name, success, output_preview, duration_ms, ...)` | `Event` | Convenience: emit a tool result event. |
| `filter(trace_id=None, agent_name=None, event_type=None, level=None)` | `list[Event]` | Filter events by criteria. |
| `get_trace(trace_id)` | `list[Event]` | Get all events for a specific trace (end-to-end request). |
| `get_errors()` | `list[Event]` | Get all error-level events. |
| `get_summary()` | `dict` | Get summary with event counts, unique traces/agents, errors, and costs. |
| `export_json(trace_id=None)` | `str` | Export events as JSON string (for audit logs, debugging). |
| `events` | `list[Event]` | Property: copy of all events. |

### TraceContext

Manages trace IDs for correlating events across agents, teams, and plans.

```python
trace = TraceContext()            # Auto-generates trace ID
trace = TraceContext("my-trace")  # Explicit trace ID
```

| Method | Returns | Description |
|--------|---------|-------------|
| `new_span()` | `str` | Create a new span within this trace. |
| `current_span()` | `str` | Get the current span ID. |
| `end_span()` | `str \| None` | End the current span. |
| `child()` | `TraceContext` | Create a child context sharing the same trace_id. |

### CostTracker

Tracks token usage and estimated costs across all LLM calls.

```python
costs = event_log.cost_tracker.get_summary()
# → {"total_tokens": 1500, "total_cost_usd": 0.0045, "per_agent": {...}, ...}
```

| Method | Returns | Description |
|--------|---------|-------------|
| `record(model, prompt_tokens, completion_tokens, agent_name="")` | `float` | Record a single LLM call. Returns estimated cost in USD. |
| `get_summary()` | `dict` | Get cost summary: total tokens, total cost, per-agent breakdown, call count. |

### EventType

```python
class EventType(str, Enum):
    LLM_CALL = "llm_call"
    LLM_RESPONSE = "llm_response"
    TOOL_USE = "tool_use"
    TOOL_RESULT = "tool_result"
    AGENT_START = "agent_start"
    AGENT_COMPLETE = "agent_complete"
    AGENT_ERROR = "agent_error"
    TEAM_DISPATCH = "team_dispatch"
    PLAN_CREATED = "plan_created"
    STEP_EXECUTED = "step_executed"
    QUALITY_CHECK = "quality_check"
    REFLECTION = "reflection"
    HUMAN_APPROVAL = "human_approval"
    MEMORY_STORE = "memory_store"
    COST_TRACKED = "cost_tracked"
```

### Event

```python
@dataclass
class Event:
    event_type: EventType
    agent_name: str = ""
    trace_id: str = ""
    span_id: str             # Auto-generated
    timestamp: str           # ISO 8601 UTC
    data: dict[str, Any] = {}
    tokens: int = 0
    cost_usd: float = 0.0
    duration_ms: float = 0.0
    parent_span_id: str = ""
    level: str = "info"      # "info", "warning", "error"
```

---

## Quality & Improvement

Self-improvement runtime with quality gates, reflection, performance tracking, and feedback collection.

### QualityGate

Validates agent outputs against quality criteria. If output doesn't pass, it's sent back for revision with feedback, creating a critique → revise loop.

```python
from forge.runtime.improvement import QualityGate, QualityVerdict

gate = QualityGate(
    min_score=0.8,        # Minimum passing score (0.0 - 1.0)
    max_revisions=5,      # Max revision iterations
    evaluator=None,       # Optional custom evaluator function
)
gate.set_llm_client(llm_client)  # For LLM-based evaluation
```

| Method | Returns | Description |
|--------|---------|-------------|
| `await check(output, task, criteria="", iteration=0)` | `QualityVerdict` | Check if output meets quality standards. Uses custom evaluator or LLM-based self-evaluation. |
| `set_llm_client(client)` | `None` | Set the LLM client for self-evaluation. |

#### QualityVerdict

```python
@dataclass
class QualityVerdict:
    passed: bool           # Whether the output passed quality check
    score: float           # 0.0 to 1.0
    feedback: str = ""     # Specific feedback for improvement
    needs_revision: bool = False
    iteration: int = 0
```

### ReflectionEngine

Enables agents to reflect on their outputs and self-improve through an iterative evaluate → critique → improve cycle.

```python
from forge.runtime.improvement import ReflectionEngine

engine = ReflectionEngine(quality_gate=gate)
```

| Method | Returns | Description |
|--------|---------|-------------|
| `await reflect_and_improve(agent, task, initial_output, max_reflections=5)` | `(str, list[QualityVerdict])` | Reflect and iteratively improve until quality is met. Returns final output and verdict history. |

### PerformanceTracker

Tracks performance metrics for all agents in an agency.

```python
from forge.runtime.improvement import PerformanceTracker, TaskMetric

tracker = PerformanceTracker()

agent.set_quality_gate(gate)
agent.set_performance_tracker(tracker)
agent.enable_reflection = True
```

| Method | Returns | Description |
|--------|---------|-------------|
| `record(metric)` | `None` | Record a `TaskMetric`. |
| `get_agent_stats(agent_name)` | `dict` | Get aggregate stats for an agent (success rate, avg quality, avg duration, recent failures). |
| `get_agency_stats()` | `dict` | Get aggregate stats for the entire agency with per-agent breakdown. |
| `get_failure_patterns(limit=20)` | `list[dict]` | Get recent failures for pattern analysis. |

#### TaskMetric

```python
@dataclass
class TaskMetric:
    agent_name: str
    task_preview: str
    success: bool
    quality_score: float
    duration_seconds: float
    iterations_used: int = 1
    revision_count: int = 0
    timestamp: float         # Unix timestamp
```

### FeedbackCollector

Collects and aggregates feedback on agent outputs from users, system, or QA agents.

```python
from forge.runtime.improvement import FeedbackCollector, Feedback

collector = FeedbackCollector()
collector.collect(Feedback(
    agent_name="Support Specialist",
    task_preview="Handle billing inquiry",
    rating=0.9,
    comment="Thorough response",
    source="user",
))
avg = collector.get_avg_rating("Support Specialist")
```

---

## Human Approval

Approval gates for human-in-the-loop workflows. Agents pause execution before tool calls and request human approval.

### HumanApprovalGate

Console-based approval gate with rich-formatted prompts.

```python
from forge.runtime.human import HumanApprovalGate, Urgency

gate = HumanApprovalGate(
    auto_approve_urgency=Urgency.LOW,  # Auto-approve LOW urgency actions (None = always ask)
    timeout_seconds=300,                # Timeout for human response (default: 5 minutes)
)
agent.set_approval_gate(gate)
```

| Method | Returns | Description |
|--------|---------|-------------|
| `await approve(request)` | `ApprovalResult` | Request human approval for an action. Auto-approves if urgency is at or below threshold. |
| `get_history()` | `list[dict]` | Get approval history. |

### WebhookApprovalGate

Sends approval requests via webhook and polls for response. Useful for Slack, Teams, email, or custom approval UIs.

```python
from forge.runtime.human import WebhookApprovalGate

gate = WebhookApprovalGate(
    webhook_url="https://hooks.slack.com/...",  # Where to send approval requests
    poll_url="https://my-api.com/approvals",    # Where to poll for decisions
    poll_interval=5,                             # Seconds between polls
    timeout_seconds=300,
)
```

### Enums & Data Classes

```python
class ApprovalDecision(str, Enum):
    APPROVED = "approved"
    REJECTED = "rejected"
    MODIFIED = "modified"     # Approved with modifications

class Urgency(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

@dataclass
class ApprovalRequest:
    request_id: str           # Auto-generated
    agent_name: str
    action_description: str
    action_type: str          # "tool_call", "final_output", "delegation"
    context: dict
    urgency: Urgency = MEDIUM

@dataclass
class ApprovalResult:
    decision: ApprovalDecision
    feedback: str = ""
    modified_action: str = "" # If MODIFIED, the revised action
    approver: str = "human"
```

---

## Integrations

Built-in real working tools — not stubs. They make actual HTTP requests, send real emails, query real databases, and read/write real files.

```python
from forge.runtime.integrations import BuiltinToolkit

# Get all built-in tools
tools = BuiltinToolkit.all_tools(
    sandbox_dir="./data",
    db_path="./data/agency.db",
    smtp_host="smtp.gmail.com",  # Optional; email tool only added if provided
)

# Individual tool factories
from forge.runtime.integrations.http_tool import create_http_tool
from forge.runtime.integrations.email_tool import create_email_tool
from forge.runtime.integrations.sql_tool import create_sql_tool
from forge.runtime.integrations.file_tool import create_file_tool
from forge.runtime.integrations.webhook_tool import create_webhook_tool
```

| Tool | Function Name | Description |
|------|---------------|-------------|
| HTTP | `http_request` | Real HTTP GET/POST/PUT/DELETE requests |
| Email | `send_email` | Real SMTP email sending (configure via `SMTP_*` env vars) |
| SQL | `query_database` | Real SQLite queries (DROP/TRUNCATE blocked for safety) |
| File | `read_write_file` | Sandboxed file read/write/append/list/delete |
| Webhook | `send_webhook` | Real JSON webhook delivery |

#### BuiltinToolkit

| Method | Returns | Description |
|--------|---------|-------------|
| `all_tools(sandbox_dir="./data", db_path="./data/agency.db", smtp_host=None)` | `list[Tool]` | Get all built-in tools. Email tool is included only if `smtp_host` is provided. |
| `get_tool_names()` | `list[str]` | Get names of all available built-in tools. |

---

## Blueprints

Pydantic data models for agency design. These are the schema the Forge generates from domain descriptions.

```python
from forge.core.blueprint import (
    AgencyBlueprint,   # Complete agency design
    AgentBlueprint,    # Individual agent design
    TeamBlueprint,     # Team structure
    ToolBlueprint,     # Tool definition
    WorkflowBlueprint, # Workflow with steps
    WorkflowStep,      # Individual workflow step
    APIEndpoint,       # REST API endpoint
    AgentRole,         # Role enum
)
```

### AgencyBlueprint

The master document containing everything needed to generate a deployable agency.

| Field | Type | Description |
|-------|------|-------------|
| `name` | `str` | Agency name |
| `slug` | `str` | URL/directory-safe name |
| `description` | `str` | What this agency does |
| `domain` | `str` | The domain this agency serves |
| `teams` | `list[TeamBlueprint]` | All teams in the agency |
| `workflows` | `list[WorkflowBlueprint]` | Agency workflows |
| `api_endpoints` | `list[APIEndpoint]` | API endpoints to expose |
| `shared_tools` | `list[ToolBlueprint]` | Tools shared across all agents |
| `environment_variables` | `dict[str, str]` | Required env vars |
| `model` | `str` | Default LLM model (default: `"gpt-4"`) |
| `all_agents` | `list[AgentBlueprint]` | Property: all agents across all teams |
| `all_tools` | `list[ToolBlueprint]` | Property: all tools (shared + agent-specific), deduplicated |

### AgentBlueprint

| Field | Type | Description |
|-------|------|-------------|
| `name` | `str` | Agent display name |
| `role` | `AgentRole` | Role archetype |
| `title` | `str` | Job title within the agency |
| `system_prompt` | `str` | System prompt defining persona and behavior |
| `capabilities` | `list[str]` | List of capabilities |
| `tools` | `list[ToolBlueprint]` | Tools available to this agent |
| `model` | `str` | LLM model (default: `"gpt-4"`) |
| `temperature` | `float` | LLM temperature (0.0–2.0, default: 0.7) |
| `max_iterations` | `int` | Max reasoning iterations (1–100, default: 20) |
| `can_spawn_sub_agents` | `bool` | Whether this agent can create sub-agents |

### AgentRole

```python
class AgentRole(str, Enum):
    MANAGER = "manager"
    SPECIALIST = "specialist"
    RESEARCHER = "researcher"
    WRITER = "writer"
    REVIEWER = "reviewer"
    COORDINATOR = "coordinator"
    ANALYST = "analyst"
    SUPPORT = "support"
    CUSTOM = "custom"
```

### TeamBlueprint

| Field | Type | Description |
|-------|------|-------------|
| `name` | `str` | Team name |
| `description` | `str` | What this team does |
| `lead` | `AgentBlueprint \| None` | Team lead agent |
| `agents` | `list[AgentBlueprint]` | Team member agents |
| `allow_dynamic_scaling` | `bool` | Allow spawning new agents at runtime (default: `True`) |
| `max_concurrent_tasks` | `int` | Max parallel tasks (default: 10) |

### WorkflowBlueprint / WorkflowStep

```python
class WorkflowBlueprint(BaseModel):
    name: str                        # Workflow name
    description: str = ""            # What this workflow accomplishes
    trigger: str = "manual"          # What triggers this workflow
    steps: list[WorkflowStep] = []   # Ordered steps

class WorkflowStep(BaseModel):
    id: str                          # Step identifier
    description: str                 # What happens in this step
    assigned_team: str = ""          # Team responsible
    assigned_agent: str = ""         # Specific agent
    depends_on: list[str] = []       # Step IDs this depends on
    parallel: bool = False           # Can run in parallel
```

### APIEndpoint

```python
class APIEndpoint(BaseModel):
    path: str                        # API path (e.g., /api/tasks)
    method: str = "POST"             # HTTP method
    description: str = ""            # What this endpoint does
    request_schema: dict = {}        # Request body schema
    response_schema: dict = {}       # Response schema
    handler_team: str = ""           # Team that handles this endpoint
```

---

## Configuration

Centralized configuration loaded from environment variables and `.env` files.

```python
from forge.config import get_config, ForgeConfig

config = get_config()  # Singleton, auto-loads from env + .env file
```

| Field | Env Variable | Default | Description |
|-------|-------------|---------|-------------|
| `model` | `FORGE_MODEL` | `"gpt-4"` | LLM model |
| `api_key` | `OPENAI_API_KEY` | `""` | OpenAI API key |
| `base_url` | `OPENAI_BASE_URL` | `""` | Custom API endpoint |
| `temperature` | `FORGE_TEMPERATURE` | `0.7` | LLM temperature |
| `max_retries` | `FORGE_MAX_RETRIES` | `3` | LLM call retry limit |
| `max_iterations` | `FORGE_MAX_ITERATIONS` | `20` | Agent max reasoning iterations |
| `max_reflections` | `FORGE_MAX_REFLECTIONS` | `5` | Max self-critique iterations |
| `quality_threshold` | `FORGE_QUALITY_THRESHOLD` | `0.8` | Min quality score |
| `enable_reflection` | `FORGE_ENABLE_REFLECTION` | `true` | Enable self-critique |
| `max_refinement_iterations` | `FORGE_MAX_REFINEMENTS` | `10` | Blueprint refinement iterations |
| `min_quality_score` | `FORGE_MIN_QUALITY` | `0.8` | Min blueprint quality score |
| `db_path` | `AGENCY_DB_PATH` | `"./data/agency_memory.db"` | SQLite memory path |
| `data_dir` | `AGENCY_DATA_DIR` | `"./data"` | Data directory |
| `log_level` | `FORGE_LOG_LEVEL` | `"INFO"` | Logging level |
| `smtp_host` | `SMTP_HOST` | `""` | SMTP server host |
| `smtp_port` | `SMTP_PORT` | `587` | SMTP server port |
| `smtp_user` | `SMTP_USER` | `""` | SMTP username |
| `smtp_pass` | `SMTP_PASS` | `""` | SMTP password |
| `smtp_from` | `SMTP_FROM` | `""` | SMTP from address |
| `output_dir` | `FORGE_OUTPUT_DIR` | `"generated"` | Output directory for generated agencies |

#### Utility Methods

| Method | Returns | Description |
|--------|---------|-------------|
| `ForgeConfig.from_env()` | `ForgeConfig` | Create config from environment variables. |
| `config.has_api_key()` | `bool` | Check if an API key is configured. |
| `config.has_smtp()` | `bool` | Check if SMTP is configured. |
| `config.to_dict()` | `dict` | Export config as dict (sensitive values redacted). |
| `get_config()` | `ForgeConfig` | Get the global singleton config. |
| `reset_config()` | `None` | Reset config (forces re-read from env on next call). |

---

## Generated Agency API Endpoints

Every generated agency includes a FastAPI server that exposes these REST endpoints:

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/task` | Execute a task (body: `{task, team?, context?, use_planner?}`) |
| `POST` | `/api/task/stream` | Execute with streaming (SSE) |
| `POST` | `/api/plan` | Plan a task (decompose without executing) |
| `POST` | `/api/plan/{id}/execute` | Execute a previously created plan |
| `GET` | `/api/status` | Agency status + cost + event metrics |
| `GET` | `/api/events` | Recent observable events (filterable) |
| `GET` | `/api/costs` | Cost tracking summary |
| `POST` | `/api/memory/search` | Search agency memory |
| `POST` | `/api/memory/store` | Store a value in memory |
| `GET` | `/health` | Health check |
