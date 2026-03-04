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
        # Business ambition weights — intentionally higher than technical
        QualityDimension.REVENUE_POTENTIAL: 1.8,
        QualityDimension.CUSTOMER_ACQUISITION: 1.6,
        QualityDimension.COMPETITIVE_ADVANTAGE: 1.5,
        QualityDimension.MONETIZATION: 1.4,
        QualityDimension.GROWTH_ENGINE: 1.7,
    }

    MANDATORY_ARCHETYPE_ROLES = [
        "qa_reviewer",
        "intake_coordinator", 
        "self_improvement",
        "analytics",
        "growth",
        "customer_success",
        "lead_generation",
        "revenue",
    ]

    def __init__(self, threshold: float = 0.8, weights: dict[QualityDimension, float] | None = None):
        self.threshold = threshold
        self.weights = weights or self.DEFAULT_WEIGHTS


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
        """Are agent system prompts detailed enough?"""
        agents = bp.all_agents
        findings = []
        score = 1.0

        shallow_agents = []
        for agent in agents:
            prompt_len = len(agent.system_prompt)
            if prompt_len < 100:
                shallow_agents.append(agent.name)
            elif prompt_len < 200:
                score -= 0.05

        if shallow_agents:
            ratio = len(shallow_agents) / max(len(agents), 1)
            score -= ratio * 0.5
            findings.append(f"Shallow system prompts: {', '.join(shallow_agents)}")

        # Check for capabilities
        no_caps = [a.name for a in agents if not a.capabilities]
        if no_caps:
            score -= 0.1 * min(len(no_caps) / max(len(agents), 1), 1.0)
            findings.append(f"Missing capabilities list: {', '.join(no_caps[:3])}")

        suggestions = []
        if score < 0.8:
            suggestions.append("Expand agent system prompts to 3+ paragraphs with personality, expertise, constraints")
            suggestions.append("Add explicit capabilities lists to all agents")

        return DimensionScore(
            dimension=QualityDimension.AGENT_DEPTH,
            score=max(0.0, score),
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
        findings = []
        score = 0.7  # Start at 0.7 — resilience comes from runtime, not just blueprint

        # Check for error handling in agent prompts
        error_aware = 0
        for agent in bp.all_agents:
            prompt_lower = agent.system_prompt.lower()
            if any(word in prompt_lower for word in ("error", "fail", "fallback", "escalat", "retry", "exception")):
                error_aware += 1

        awareness_ratio = error_aware / max(len(bp.all_agents), 1)
        if awareness_ratio < 0.3:
            score -= 0.2
            findings.append("Few agents mention error handling in their prompts")
        else:
            score += 0.15

        suggestions = []
        if score < 0.8:
            suggestions.append("Include error handling and escalation instructions in agent system prompts")
            suggestions.append("Add fallback behaviors for when tools fail or agents are unavailable")

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
        all_text = " ".join(a.name.lower() + " " + a.system_prompt.lower()[:100] for a in bp.all_agents)

        missing = []
        for archetype in QualityRubric.MANDATORY_ARCHETYPE_ROLES:
            # Flexible matching — check name, role, or prompt
            found = False
            for name, agent in agents_lower.items():
                archetype_terms = archetype.replace("_", " ").split()
                if any(t in name or t in agent.system_prompt.lower()[:200] for t in archetype_terms):
                    found = True
                    break
            if not found:
                missing.append(archetype)
                score -= 0.25

        if missing:
            findings.append(f"Missing universal archetypes: {', '.join(missing)}")
        else:
            findings.append("All universal archetypes present")

        suggestions = []
        if missing:
            suggestions.append(f"Add mandatory agents: {', '.join(missing)}")

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
        score = 0.3  # Start low — must prove revenue potential

        all_text = " ".join(
            a.system_prompt.lower() + " " + " ".join(a.capabilities)
            for a in bp.all_agents
        ).lower()

        # Check for revenue-oriented language in agents
        revenue_terms = ("revenue", "sales", "monetiz", "profit", "pricing", "billing",
                         "payment", "subscription", "upsell", "cross-sell", "conversion",
                         "roi", "cost sav", "value", "customer lifetime")
        matches = sum(1 for t in revenue_terms if t in all_text)
        if matches >= 5:
            score += 0.4
            findings.append(f"Strong revenue awareness ({matches} revenue-related concepts found)")
        elif matches >= 2:
            score += 0.2
            findings.append(f"Some revenue awareness ({matches} revenue concepts)")
        else:
            findings.append("Almost no revenue-oriented language in agent prompts")

        # Check for dedicated revenue/sales agents
        revenue_agents = [a for a in bp.all_agents if any(
            t in a.name.lower() or t in a.title.lower()
            for t in ("sales", "revenue", "growth", "monetiz", "billing", "pricing")
        )]
        if revenue_agents:
            score += 0.2
            findings.append(f"Revenue-focused agents: {', '.join(a.name for a in revenue_agents)}")
        else:
            findings.append("No dedicated revenue or sales agents")

        # Check for revenue-related tools
        revenue_tools = [t for t in bp.all_tools if any(
            term in t.name.lower() or term in t.description.lower()
            for term in ("payment", "invoice", "price", "billing", "revenue", "sales", "convert")
        )]
        if revenue_tools:
            score += 0.1

        suggestions = []
        if score < 0.8:
            suggestions.append("Add agents specifically designed to drive revenue (sales, upselling, pricing optimization)")
            suggestions.append("Include revenue-tracking tools and conversion metrics")
            suggestions.append("Ensure agent prompts explicitly mention revenue goals and KPIs")

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
        score = 0.3

        all_text = " ".join(
            a.system_prompt.lower() + " " + " ".join(a.capabilities)
            for a in bp.all_agents
        ).lower()

        # Check for customer acquisition concepts
        acq_terms = ("lead", "prospect", "acquisition", "onboard", "signup", "register",
                      "funnel", "outreach", "marketing", "campaign", "referral", "viral",
                      "demo", "trial", "nurtur", "qualify", "pipeline")
        matches = sum(1 for t in acq_terms if t in all_text)
        if matches >= 5:
            score += 0.4
            findings.append(f"Strong acquisition focus ({matches} acquisition concepts)")
        elif matches >= 2:
            score += 0.2
            findings.append(f"Some acquisition awareness ({matches} concepts)")
        else:
            findings.append("No customer acquisition strategy in agent design")

        # Check for intake/onboarding workflow
        intake_wfs = [wf for wf in bp.workflows if any(
            t in wf.name.lower() or t in wf.description.lower()
            for t in ("intake", "onboard", "acquisition", "lead", "signup")
        )]
        if intake_wfs:
            score += 0.2
            findings.append("Has intake/onboarding workflows")
        
        # Check for customer-facing agents
        customer_agents = [a for a in bp.all_agents if any(
            t in a.name.lower() or t in a.role.value
            for t in ("intake", "customer", "support", "success", "onboard")
        )]
        if customer_agents:
            score += 0.1

        suggestions = []
        if score < 0.8:
            suggestions.append("Add a Lead Generation agent that identifies and qualifies prospects")
            suggestions.append("Create an onboarding workflow that converts leads to active users")
            suggestions.append("Include referral and viral growth mechanisms")

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
        score = 0.3

        # API endpoints = can be offered as a service
        if len(bp.api_endpoints) >= 3:
            score += 0.2
            findings.append(f"Service-ready: {len(bp.api_endpoints)} API endpoints (can be offered as SaaS)")
        elif bp.api_endpoints:
            score += 0.1

        # Multiple teams = comprehensive service offering
        if len(bp.teams) >= 3:
            score += 0.15
            findings.append("Comprehensive offering: multiple specialized teams")

        # Workflows = repeatable processes (subscription-worthy)
        if len(bp.workflows) >= 3:
            score += 0.15
            findings.append("Process automation: multiple workflows (subscription model viable)")

        # Domain specificity = higher willingness to pay
        if len(bp.domain) > 100:
            score += 0.1
            findings.append("Domain-specific solution (commands premium pricing)")

        # Analytics/reporting = proof of value to customers
        analytics_capable = any("analytic" in a.name.lower() or "report" in a.name.lower() for a in bp.all_agents)
        if analytics_capable:
            score += 0.1
            findings.append("Can demonstrate ROI to customers via analytics/reporting")

        suggestions = []
        if score < 0.8:
            suggestions.append("Add more API endpoints to package as a SaaS product")
            suggestions.append("Include analytics/reporting to prove ROI to paying customers")
            suggestions.append("Design workflows that map to specific billable services")
            suggestions.append("Add usage tracking for metered billing")

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
        score = 0.2  # Start very low — growth engines are rare and valuable

        all_text = " ".join(
            a.system_prompt.lower() + " " + " ".join(a.capabilities)
            for a in bp.all_agents
        ).lower()

        # Check for growth-compounding concepts
        growth_terms = ("growth", "scale", "automat", "compound", "network effect",
                        "viral", "referral", "retention", "lifetime value", "ltv",
                        "recurring", "repeat", "expand", "flywheel", "loop")
        matches = sum(1 for t in growth_terms if t in all_text)
        if matches >= 5:
            score += 0.3
            findings.append(f"Growth engine concepts present ({matches} growth terms)")
        elif matches >= 2:
            score += 0.15

        # Self-improvement = gets better over time (compounding advantage)
        has_improvement = any("improv" in a.name.lower() for a in bp.all_agents)
        if has_improvement:
            score += 0.15
            findings.append("Self-improving: gets better over time (compounding advantage)")

        # Data/learning flywheel
        has_memory_usage = any("memory" in a.system_prompt.lower() or "learn" in a.system_prompt.lower() for a in bp.all_agents)
        if has_memory_usage:
            score += 0.1
            findings.append("Learning flywheel: agents learn from interactions")

        # Scalability (can handle 10x-100x growth without proportional cost)
        scalable = any(t.allow_dynamic_scaling for t in bp.teams)
        if scalable:
            score += 0.15
            findings.append("Scales without linear cost increase (AI economics)")

        # Retention/success agents (keeps customers = recurring revenue)
        retention_agents = [a for a in bp.all_agents if any(
            t in a.name.lower() for t in ("retention", "success", "loyalty", "satisfaction")
        )]
        if retention_agents:
            score += 0.1
            findings.append("Retention focus: keeps customers paying month after month")

        suggestions = []
        if score < 0.8:
            suggestions.append("Add a Growth Hacker agent that finds and exploits viral/referral loops")
            suggestions.append("Add a Customer Success agent for retention and LTV maximization")
            suggestions.append("Design agents that learn from every interaction (compounding intelligence)")
            suggestions.append("Include referral/viral growth mechanisms in workflows")

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
