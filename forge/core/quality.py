"""Quality standards framework for evaluating agency blueprints."""

from __future__ import annotations

import logging
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from forge.core.blueprint import AgencyBlueprint

logger = logging.getLogger(__name__)


class QualityDimension(str, Enum):
    """Dimensions along which blueprint quality is measured."""
    ROLE_COVERAGE = "role_coverage"           # Do agents cover all domain functions?
    AGENT_DEPTH = "agent_depth"               # Are agent prompts detailed and specific?
    TOOLING = "tooling"                       # Do agents have the tools they need?
    TEAM_ARCHITECTURE = "team_architecture"   # Are teams well-organized with clear leads?
    WORKFLOW_COMPLETENESS = "workflow_completeness"  # Do workflows cover key operations?
    SCALABILITY = "scalability"               # Can the agency handle dynamic workloads?
    RESILIENCE = "resilience"                 # Does the agency handle errors and edge cases?
    API_DESIGN = "api_design"                 # Are API endpoints practical and complete?
    SELF_IMPROVEMENT = "self_improvement"     # Does the agency have feedback/improvement loops?
    UNIVERSALS = "universals"                 # Are mandatory archetypes (QA, intake, etc.) present?
    # Business Ambition Dimensions
    REVENUE_POTENTIAL = "revenue_potential"       # Does this agency generate or save money?
    CUSTOMER_ACQUISITION = "customer_acquisition" # Can it attract and convert customers?
    COMPETITIVE_ADVANTAGE = "competitive_advantage" # What makes this better than humans/competitors?
    MONETIZATION = "monetization"                 # Is there a clear path to revenue?
    GROWTH_ENGINE = "growth_engine"               # Does it compound and scale revenue over time?


class DimensionScore(BaseModel):
    """Score for a single quality dimension."""
    dimension: QualityDimension
    score: float = Field(ge=0.0, le=1.0, description="Score from 0 to 1")
    weight: float = Field(default=1.0, ge=0.0, description="Weight for this dimension")
    findings: list[str] = Field(default_factory=list, description="Specific findings")
    suggestions: list[str] = Field(default_factory=list, description="Improvement suggestions")


class QualityScore(BaseModel):
    """Complete quality assessment of a blueprint."""
    dimension_scores: list[DimensionScore] = Field(default_factory=list)
    overall_score: float = Field(ge=0.0, le=1.0, description="Weighted average score")
    passed: bool = Field(default=False, description="Whether the blueprint meets minimum standards")
    threshold: float = Field(default=0.8, description="Minimum passing score")
    critical_issues: list[str] = Field(default_factory=list, description="Issues that must be fixed")
    recommendations: list[str] = Field(default_factory=list, description="Nice-to-have improvements")
    iteration: int = Field(default=0, description="Which refinement iteration this score is from")


class QualityRubric:
    """
    Defines the quality standards for agency blueprints.
    
    Each dimension has criteria, weights, and evaluation logic.
    The rubric is domain-agnostic — it evaluates structural quality
    regardless of what business domain the agency serves.
    """

    DEFAULT_WEIGHTS = {
        QualityDimension.ROLE_COVERAGE: 1.5,
        QualityDimension.AGENT_DEPTH: 1.2,
        QualityDimension.TOOLING: 1.3,
        QualityDimension.TEAM_ARCHITECTURE: 1.0,
        QualityDimension.WORKFLOW_COMPLETENESS: 1.0,
        QualityDimension.SCALABILITY: 0.8,
        QualityDimension.RESILIENCE: 0.9,
        QualityDimension.API_DESIGN: 0.7,
        QualityDimension.SELF_IMPROVEMENT: 1.1,
        QualityDimension.UNIVERSALS: 1.4,
        # Business dimensions — opt-in, weighted equally (not inflated)
        QualityDimension.REVENUE_POTENTIAL: 1.0,
        QualityDimension.CUSTOMER_ACQUISITION: 1.0,
        QualityDimension.COMPETITIVE_ADVANTAGE: 1.5,
        QualityDimension.MONETIZATION: 1.0,
        QualityDimension.GROWTH_ENGINE: 1.0,
    }

    # Core archetypes are always valuable for any agency
    MANDATORY_ARCHETYPE_ROLES = [
        "qa_reviewer",
        "intake_coordinator",
        "self_improvement",
        "analytics",
    ]

    # Business archetypes are opt-in — not every domain needs revenue agents
    OPTIONAL_BUSINESS_ARCHETYPES = [
        "growth",
        "customer_success",
        "lead_generation",
        "revenue",
    ]

    def __init__(
        self,
        threshold: float = 0.8,
        weights: dict[QualityDimension, float] | None = None,
        include_business_archetypes: bool = False,
    ):
        self.threshold = threshold
        self.weights = weights or self.DEFAULT_WEIGHTS
        self.include_business_archetypes = include_business_archetypes


