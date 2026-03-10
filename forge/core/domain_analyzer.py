"""Domain Analyzer — uses AI to analyze a domain and produce an agency blueprint."""

from __future__ import annotations

import logging
import re
from typing import Any

from forge.core.blueprint import (
    AgencyBlueprint,
    AgentBlueprint,
    AgentRole,
    APIEndpoint,
    TeamBlueprint,
    ToolBlueprint,
    WorkflowBlueprint,
    WorkflowStep,
)
from forge.core.llm import LLMClient

logger = logging.getLogger(__name__)


class DomainAnalyzer:
    """
    Analyzes a domain description using AI and produces a complete AgencyBlueprint.
    
    This is the core intelligence of the Forge — it uses a team of internal
    meta-agents to understand a domain and design an optimal agency structure.
    """

    def __init__(self, llm: LLMClient) -> None:
        self.llm = llm

    async def analyze(self, domain_description: str, model: str = "gpt-4") -> AgencyBlueprint:
        """
        Analyze a domain and produce a complete agency blueprint.
        
        Uses a multi-phase approach:
        1. Domain Analysis — understand the domain
        2. Role Design — identify required agent roles  
        3. Tool Design — determine what tools agents need
        4. Team Structure — organize agents into teams
        5. Workflow Design — define operational workflows
        6. API Design — define external interfaces
        """
        logger.info("Phase 1: Analyzing domain...")
        try:
            domain_analysis = await self._analyze_domain(domain_description)
        except Exception as e:
            logger.warning(f"Phase 1 (Domain Analysis) failed: {e}, using default")
            domain_analysis = {"agency_name": "AI Agency", "description": domain_description[:200], "env_vars": {}}

        logger.info("Phase 2: Designing agent roles...")
        try:
            agents = await self._design_agents(domain_description, domain_analysis)
        except Exception as e:
            logger.warning(f"Phase 2 (Role Design) failed: {e}, using default")
            agents = []

        logger.info("Phase 3: Designing tools...")
        try:
            agents_with_tools, shared_tools = await self._design_tools(domain_description, domain_analysis, agents)
        except Exception as e:
            logger.warning(f"Phase 3 (Tool Design) failed: {e}, using default")
            agents_with_tools, shared_tools = agents, []

        logger.info("Phase 4: Organizing teams...")
        try:
            teams = await self._organize_teams(domain_description, domain_analysis, agents_with_tools)
        except Exception as e:
            logger.warning(f"Phase 4 (Team Organization) failed: {e}, using default")
            from forge.core.blueprint import TeamBlueprint
            teams = [TeamBlueprint(name="Main Team", description="Primary team", agents=agents_with_tools, lead=agents_with_tools[0] if agents_with_tools else None)]

        logger.info("Phase 5: Designing workflows...")
        try:
            workflows = await self._design_workflows(domain_description, domain_analysis, teams)
        except Exception as e:
            logger.warning(f"Phase 5 (Workflow Design) failed: {e}, using default")
            workflows = []

        logger.info("Phase 6: Designing API...")
        try:
            api_endpoints = await self._design_api(domain_description, domain_analysis, teams)
        except Exception as e:
            logger.warning(f"Phase 6 (API Design) failed: {e}, using default")
            api_endpoints = []

        # Build the final blueprint
        slug = self._make_slug(domain_analysis.get("agency_name", "ai-agency"))

        blueprint = AgencyBlueprint(
            name=domain_analysis.get("agency_name", "AI Agency"),
            slug=slug,
            description=domain_analysis.get("description", domain_description[:200]),
            domain=domain_description[:500],
            teams=teams,
            workflows=workflows,
            api_endpoints=api_endpoints,
            shared_tools=shared_tools,
            environment_variables=domain_analysis.get("env_vars", {}),
            model=model,
        )

        logger.info(
            f"Blueprint complete: {blueprint.name} — "
            f"{len(blueprint.teams)} teams, "
            f"{len(blueprint.all_agents)} agents, "
            f"{len(blueprint.all_tools)} tools"
        )
        return blueprint

    async def _analyze_domain(self, domain_description: str) -> dict[str, Any]:
        """Phase 1: High-level domain analysis."""
        from pydantic import BaseModel, Field

        class DomainAnalysis(BaseModel):
            agency_name: str = Field(description="Short, professional name for the agency")
            description: str = Field(description="One-paragraph description of what the agency does")
            key_functions: list[str] = Field(description="Core functions the agency must perform")
            stakeholders: list[str] = Field(description="Who interacts with this agency")
            integrations: list[str] = Field(description="External systems to integrate with")
            env_vars: dict[str, str] = Field(default_factory=dict, description="Required environment variables with defaults")
            complexity: str = Field(description="low, medium, or high")
            revenue_streams: list[str] = Field(default_factory=list, description="How this agency can generate revenue (direct + indirect)")
            target_market_size: str = Field(default="", description="Estimated addressable market size")
            competitive_advantages: list[str] = Field(default_factory=list, description="What makes this AI agency better than human alternatives")
            growth_levers: list[str] = Field(default_factory=list, description="Mechanisms for compounding growth")
            monetization_strategy: str = Field(default="", description="Primary monetization model (SaaS, usage-based, per-task, etc.)")

        messages = [
            {"role": "system", "content": (
                "You are a domain analyst AND ruthless business strategist specializing in AI agency design. "
                "Your goal is NOT just to understand the domain — it's to find the MOST AMBITIOUS, "
                "MOST PROFITABLE interpretation of the domain that will generate maximum revenue.\n\n"
                "Think like an entrepreneur who wants to build a billion-dollar business:\n"
                "- Don't just automate tasks — find ways to GENERATE revenue\n"
                "- Don't just support customers — find ways to GROW the customer base\n"
                "- Don't just answer questions — find ways to UPSELL, CROSS-SELL, and RETAIN\n"
                "- Identify every possible revenue stream, not just the obvious ones\n"
                "- Think about what would make someone pay $10K-$50K/month for this agency\n"
                "- Consider: what does a human team doing this cost? Your agency should replace $200K+ in salaries\n\n"
                "Be specific, practical, and AMBITIOUS."
            )},
            {"role": "user", "content": (
                f"Analyze this domain for building a REVENUE-MAXIMIZING AI agency:\n\n{domain_description}\n\n"
                f"Identify:\n"
                f"- A compelling agency name that conveys premium value\n"
                f"- Core functions (include revenue-generating functions, not just operational ones)\n"
                f"- Stakeholders and target customers willing to PAY for this\n"
                f"- Integrations needed for both operations AND revenue tracking\n"
                f"- Revenue streams: how does this agency make money? (list at least 3)\n"
                f"- Target market size: how big is the opportunity?\n"
                f"- Competitive advantages: why is an AI agency better than hiring humans?\n"
                f"- Growth levers: what creates compounding growth?\n"
                f"- Monetization strategy: SaaS subscription, usage-based, per-task, or hybrid?\n"
                f"- Environment variables needed\n\n"
                f"Push for the MOST AMBITIOUS interpretation. If someone says 'customer support agency', "
                f"think: support + sales + upselling + retention + analytics + growth."
            )},
        ]

        result = await self.llm.complete_structured(messages, DomainAnalysis)
        return result.model_dump()

    async def _design_agents(self, domain: str, analysis: dict) -> list[AgentBlueprint]:
        """Phase 2: Design individual agent roles."""
        from pydantic import BaseModel, Field

        class AgentDesign(BaseModel):
            name: str
            role: str
            title: str
            system_prompt: str
            capabilities: list[str]
            temperature: float = 0.7
            can_spawn_sub_agents: bool = False

        class AgentDesigns(BaseModel):
            agents: list[AgentDesign]

        messages = [
            {"role": "system", "content": (
                "You are an AI agent architect designing agents for a REVENUE-MAXIMIZING agency. "
                "Each agent should have a clear role, detailed system prompt, and specific capabilities.\n\n"
                "CRITICAL DESIGN PRINCIPLES:\n"
                "- Every agent should have a revenue angle — even support agents should identify upsell opportunities\n"
                "- Include agents that DIRECTLY drive revenue (sales, growth, retention), not just operational agents\n"
                "- System prompts must be detailed (3+ paragraphs) with personality, expertise, KPIs, and constraints\n"
                "- Include a mix of managers, specialists, and support agents\n"
                "- Design agents that make the agency worth $10K+/month to customers\n"
                "- Think about what would make this agency IRREPLACEABLE\n\n"
                "Use roles: manager, specialist, researcher, writer, reviewer, coordinator, analyst, support."
                "\n\nCRITICAL TOOL INSTRUCTIONS FOR SYSTEM PROMPTS:\n"
                "Every agent's system prompt MUST include these instructions:\n"
                '1. "You have access to these real tools: run_command (execute shell commands), read_write_file (create/read/edit files), http_request (call APIs), query_database (SQL queries), send_email, send_webhook."\n'
                '2. "When asked to accomplish a task, USE these tools to actually DO it. Create real files. Run real commands. Don\'t just describe what you would do — DO it."\n'
                '3. "Follow the pattern: think about what needs to be done, then use your tools to do each step, then verify the result."\n'
                '4. For coding agents: "Write code using read_write_file to create the actual files, then use run_command to install dependencies, build, and test."\n'
                '5. For support agents: "Use query_database to look up real customer data, use send_email to actually send responses."'
            )},
            {"role": "user", "content": (
                f"Domain: {domain}\n\n"
                f"Analysis: {analysis}\n\n"
                f"Design all AI agents needed for a REVENUE-MAXIMIZING agency.\n"
                f"- Include at least one manager and multiple specialists\n"
                f"- Include revenue-focused agents (not just operational ones)\n"
                f"- Every agent should have KPIs tied to business outcomes\n"
                f"- Each agent needs a detailed system prompt (3+ paragraphs)\n"
                f"- Think: what agents would a $10M/year business in this domain need?"
            )},
        ]

        result = await self.llm.complete_structured(messages, AgentDesigns)

        blueprints = []
        role_map = {r.value: r for r in AgentRole}
        for a in result.agents:
            role = role_map.get(a.role, AgentRole.CUSTOM)
            blueprints.append(AgentBlueprint(
                name=a.name,
                role=role,
                title=a.title,
                system_prompt=a.system_prompt,
                capabilities=a.capabilities,
                temperature=a.temperature,
                can_spawn_sub_agents=a.can_spawn_sub_agents,
            ))
        return blueprints

    async def _design_tools(
        self, domain: str, analysis: dict, agents: list[AgentBlueprint]
    ) -> tuple[list[AgentBlueprint], list[ToolBlueprint]]:
        """Phase 3: Design tools for agents."""
        from pydantic import BaseModel, Field

        class ToolDesign(BaseModel):
            name: str
            description: str
            parameters: list[dict[str, Any]] = []
            implementation_hint: str = ""
            assigned_to: list[str] = Field(default_factory=list, description="Agent names that use this tool, or empty for shared")

        class ToolDesigns(BaseModel):
            tools: list[ToolDesign]

        agent_summary = "\n".join(f"- {a.name}: {a.title}" for a in agents)
        functions = "\n".join(f"- {f}" for f in analysis.get("key_functions", []))
        integrations = "\n".join(f"- {i}" for i in analysis.get("integrations", []))

        messages = [
            {"role": "system", "content": (
                "You are a tool designer for AI agents. Design the tools these agents need. "
                "Tools are Python async functions that agents can call. "
                "Each tool has a name (snake_case), description, parameters (list of {name, type, description, required}), "
                "and implementation_hint. "
                "Assign tools to specific agents, or leave assigned_to empty for shared tools. "
                "Parameter types: string, integer, number, boolean, array, object."
            )},
            {"role": "user", "content": (
                f"Domain: {domain}\n\n"
                f"Key functions:\n{functions}\n\n"
                f"Integrations:\n{integrations}\n\n"
                f"Agents:\n{agent_summary}\n\n"
                f"Design all tools needed. Create practical tools that cover the domain's operations."
            )},
        ]

        result = await self.llm.complete_structured(messages, ToolDesigns)

        # Separate shared vs agent-specific tools
        shared_tools = []
        agent_tools: dict[str, list[ToolBlueprint]] = {}

        for t in result.tools:
            tool_bp = ToolBlueprint(
                name=t.name,
                description=t.description,
                parameters=t.parameters,
                implementation_hint=t.implementation_hint,
            )
            if not t.assigned_to:
                shared_tools.append(tool_bp)
            else:
                for agent_name in t.assigned_to:
                    agent_tools.setdefault(agent_name, []).append(tool_bp)

        # Attach tools to agents
        updated_agents = []
        for agent in agents:
            agent_copy = agent.model_copy()
            if agent.name in agent_tools:
                agent_copy.tools = agent_tools[agent.name]
            updated_agents.append(agent_copy)

        return updated_agents, shared_tools

    async def _organize_teams(
        self, domain: str, analysis: dict, agents: list[AgentBlueprint]
    ) -> list[TeamBlueprint]:
        """Phase 4: Organize agents into teams."""
        from pydantic import BaseModel, Field

        class TeamDesign(BaseModel):
            name: str
            description: str
            lead_agent: str = Field(description="Name of the team lead agent")
            member_agents: list[str] = Field(description="Names of team member agents")

        class TeamDesigns(BaseModel):
            teams: list[TeamDesign]

        agent_summary = "\n".join(
            f"- {a.name} ({a.role.value}): {a.title} — capabilities: {', '.join(a.capabilities[:3])}"
            for a in agents
        )

        messages = [
            {"role": "system", "content": (
                "You are an organizational architect. Organize agents into effective teams. "
                "Each team has a lead (typically a manager or coordinator) and member agents. "
                "Every agent must be assigned to exactly one team. "
                "Teams should be organized by function/responsibility."
            )},
            {"role": "user", "content": (
                f"Domain: {domain}\n\n"
                f"Agents:\n{agent_summary}\n\n"
                f"Organize these agents into teams. Each team needs a lead and members."
            )},
        ]

        result = await self.llm.complete_structured(messages, TeamDesigns)

        # Build agent lookup
        agent_map = {a.name: a for a in agents}

        teams = []
        assigned = set()
        for td in result.teams:
            lead = agent_map.get(td.lead_agent)
            members = [agent_map[name] for name in td.member_agents if name in agent_map]

            if lead:
                assigned.add(td.lead_agent)
            for m in members:
                assigned.add(m.name)

            teams.append(TeamBlueprint(
                name=td.name,
                description=td.description,
                lead=lead,
                agents=members,
            ))

        # Catch any unassigned agents — put in a "General" team
        unassigned = [a for a in agents if a.name not in assigned]
        if unassigned:
            teams.append(TeamBlueprint(
                name="General",
                description="General-purpose agents",
                agents=unassigned,
            ))

        return teams

    async def _design_workflows(
        self, domain: str, analysis: dict, teams: list[TeamBlueprint]
    ) -> list[WorkflowBlueprint]:
        """Phase 5: Design workflows."""
        from pydantic import BaseModel, Field

        class WfStep(BaseModel):
            id: str
            description: str
            assigned_team: str = ""
            depends_on: list[str] = []
            parallel: bool = False

        class WfDesign(BaseModel):
            name: str
            description: str
            trigger: str = "manual"
            steps: list[WfStep]

        class WfDesigns(BaseModel):
            workflows: list[WfDesign]

        team_summary = "\n".join(f"- {t.name}: {t.description}" for t in teams)
        functions = "\n".join(f"- {f}" for f in analysis.get("key_functions", []))

        messages = [
            {"role": "system", "content": (
                "You are a workflow designer. Design operational workflows for an AI agency. "
                "Each workflow has steps that can depend on each other and run in parallel where possible."
            )},
            {"role": "user", "content": (
                f"Domain: {domain}\n\nKey functions:\n{functions}\n\nTeams:\n{team_summary}\n\n"
                f"Design 2-4 key workflows covering the main operations."
            )},
        ]

        result = await self.llm.complete_structured(messages, WfDesigns)

        workflows = []
        for wf in result.workflows:
            steps = [
                WorkflowStep(
                    id=s.id,
                    description=s.description,
                    assigned_team=s.assigned_team,
                    depends_on=s.depends_on,
                    parallel=s.parallel,
                )
                for s in wf.steps
            ]
            workflows.append(WorkflowBlueprint(
                name=wf.name,
                description=wf.description,
                trigger=wf.trigger,
                steps=steps,
            ))
        return workflows

    async def _design_api(
        self, domain: str, analysis: dict, teams: list[TeamBlueprint]
    ) -> list[APIEndpoint]:
        """Phase 6: Design API endpoints."""
        from pydantic import BaseModel, Field

        class EndpointDesign(BaseModel):
            path: str
            method: str = "POST"
            description: str
            handler_team: str = ""

        class APIDesign(BaseModel):
            endpoints: list[EndpointDesign]

        team_names = [t.name for t in teams]
        functions = analysis.get("key_functions", [])

        messages = [
            {"role": "system", "content": (
                "You are an API designer. Design REST API endpoints for an AI agency. "
                "Include practical endpoints for the domain's key operations. "
                "Each endpoint routes to a specific team."
            )},
            {"role": "user", "content": (
                f"Domain: {domain}\n\nKey functions: {functions}\n\nTeams: {team_names}\n\n"
                f"Design 3-6 API endpoints. Always include /api/task (POST) for general tasks."
            )},
        ]

        result = await self.llm.complete_structured(messages, APIDesign)
        return [
            APIEndpoint(
                path=ep.path,
                method=ep.method,
                description=ep.description,
                handler_team=ep.handler_team,
            )
            for ep in result.endpoints
        ]

    @staticmethod
    def _make_slug(name: str) -> str:
        """Convert a name to a URL/directory-safe slug."""
        slug = name.lower().strip()
        slug = re.sub(r'[^a-z0-9\s-]', '', slug)
        slug = re.sub(r'[\s]+', '-', slug)
        slug = re.sub(r'-+', '-', slug)
        return slug.strip('-')
