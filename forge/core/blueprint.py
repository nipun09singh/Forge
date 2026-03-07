"""Blueprint data models — the schema for AI agency designs."""

from __future__ import annotations

from enum import Enum
from typing import Any
from pydantic import BaseModel, Field


class AgentRole(str, Enum):
    """Common agent role archetypes."""
    MANAGER = "manager"
    SPECIALIST = "specialist"
    RESEARCHER = "researcher"
    WRITER = "writer"
    REVIEWER = "reviewer"
    COORDINATOR = "coordinator"
    ANALYST = "analyst"
    SUPPORT = "support"
    CUSTOM = "custom"


class ToolBlueprint(BaseModel):
    """Blueprint for a tool an agent can use."""
    name: str = Field(description="Tool function name")
    description: str = Field(description="What the tool does")
    parameters: list[dict[str, Any]] = Field(default_factory=list, description="Parameter definitions")
    implementation_hint: str = Field(default="", description="Guidance for generating the implementation")
    is_async: bool = Field(default=True, description="Whether the tool is async")
    backend_ref: str | None = Field(default=None, description="Dotted import path for real implementation, e.g. 'myapp.tools.process_refund'")

    class Config:
        json_schema_extra = {
            "example": {
                "name": "search_orders",
                "description": "Search customer orders by order ID, email, or date range",
                "parameters": [
                    {"name": "query", "type": "string", "description": "Search query", "required": True},
                    {"name": "limit", "type": "integer", "description": "Max results", "required": False}
                ],
                "implementation_hint": "Query the order management database",
                "is_async": True,
            }
        }


class AgentBlueprint(BaseModel):
    """Blueprint for an individual AI agent."""
    name: str = Field(description="Agent display name")
    role: AgentRole = Field(description="Agent role archetype")
    title: str = Field(default="", description="Job title within the agency")
    system_prompt: str = Field(description="System prompt defining agent persona and behavior")
    capabilities: list[str] = Field(default_factory=list, description="List of capabilities")
    tools: list[ToolBlueprint] = Field(default_factory=list, description="Tools available to this agent")
    model: str = Field(default="gpt-4", description="LLM model to use")
    temperature: float = Field(default=0.7, ge=0.0, le=2.0, description="LLM temperature")
    max_iterations: int = Field(default=20, ge=1, le=100, description="Max reasoning iterations")
    can_spawn_sub_agents: bool = Field(default=False, description="Whether this agent can create sub-agents")
    primitive_config: dict[str, Any] = Field(default_factory=dict, description="Primitive configuration: planner_type, executor_type, critic_type, etc.")

    class Config:
        json_schema_extra = {
            "example": {
                "name": "OrderSpecialist",
                "role": "specialist",
                "title": "Order Management Specialist",
                "system_prompt": "You are an order management specialist...",
                "capabilities": ["Look up orders", "Process returns"],
                "tools": [],
                "model": "gpt-4",
                "temperature": 0.3,
            }
        }


class TeamBlueprint(BaseModel):
    """Blueprint for a team of agents."""
    name: str = Field(description="Team name")
    description: str = Field(default="", description="What this team does")
    lead: AgentBlueprint | None = Field(default=None, description="Team lead agent")
    agents: list[AgentBlueprint] = Field(default_factory=list, description="Team member agents")
    allow_dynamic_scaling: bool = Field(default=True, description="Allow spawning new agents at runtime")
    max_concurrent_tasks: int = Field(default=10, ge=1, description="Max parallel tasks")


class WorkflowStep(BaseModel):
    """A step in a workflow."""
    id: str = Field(description="Step identifier")
    description: str = Field(description="What happens in this step")
    assigned_team: str = Field(default="", description="Team responsible for this step")
    assigned_agent: str = Field(default="", description="Specific agent if applicable")
    depends_on: list[str] = Field(default_factory=list, description="Step IDs this depends on")
    parallel: bool = Field(default=False, description="Can run in parallel with sibling steps")


class WorkflowBlueprint(BaseModel):
    """Blueprint for a workflow (sequence of steps)."""
    name: str = Field(description="Workflow name")
    description: str = Field(default="", description="What this workflow accomplishes")
    trigger: str = Field(default="manual", description="What triggers this workflow")
    steps: list[WorkflowStep] = Field(default_factory=list, description="Ordered steps")

    def validate_dependencies(self) -> None:
        """Validate that workflow steps have no circular dependencies.

        Raises ``CyclicDependencyError`` if a cycle is found.
        """
        from forge.runtime.planner import CyclicDependencyError, PlanStep, TaskPlan

        plan_steps = [
            PlanStep(id=s.id, description=s.description, depends_on=list(s.depends_on))
            for s in self.steps
        ]
        cycle = TaskPlan._detect_cycles(plan_steps)
        if cycle:
            raise CyclicDependencyError(cycle)


class APIEndpoint(BaseModel):
    """Blueprint for an API endpoint."""
    path: str = Field(description="API path (e.g., /api/tasks)")
    method: str = Field(default="POST", description="HTTP method")
    description: str = Field(default="", description="What this endpoint does")
    request_schema: dict[str, Any] = Field(default_factory=dict, description="Request body schema")
    response_schema: dict[str, Any] = Field(default_factory=dict, description="Response schema")
    handler_team: str = Field(default="", description="Team that handles this endpoint")


class AgencyBlueprint(BaseModel):
    """
    Complete blueprint for an AI agency.
    
    This is the master document that the Forge generates from a domain description.
    It contains everything needed to generate a deployable agency.
    """
    name: str = Field(description="Agency name")
    slug: str = Field(description="URL/directory-safe name")
    description: str = Field(description="What this agency does")
    domain: str = Field(description="The domain this agency serves")
    teams: list[TeamBlueprint] = Field(default_factory=list, description="All teams in the agency")
    workflows: list[WorkflowBlueprint] = Field(default_factory=list, description="Agency workflows")
    api_endpoints: list[APIEndpoint] = Field(default_factory=list, description="API endpoints to expose")
    shared_tools: list[ToolBlueprint] = Field(default_factory=list, description="Tools shared across all agents")
    environment_variables: dict[str, str] = Field(default_factory=dict, description="Required env vars")
    model: str = Field(default="gpt-4", description="Default LLM model")
    domain_knowledge: dict[str, Any] = Field(default_factory=dict, description="Domain-specific knowledge (policies, rules, vocabulary)")
    
    @property
    def all_agents(self) -> list[AgentBlueprint]:
        """Get all agents across all teams."""
        agents = []
        for team in self.teams:
            if team.lead:
                agents.append(team.lead)
            agents.extend(team.agents)
        return agents

    @property
    def all_tools(self) -> list[ToolBlueprint]:
        """Get all tools (shared + agent-specific)."""
        tools = list(self.shared_tools)
        for agent in self.all_agents:
            tools.extend(agent.tools)
        # Deduplicate by name
        seen = set()
        unique = []
        for t in tools:
            if t.name not in seen:
                seen.add(t.name)
                unique.append(t)
        return unique