class BlueprintEvaluator:
    """
    Evaluates an AgencyBlueprint against quality standards.
    
    Uses deterministic structural checks (not LLM-based) to provide
    fast, consistent scoring. The LLM-based CriticAgent provides
    deeper semantic review on top of this.
    """

    def __init__(self, rubric: QualityRubric | None = None):
        self.rubric = rubric or QualityRubric()

    def evaluate(self, blueprint: AgencyBlueprint, iteration: int = 0) -> QualityScore:
        """Evaluate a blueprint and produce a quality score."""
        scores = []

        scores.append(self._eval_role_coverage(blueprint))
        scores.append(self._eval_agent_depth(blueprint))
        scores.append(self._eval_tooling(blueprint))
        scores.append(self._eval_team_architecture(blueprint))
        scores.append(self._eval_workflow_completeness(blueprint))
        scores.append(self._eval_scalability(blueprint))
        scores.append(self._eval_resilience(blueprint))
        scores.append(self._eval_api_design(blueprint))
        scores.append(self._eval_self_improvement(blueprint))
        scores.append(self._eval_universals(blueprint))
        scores.append(self._eval_revenue_potential(blueprint))
        scores.append(self._eval_customer_acquisition(blueprint))
        scores.append(self._eval_competitive_advantage(blueprint))
        scores.append(self._eval_monetization(blueprint))
        scores.append(self._eval_growth_engine(blueprint))

        # Calculate weighted average
        total_weight = sum(s.weight for s in scores)
        weighted_sum = sum(s.score * s.weight for s in scores)
        overall = weighted_sum / total_weight if total_weight > 0 else 0.0

        # Collect critical issues and recommendations
        critical = []
        recommendations = []
        for s in scores:
            if s.score < 0.5:
                critical.extend(s.suggestions)
            elif s.score < 0.8:
                recommendations.extend(s.suggestions)

        return QualityScore(
            dimension_scores=scores,
            overall_score=round(overall, 3),
            passed=overall >= self.rubric.threshold,
            threshold=self.rubric.threshold,
            critical_issues=critical,
            recommendations=recommendations,
            iteration=iteration,
        )

    def _eval_role_coverage(self, bp: AgencyBlueprint) -> DimensionScore:
        """Do agents cover the domain's needs?"""
        agents = bp.all_agents
        findings = []
        score = 1.0

        if len(agents) < 3:
            score -= 0.4
            findings.append(f"Only {len(agents)} agents — most domains need at least 5")
        elif len(agents) < 5:
            score -= 0.15
            findings.append(f"{len(agents)} agents — consider if more specialization is needed")

        # Check for role diversity
        roles = set(a.role.value for a in agents)
        if len(roles) < 3:
            score -= 0.3
            findings.append(f"Only {len(roles)} distinct roles — needs more diversity")

        # Check for manager/coordinator
        has_manager = any(a.role.value in ("manager", "coordinator") for a in agents)
        if not has_manager:
            score -= 0.2
            findings.append("No manager or coordinator agent found")

        suggestions = []
        if score < 0.8:
            suggestions.append("Add more specialized agents to cover domain functions")
            suggestions.append("Ensure at least one manager/coordinator agent exists")

        return DimensionScore(
            dimension=QualityDimension.ROLE_COVERAGE,
            score=max(0.0, score),
            weight=self.rubric.weights[QualityDimension.ROLE_COVERAGE],
            findings=findings,
            suggestions=suggestions,
        )

    def _eval_agent_depth(self, bp: AgencyBlueprint) -> DimensionScore:
        """Are agent system prompts detailed and specific?"""
        import re as _re

        agents = bp.all_agents
        findings = []
        agent_scores: list[float] = []

        role_patterns = _re.compile(
            r"\b(you are|your role|act as|responsible for|specialist in|expert in)\b", _re.IGNORECASE,
        )
        constraint_patterns = _re.compile(
            r"\b(must|never|always|do not|ensure|require|limit|only|forbidden|prohibited)\b", _re.IGNORECASE,
        )
        action_patterns = _re.compile(
            r"\b(analyze|evaluate|generate|create|review|validate|monitor|report|execute|deliver|optimize)\b",
            _re.IGNORECASE,
        )
        conditional_patterns = _re.compile(
            r"\b(if|when|unless|otherwise|in case|provided that|depending on|should .+ then)\b", _re.IGNORECASE,
        )
        domain_patterns = _re.compile(
            r"\b(api|database|workflow|pipeline|metric|compliance|security|integration|deployment|schema)\b",
            _re.IGNORECASE,
        )

        weak_agents: list[str] = []
        for agent in agents:
            prompt = agent.system_prompt
            has_role = 0.2 if role_patterns.search(prompt) else 0.0
            has_constraints = 0.2 if constraint_patterns.search(prompt) else 0.0
            has_actions = 0.2 if len(action_patterns.findall(prompt)) >= 2 else (0.1 if action_patterns.search(prompt) else 0.0)
            has_conditionals = 0.2 if conditional_patterns.search(prompt) else 0.0
            has_domain = 0.2 if domain_patterns.search(prompt) else 0.0
            agent_score = has_role + has_constraints + has_actions + has_conditionals + has_domain
            agent_scores.append(agent_score)
            if agent_score < 0.4:
                weak_agents.append(agent.name)

        avg_depth = sum(agent_scores) / max(len(agent_scores), 1)
        score = avg_depth

        if weak_agents:
            findings.append(f"Weak prompts (lack specifics): {', '.join(weak_agents[:5])}")

        # Check for capabilities
        no_caps = [a.name for a in agents if not a.capabilities]
        if no_caps:
            score -= 0.1 * min(len(no_caps) / max(len(agents), 1), 1.0)
            findings.append(f"Missing capabilities list: {', '.join(no_caps[:3])}")

        if not findings:
            findings.append("All agent prompts have good specificity")

        suggestions = []
        if score < 0.8:
            suggestions.append("Add role definitions, constraints, and conditional logic to agent prompts")
            suggestions.append("Use domain-specific terminology and action verbs in prompts")
            suggestions.append("Add explicit capabilities lists to all agents")

        return DimensionScore(
            dimension=QualityDimension.AGENT_DEPTH,
            score=max(0.0, min(1.0, score)),
            weight=self.rubric.weights[QualityDimension.AGENT_DEPTH],
            findings=findings,
            suggestions=suggestions,
        )

    def _eval_tooling(self, bp: AgencyBlueprint) -> DimensionScore:
        """Do agents have the tools they need?"""
        agents = bp.all_agents
        all_tools = bp.all_tools
        findings = []
        score = 1.0

        if not all_tools:
            score = 0.2
            findings.append("No tools defined — agents have no capabilities beyond conversation")
        elif len(all_tools) < 3:
            score -= 0.3
            findings.append(f"Only {len(all_tools)} tools — most agencies need more")

        # Check agents without tools (excluding managers who may delegate)
        toolless = [a for a in agents if not a.tools and a.role.value not in ("manager", "coordinator")]
        if toolless and len(toolless) > len(agents) * 0.5:
            score -= 0.25
            findings.append(f"{len(toolless)} specialist agents have no tools")

        # Check tool parameter quality
        paramless_tools = [t for t in all_tools if not t.parameters]
        if paramless_tools:
            score -= 0.1
            findings.append(f"{len(paramless_tools)} tools have no parameters defined")

        suggestions = []
        if score < 0.8:
            suggestions.append("Add domain-specific tools to specialist agents")
            suggestions.append("Ensure all tools have well-defined parameters")

        return DimensionScore(
            dimension=QualityDimension.TOOLING,
            score=max(0.0, score),
            weight=self.rubric.weights[QualityDimension.TOOLING],
            findings=findings,
            suggestions=suggestions,
        )

    def _eval_team_architecture(self, bp: AgencyBlueprint) -> DimensionScore:
        """Are teams well-organized?"""
        findings = []
        score = 1.0

        if not bp.teams:
            return DimensionScore(
                dimension=QualityDimension.TEAM_ARCHITECTURE,
                score=0.0,
                weight=self.rubric.weights[QualityDimension.TEAM_ARCHITECTURE],
                findings=["No teams defined"],
                suggestions=["Organize agents into functional teams"],
            )

        # Check each team has a lead
        leaderless = [t for t in bp.teams if not t.lead]
        if leaderless:
            score -= 0.2 * (len(leaderless) / len(bp.teams))
            findings.append(f"Teams without leads: {', '.join(t.name for t in leaderless)}")

        # Check for empty teams
        empty = [t for t in bp.teams if not t.agents and not t.lead]
        if empty:
            score -= 0.3
            findings.append(f"Empty teams: {', '.join(t.name for t in empty)}")

        # Check team sizes
        for team in bp.teams:
            member_count = len(team.agents)
            if member_count > 8:
                score -= 0.05
                findings.append(f"Team '{team.name}' has {member_count} members — consider splitting")

        suggestions = []
        if score < 0.8:
            suggestions.append("Ensure every team has a designated lead agent")
            suggestions.append("Balance team sizes (3-6 agents per team is optimal)")

        return DimensionScore(
            dimension=QualityDimension.TEAM_ARCHITECTURE,
            score=max(0.0, score),
            weight=self.rubric.weights[QualityDimension.TEAM_ARCHITECTURE],
            findings=findings,
            suggestions=suggestions,
        )

    def _eval_workflow_completeness(self, bp: AgencyBlueprint) -> DimensionScore:
        """Do workflows cover key operations?"""
        findings = []
        score = 1.0

        if not bp.workflows:
            score = 0.3
            findings.append("No workflows defined")
        elif len(bp.workflows) < 2:
            score -= 0.2
            findings.append("Only 1 workflow — most agencies need 2-4")

        # Check workflow steps
        for wf in bp.workflows:
            if not wf.steps:
                score -= 0.15
                findings.append(f"Workflow '{wf.name}' has no steps")
            elif len(wf.steps) < 2:
                score -= 0.05
                findings.append(f"Workflow '{wf.name}' has only {len(wf.steps)} step")

        suggestions = []
        if score < 0.8:
            suggestions.append("Add more workflows covering the domain's key operations")
            suggestions.append("Ensure each workflow has 2+ well-defined steps")

        return DimensionScore(
            dimension=QualityDimension.WORKFLOW_COMPLETENESS,
            score=max(0.0, score),
            weight=self.rubric.weights[QualityDimension.WORKFLOW_COMPLETENESS],
            findings=findings,
            suggestions=suggestions,
        )

    def _eval_scalability(self, bp: AgencyBlueprint) -> DimensionScore:
        """Can the agency handle dynamic workloads?"""
        findings = []
        score = 1.0

        # Check for dynamic scaling
        scalable_teams = [t for t in bp.teams if t.allow_dynamic_scaling]
        if not scalable_teams:
            score -= 0.3
            findings.append("No teams support dynamic agent scaling")
        
        # Check for agents that can spawn sub-agents
        spawners = [a for a in bp.all_agents if a.can_spawn_sub_agents]
        if not spawners:
            score -= 0.2
            findings.append("No agents can spawn sub-agents for delegation")

        suggestions = []
        if score < 0.8:
            suggestions.append("Enable dynamic scaling on teams for unlimited agent spawning")
            suggestions.append("Allow key agents (managers) to spawn sub-agents")

        return DimensionScore(
            dimension=QualityDimension.SCALABILITY,
            score=max(0.0, score),
            weight=self.rubric.weights[QualityDimension.SCALABILITY],
            findings=findings,
            suggestions=suggestions,
        )

    def _eval_resilience(self, bp: AgencyBlueprint) -> DimensionScore:
        """Does the agency handle errors and edge cases?"""
        import re as _re

        findings = []
        score = 0.0

        # 1. Check for error handling patterns in agent prompts (structural, not keyword)
        error_handling_pattern = _re.compile(
            r"\b(try|except|catch|handle error|on failure|error handling|gracefully)\b", _re.IGNORECASE,
        )
        agents_with_handling = [a for a in bp.all_agents if error_handling_pattern.search(a.system_prompt)]
        handling_ratio = len(agents_with_handling) / max(len(bp.all_agents), 1)
        if handling_ratio >= 0.3:
            score += 0.25
            findings.append(f"{len(agents_with_handling)} agents have error handling patterns")
        elif agents_with_handling:
            score += 0.1

        # 2. Check for escalation paths in workflows
        escalation_pattern = _re.compile(r"\b(escalat|notify|alert|handoff|hand off|fallback)\b", _re.IGNORECASE)
        escalation_wfs = [
            wf for wf in bp.workflows
            if any(escalation_pattern.search(s.description) for s in wf.steps)
        ]
        if escalation_wfs:
            score += 0.25
            findings.append(f"Escalation paths in {len(escalation_wfs)} workflow(s)")
        else:
            findings.append("No escalation paths defined in workflows")

        # 3. Check for fallback agents in teams
        fallback_agents = [
            a for a in bp.all_agents
            if _re.search(r"\b(fallback|backup|failover)\b", a.name.lower() + " " + a.system_prompt.lower()[:200])
        ]
        if fallback_agents:
            score += 0.25
            findings.append(f"Fallback agents: {', '.join(a.name for a in fallback_agents)}")

        # 4. Check for retry configuration in tools
        retry_tools = [
            t for t in bp.all_tools
            if any(p.get("name", "").lower() in ("retry", "retries", "max_retries", "retry_count", "timeout")
                   for p in t.parameters)
        ]
        if retry_tools:
            score += 0.25
            findings.append(f"Retry config in {len(retry_tools)} tool(s)")

        # Baseline: having agents at all provides some resilience
        if bp.all_agents and score == 0.0:
            score = 0.3

        suggestions = []
        if score < 0.8:
            suggestions.append("Add error handling instructions to agent system prompts")
            suggestions.append("Define escalation steps in workflows for failure scenarios")
            suggestions.append("Add fallback agents for critical functions")
            suggestions.append("Include retry/timeout parameters in tool definitions")

        return DimensionScore(
            dimension=QualityDimension.RESILIENCE,
            score=max(0.0, min(1.0, score)),
            weight=self.rubric.weights[QualityDimension.RESILIENCE],
            findings=findings,
            suggestions=suggestions,
        )

    def _eval_api_design(self, bp: AgencyBlueprint) -> DimensionScore:
        """Are API endpoints practical?"""
        findings = []
        score = 1.0

        if not bp.api_endpoints:
            score = 0.4
            findings.append("No API endpoints defined")
        elif len(bp.api_endpoints) < 2:
            score -= 0.2
            findings.append("Only 1 API endpoint — most agencies need more")

        # Check for task endpoint
        has_task = any("/task" in ep.path for ep in bp.api_endpoints)
        if not has_task:
            score -= 0.15
            findings.append("No general /api/task endpoint for ad-hoc tasks")

        suggestions = []
        if score < 0.8:
            suggestions.append("Add a general /api/task endpoint for arbitrary task execution")
            suggestions.append("Add domain-specific endpoints for key operations")

        return DimensionScore(
            dimension=QualityDimension.API_DESIGN,
            score=max(0.0, score),
            weight=self.rubric.weights[QualityDimension.API_DESIGN],
            findings=findings,
            suggestions=suggestions,
        )

    def _eval_self_improvement(self, bp: AgencyBlueprint) -> DimensionScore:
        """Does the agency have feedback and improvement loops?"""
        findings = []
        score = 0.5  # Start low — must prove self-improvement exists

        # Check for QA/review agents
        qa_terms = ("qa", "quality", "review", "critic", "audit", "validation")
        qa_agents = [a for a in bp.all_agents if any(t in a.name.lower() or t in a.role.value.lower() for t in qa_terms)]
        if qa_agents:
            score += 0.2
            findings.append(f"QA/review agents found: {', '.join(a.name for a in qa_agents)}")
        else:
            findings.append("No QA or review agents found")

        # Check for improvement/learning agents
        improve_terms = ("improv", "learn", "adapt", "optim", "feedback", "monitor", "analyt")
        improve_agents = [a for a in bp.all_agents if any(t in a.name.lower() or t in a.system_prompt.lower()[:200] for t in improve_terms)]
        if improve_agents:
            score += 0.2
            findings.append(f"Self-improvement capable agents: {', '.join(a.name for a in improve_agents)}")
        else:
            findings.append("No self-improvement or analytics agents found")

        # Check for feedback in workflows
        feedback_wfs = [wf for wf in bp.workflows if any(
            "review" in s.description.lower() or "feedback" in s.description.lower() or "quality" in s.description.lower()
            for s in wf.steps
        )]
        if feedback_wfs:
            score += 0.1

        suggestions = []
        if score < 0.8:
            suggestions.append("Add a QA Reviewer agent that validates all outputs before delivery")
            suggestions.append("Add a Self-Improvement agent that monitors performance and suggests improvements")
            suggestions.append("Add feedback collection steps to workflows")

        return DimensionScore(
            dimension=QualityDimension.SELF_IMPROVEMENT,
            score=max(0.0, min(1.0, score)),
            weight=self.rubric.weights[QualityDimension.SELF_IMPROVEMENT],
            findings=findings,
            suggestions=suggestions,
        )

    def _eval_universals(self, bp: AgencyBlueprint) -> DimensionScore:
        """Are mandatory universal archetypes present?"""
        findings = []
        score = 1.0

        agents_lower = {a.name.lower().replace(" ", "_"): a for a in bp.all_agents}

        def _agent_matches_archetype(archetype: str) -> bool:
            """Check if any agent matches an archetype by name or role in prompt."""
            archetype_terms = archetype.replace("_", " ").split()
            for name, agent in agents_lower.items():
                prompt_start = agent.system_prompt.lower()[:200]
                role_val = agent.role.value.lower()
                if any(t in name or t in role_val or t in prompt_start for t in archetype_terms):
                    return True
            return False

        # Check core (mandatory) archetypes — full penalty for missing
        missing_core = []
        for archetype in QualityRubric.MANDATORY_ARCHETYPE_ROLES:
            if not _agent_matches_archetype(archetype):
                missing_core.append(archetype)
                score -= 0.25

        if missing_core:
            findings.append(f"Missing core archetypes: {', '.join(missing_core)}")

        # Check business archetypes only when opted-in, with a lighter penalty
        missing_business = []
        if self.rubric.include_business_archetypes:
            for archetype in QualityRubric.OPTIONAL_BUSINESS_ARCHETYPES:
                if not _agent_matches_archetype(archetype):
                    missing_business.append(archetype)
                    score -= 0.10

            if missing_business:
                findings.append(f"Missing optional business archetypes: {', '.join(missing_business)}")

        if not missing_core and not missing_business:
            findings.append("All universal archetypes present")

        suggestions = []
        if missing_core:
            suggestions.append(f"Add mandatory agents: {', '.join(missing_core)}")
        if missing_business:
            suggestions.append(f"Consider adding business agents: {', '.join(missing_business)}")

        return DimensionScore(
            dimension=QualityDimension.UNIVERSALS,
            score=max(0.0, score),
            weight=self.rubric.weights[QualityDimension.UNIVERSALS],
            findings=findings,
            suggestions=suggestions,
        )

    def _eval_revenue_potential(self, bp: AgencyBlueprint) -> DimensionScore:
        """Does this agency have clear revenue-generating capability?"""
        findings = []
        score = 0.0

        # 1. Check for payment/billing tools (0.3)
        payment_terms = ("stripe", "payment", "billing", "invoice", "charge", "checkout", "paypal")
        payment_tools = [t for t in bp.all_tools if any(
            term in t.name.lower() or term in t.description.lower()
            for term in payment_terms
        )]
        if payment_tools:
            score += 0.3
            findings.append(f"Payment/billing tools: {', '.join(t.name for t in payment_tools[:3])}")
        else:
            findings.append("No payment or billing tools found")

        # 2. Check for sales/conversion workflow steps (0.3)
        sales_steps = []
        for wf in bp.workflows:
            for step in wf.steps:
                desc = step.description.lower()
                if any(t in desc for t in ("convert", "close", "proposal", "quote", "upsell", "sales", "purchase")):
                    sales_steps.append(f"{wf.name}:{step.description[:40]}")
        if sales_steps:
            score += 0.3
            findings.append(f"Sales/conversion steps in workflows: {len(sales_steps)}")
        else:
            findings.append("No sales or conversion steps in workflows")

        # 3. Check for customer-facing API endpoints (0.2)
        customer_endpoints = [ep for ep in bp.api_endpoints if any(
            t in ep.path.lower() for t in ("customer", "order", "purchase", "subscribe", "pricing", "quote")
        )]
        if customer_endpoints:
            score += 0.2
            findings.append(f"Customer-facing endpoints: {', '.join(ep.path for ep in customer_endpoints[:3])}")

        # 4. Check for pricing logic (0.2)
        pricing_agents = [a for a in bp.all_agents if any(
            t in a.name.lower() or t in a.system_prompt.lower()[:300]
            for t in ("pricing", "discount", "tier", "plan", "subscription model")
        )]
        pricing_tools = [t for t in bp.all_tools if any(
            term in t.name.lower() for term in ("price", "pricing", "discount", "tier")
        )]
        if pricing_agents or pricing_tools:
            score += 0.2
            findings.append("Pricing logic found in agents or tools")

        suggestions = []
        if score < 0.8:
            suggestions.append("Add payment processing tools (Stripe, billing integrations)")
            suggestions.append("Include sales/conversion steps in workflows")
            suggestions.append("Add customer-facing API endpoints for orders or subscriptions")
            suggestions.append("Define pricing logic in dedicated agents or tools")

        return DimensionScore(
            dimension=QualityDimension.REVENUE_POTENTIAL,
            score=max(0.0, min(1.0, score)),
            weight=self.rubric.weights[QualityDimension.REVENUE_POTENTIAL],
            findings=findings,
            suggestions=suggestions,
        )

    def _eval_customer_acquisition(self, bp: AgencyBlueprint) -> DimensionScore:
        """Can this agency attract and convert customers?"""
        findings = []
        score = 0.0

        # 1. Check for lead intake API endpoints (0.25)
        intake_endpoints = [ep for ep in bp.api_endpoints if any(
            t in ep.path.lower() for t in ("lead", "intake", "signup", "register", "contact", "inquiry")
        )]
        if intake_endpoints:
            score += 0.25
            findings.append(f"Lead intake endpoints: {', '.join(ep.path for ep in intake_endpoints[:3])}")
        else:
            findings.append("No lead intake API endpoints")

        # 2. Check for outbound communication tools (0.25)
        comm_tools = [t for t in bp.all_tools if any(
            term in t.name.lower() or term in t.description.lower()
            for term in ("email", "sms", "notify", "send_message", "outreach", "newsletter", "campaign")
        )]
        if comm_tools:
            score += 0.25
            findings.append(f"Outbound communication tools: {', '.join(t.name for t in comm_tools[:3])}")
        else:
            findings.append("No outbound communication tools (email, SMS, etc.)")

        # 3. Check for CRM/database tools for customer tracking (0.25)
        crm_tools = [t for t in bp.all_tools if any(
            term in t.name.lower() or term in t.description.lower()
            for term in ("crm", "customer_record", "lead_track", "pipeline", "contact_db", "prospect")
        )]
        crm_agents = [a for a in bp.all_agents if any(
            t in a.name.lower() for t in ("crm", "lead", "prospect", "pipeline")
        )]
        if crm_tools or crm_agents:
            score += 0.25
            findings.append("CRM/customer tracking capability found")

        # 4. Check for onboarding workflows (0.25)
        onboard_wfs = [wf for wf in bp.workflows if any(
            t in wf.name.lower() or t in wf.description.lower()
            for t in ("onboard", "intake", "welcome", "signup", "registration")
        )]
        if onboard_wfs:
            score += 0.25
            findings.append(f"Onboarding workflows: {', '.join(wf.name for wf in onboard_wfs[:3])}")
        else:
            findings.append("No onboarding workflows defined")

        suggestions = []
        if score < 0.8:
            suggestions.append("Add lead intake API endpoints (/api/lead, /api/signup)")
            suggestions.append("Include outbound communication tools (email, SMS)")
            suggestions.append("Add CRM or customer tracking tools")
            suggestions.append("Create onboarding workflows for new customers")

        return DimensionScore(
            dimension=QualityDimension.CUSTOMER_ACQUISITION,
            score=max(0.0, min(1.0, score)),
            weight=self.rubric.weights[QualityDimension.CUSTOMER_ACQUISITION],
            findings=findings,
            suggestions=suggestions,
        )

    def _eval_competitive_advantage(self, bp: AgencyBlueprint) -> DimensionScore:
        """What makes this agency better than humans or competitors?"""
        findings = []
        score = 0.4  # Baseline: AI agencies have inherent advantages

        agents = bp.all_agents
        all_tools = bp.all_tools

        # 24/7 availability is inherent
        score += 0.1
        findings.append("Inherent advantage: 24/7 availability, instant response")

        # Scale advantage: unlimited agents
        scalable_teams = [t for t in bp.teams if t.allow_dynamic_scaling]
        spawnable = [a for a in agents if a.can_spawn_sub_agents]
        if scalable_teams and spawnable:
            score += 0.15
            findings.append("Scalability advantage: dynamic agent spawning enabled")
        
        # Specialization depth: many specialized agents > generalist humans
        specialist_count = sum(1 for a in agents if a.role.value == "specialist")
        if specialist_count >= 4:
            score += 0.15
            findings.append(f"Deep specialization: {specialist_count} specialist agents (hard to replicate with humans)")
        elif specialist_count >= 2:
            score += 0.05

        # Tool automation advantage
        if len(all_tools) >= 8:
            score += 0.1
            findings.append(f"Automation advantage: {len(all_tools)} automated tools")
        elif len(all_tools) >= 4:
            score += 0.05

        # Self-improvement (humans don't continuously optimize themselves)
        improve_agents = [a for a in agents if "improv" in a.name.lower() or "analytic" in a.name.lower()]
        if improve_agents:
            score += 0.1
            findings.append("Self-improvement advantage: continuous optimization (humans can't do this)")

        suggestions = []
        if score < 0.8:
            suggestions.append("Add more specialist agents to create depth no human team can match")
            suggestions.append("Enable dynamic scaling so the agency can handle 1000x workload spikes")
            suggestions.append("Add domain-specific tools that automate what humans do manually")

        return DimensionScore(
            dimension=QualityDimension.COMPETITIVE_ADVANTAGE,
            score=max(0.0, min(1.0, score)),
            weight=self.rubric.weights[QualityDimension.COMPETITIVE_ADVANTAGE],
            findings=findings,
            suggestions=suggestions,
        )

    def _eval_monetization(self, bp: AgencyBlueprint) -> DimensionScore:
        """Is there a clear path to charging money for this agency?"""
        findings = []
        score = 0.0

        # 1. Billing integration (0.25)
        billing_tools = [t for t in bp.all_tools if any(
            term in t.name.lower() or term in t.description.lower()
            for term in ("billing", "invoice", "charge", "payment", "stripe", "checkout")
        )]
        if billing_tools:
            score += 0.25
            findings.append(f"Billing tools: {', '.join(t.name for t in billing_tools[:3])}")

        # 2. Subscription management tools (0.25)
        sub_tools = [t for t in bp.all_tools if any(
            term in t.name.lower() or term in t.description.lower()
            for term in ("subscri", "plan", "tier", "upgrade", "downgrade", "recurring")
        )]
        sub_endpoints = [ep for ep in bp.api_endpoints if any(
            t in ep.path.lower() for t in ("subscri", "plan", "billing", "pricing")
        )]
        if sub_tools or sub_endpoints:
            score += 0.25
            findings.append("Subscription/plan management capability")

        # 3. API endpoints for service delivery (0.25)
        if len(bp.api_endpoints) >= 3:
            score += 0.25
            findings.append(f"Service-ready: {len(bp.api_endpoints)} API endpoints (SaaS-capable)")
        elif bp.api_endpoints:
            score += 0.1

        # 4. Value-delivery workflows (0.25)
        value_wfs = [wf for wf in bp.workflows if len(wf.steps) >= 2]
        if len(value_wfs) >= 2:
            score += 0.25
            findings.append(f"{len(value_wfs)} multi-step workflows deliver repeatable value")
        elif value_wfs:
            score += 0.1

        suggestions = []
        if score < 0.8:
            suggestions.append("Add billing/payment integration tools")
            suggestions.append("Include subscription management endpoints")
            suggestions.append("Add more API endpoints to package as a SaaS product")
            suggestions.append("Design multi-step workflows that deliver billable value")

        return DimensionScore(
            dimension=QualityDimension.MONETIZATION,
            score=max(0.0, min(1.0, score)),
            weight=self.rubric.weights[QualityDimension.MONETIZATION],
            findings=findings,
            suggestions=suggestions,
        )

    def _eval_growth_engine(self, bp: AgencyBlueprint) -> DimensionScore:
        """Does this agency compound and scale revenue over time?"""
        findings = []
        score = 0.0

        # 1. Analytics/metrics tools (0.25)
        analytics_tools = [t for t in bp.all_tools if any(
            term in t.name.lower() or term in t.description.lower()
            for term in ("analytic", "metric", "track", "measure", "dashboard", "report", "kpi")
        )]
        analytics_agents = [a for a in bp.all_agents if any(
            t in a.name.lower() for t in ("analytic", "metric", "monitor", "report")
        )]
        if analytics_tools or analytics_agents:
            score += 0.25
            findings.append(f"Analytics/metrics capability ({len(analytics_tools)} tools, {len(analytics_agents)} agents)")
        else:
            findings.append("No analytics or metrics tools")

        # 2. Feedback collection mechanisms (0.25)
        feedback_wfs = [wf for wf in bp.workflows if any(
            any(t in s.description.lower() for t in ("feedback", "survey", "review", "satisfaction", "nps"))
            for s in wf.steps
        )]
        feedback_tools = [t for t in bp.all_tools if any(
            term in t.name.lower() or term in t.description.lower()
            for term in ("feedback", "survey", "review", "rating")
        )]
        if feedback_wfs or feedback_tools:
            score += 0.25
            findings.append("Feedback collection mechanisms found")

        # 3. Automated follow-up workflows (0.25)
        followup_wfs = [wf for wf in bp.workflows if any(
            any(t in s.description.lower() for t in ("follow-up", "followup", "nurture", "remind", "re-engage", "retention"))
            for s in wf.steps
        )]
        if followup_wfs:
            score += 0.25
            findings.append(f"Automated follow-up workflows: {len(followup_wfs)}")
        else:
            findings.append("No automated follow-up workflows")

        # 4. Self-improvement/learning agents (0.25)
        learning_agents = [a for a in bp.all_agents if any(
            t in a.name.lower() for t in ("improv", "learn", "optim", "adapt")
        )]
        scalable = any(t.allow_dynamic_scaling for t in bp.teams)
        if learning_agents:
            score += 0.15
            findings.append(f"Self-improvement agents: {', '.join(a.name for a in learning_agents)}")
        if scalable:
            score += 0.1
            findings.append("Dynamic scaling enabled for growth")

        suggestions = []
        if score < 0.8:
            suggestions.append("Add analytics/metrics tools and agents")
            suggestions.append("Include feedback collection steps in workflows")
            suggestions.append("Create automated follow-up/nurture workflows")
            suggestions.append("Add self-improvement agents that learn from interactions")

        return DimensionScore(
            dimension=QualityDimension.GROWTH_ENGINE,
            score=max(0.0, min(1.0, score)),
            weight=self.rubric.weights[QualityDimension.GROWTH_ENGINE],
            findings=findings,
            suggestions=suggestions,
        )


def format_quality_report(score: QualityScore) -> str:
    """Format a quality score as a human-readable report."""
    lines = []
    status = "✅ PASSED" if score.passed else "❌ FAILED"
    lines.append(f"Quality Assessment (Iteration {score.iteration}): {status}")
    lines.append(f"Overall Score: {score.overall_score:.1%} (threshold: {score.threshold:.0%})")
    lines.append("")

    for ds in score.dimension_scores:
        icon = "✅" if ds.score >= 0.8 else "⚠️" if ds.score >= 0.5 else "❌"
        lines.append(f"  {icon} {ds.dimension.value}: {ds.score:.1%}")
        for f in ds.findings:
            lines.append(f"      → {f}")

    if score.critical_issues:
        lines.append("\n🚨 Critical Issues:")
        for issue in score.critical_issues:
            lines.append(f"  • {issue}")

    if score.recommendations:
        lines.append("\n💡 Recommendations:")
        for rec in score.recommendations:
            lines.append(f"  • {rec}")

    return "\n".join(lines)
