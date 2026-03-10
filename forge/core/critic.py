"""Blueprint Critic — LLM-powered deep review with iterative refinement."""

from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, Field

from forge.core.blueprint import AgencyBlueprint
from forge.core.llm import LLMClient
from forge.core.quality import BlueprintEvaluator, QualityScore, QualityRubric, format_quality_report

logger = logging.getLogger(__name__)


class CritiqueIssue(BaseModel):
    """A specific issue found during critique."""
    severity: str = Field(description="critical, major, minor")
    category: str = Field(description="coverage, depth, tooling, architecture, workflow, scalability, resilience")
    description: str = Field(description="What the issue is")
    suggestion: str = Field(description="How to fix it")
    affected_component: str = Field(default="", description="Which agent/team/workflow is affected")


class CritiqueResult(BaseModel):
    """Result of an LLM-powered blueprint critique."""
    overall_assessment: str = Field(description="High-level assessment paragraph")
    score: float = Field(ge=0.0, le=1.0, description="Overall quality score")
    issues: list[CritiqueIssue] = Field(default_factory=list)
    strengths: list[str] = Field(default_factory=list, description="What's done well")
    improvement_instructions: str = Field(default="", description="Detailed instructions for the next iteration")
    ready_for_deployment: bool = Field(default=False)


class BlueprintCritic:
    """
    LLM-powered critic that reviews agency blueprints with deep semantic understanding.
    
    Unlike the structural BlueprintEvaluator, the Critic understands domain context
    and can identify issues like:
    - Missing agent roles for the specific domain
    - System prompts that are too generic
    - Tools that don't match the domain's real needs
    - Workflow gaps for common use cases
    """

    def __init__(self, llm: LLMClient) -> None:
        self.llm = llm

    async def critique(self, blueprint: AgencyBlueprint, previous_critique: CritiqueResult | None = None, iteration: int = 0) -> CritiqueResult:
        """
        Perform a deep critique of the blueprint.
        
        If previous_critique is provided, focuses on whether previous issues were addressed.
        """
        bp_summary = self._summarize_blueprint(blueprint)

        messages = [
            {"role": "system", "content": (
                "You are an expert AI agency architect and quality reviewer. "
                "You are reviewing a blueprint for an AI agency that will be deployed in production. "
                "Be thorough, specific, and constructive. Your review directly determines whether "
                "this agency will succeed or fail.\n\n"
                "Evaluate against these criteria:\n"
                "1. ROLE COVERAGE: Do the agents cover all the functions needed for this domain? "
                "Are there obvious roles missing?\n"
                "2. AGENT QUALITY: Are system prompts detailed, specific, and actionable? "
                "Do they include personality, constraints, and edge case handling?\n"
                "3. TOOLING: Do agents have the right tools? Are tool parameters well-defined?\n"
                "4. TEAM ARCHITECTURE: Are teams logically organized? Do leads make sense?\n"
                "5. WORKFLOWS: Do workflows cover the main operations? Are they complete?\n"
                "6. SCALABILITY: Can the agency handle dynamic workloads?\n"
                "7. RESILIENCE: How does the agency handle errors and edge cases?\n"
                "8. DOMAIN FIT: Does the agency actually solve the stated domain problem?\n"
                "9. SELF-IMPROVEMENT: Does the agency have QA, feedback, and improvement loops?\n"
                "10. DEPLOYMENT READINESS: Is this ready to deploy and run?\n\n"
                "Be SPECIFIC. Don't say 'add more agents' — say exactly which agent is needed and why."
            )},
        ]

        user_content = f"Review this AI agency blueprint:\n\n{bp_summary}"

        if previous_critique:
            user_content += (
                f"\n\n--- PREVIOUS REVIEW (Iteration {iteration - 1}) ---\n"
                f"Score: {previous_critique.score:.1%}\n"
                f"Issues found: {len(previous_critique.issues)}\n"
                f"Key issues:\n"
            )
            for issue in previous_critique.issues[:5]:
                user_content += f"  [{issue.severity}] {issue.description}\n"
            user_content += (
                f"\nThe blueprint has been revised to address these issues. "
                f"Check if the issues were actually fixed and identify any remaining or new problems."
            )

        messages.append({"role": "user", "content": user_content})

        result = await self.llm.complete_structured(messages, CritiqueResult)
        return result

    def _summarize_blueprint(self, bp: AgencyBlueprint) -> str:
        """Create a detailed text summary of the blueprint for the critic."""
        lines = []
        lines.append(f"AGENCY: {bp.name}")
        lines.append(f"DOMAIN: {bp.domain}")
        lines.append(f"DESCRIPTION: {bp.description}")
        lines.append(f"MODEL: {bp.model}")
        lines.append("")

        lines.append(f"TEAMS ({len(bp.teams)}):")
        for team in bp.teams:
            lead_str = f" | Lead: {team.lead.name} ({team.lead.role.value})" if team.lead else " | No lead"
            lines.append(f"  • {team.name}{lead_str} — {team.description}")
            for agent in team.agents:
                tool_names = [t.name for t in agent.tools]
                lines.append(f"    - {agent.name} ({agent.role.value}): {agent.title}")
                lines.append(f"      Prompt preview: {agent.system_prompt[:150]}...")
                lines.append(f"      Capabilities: {', '.join(agent.capabilities[:4])}")
                if tool_names:
                    lines.append(f"      Tools: {', '.join(tool_names)}")
        lines.append("")

        all_tools = bp.all_tools
        lines.append(f"TOOLS ({len(all_tools)}):")
        for tool in all_tools:
            params = ", ".join(p.get("name", "?") for p in tool.parameters)
            lines.append(f"  • {tool.name}({params}) — {tool.description[:80]}")
        lines.append("")

        lines.append(f"WORKFLOWS ({len(bp.workflows)}):")
        for wf in bp.workflows:
            lines.append(f"  • {wf.name} (trigger: {wf.trigger}) — {wf.description}")
            for step in wf.steps:
                deps = f" [depends: {', '.join(step.depends_on)}]" if step.depends_on else ""
                lines.append(f"    {step.id}: {step.description}{deps}")
        lines.append("")

        lines.append(f"API ENDPOINTS ({len(bp.api_endpoints)}):")
        for ep in bp.api_endpoints:
            lines.append(f"  • {ep.method} {ep.path} — {ep.description}")

        return "\n".join(lines)


class BusinessAmbitionCritic:
    """
    Evaluates a blueprint like a ruthless VC / business advisor.
    
    This critic doesn't care about code quality — it cares about:
    - Will this make money?
    - Is this the MOST AMBITIOUS interpretation of the domain?
    - Would someone pay $10K+/month for this agency?
    - What's the competitive moat?
    - Is there a path to $1M+ ARR?
    """

    def __init__(self, llm: LLMClient) -> None:
        self.llm = llm

    async def critique(self, blueprint: AgencyBlueprint, domain_description: str) -> CritiqueResult:
        """Evaluate the blueprint's business ambition and revenue potential."""
        bp_summary = BlueprintCritic(self.llm)._summarize_blueprint(blueprint)

        messages = [
            {"role": "system", "content": (
                "You are a ruthless venture capitalist and business strategist evaluating an AI agency. "
                "You've funded companies that went from zero to billions. You have ZERO patience for "
                "mediocrity. You only care about one thing: WILL THIS MAKE SERIOUS MONEY?\n\n"
                "Evaluate this agency blueprint against these criteria:\n\n"
                "1. AMBITION LEVEL (0-10): Is this the MOST AMBITIOUS interpretation of the domain? "
                "Or is it playing it safe? A customer support agency should also upsell, cross-sell, "
                "gather intelligence, reduce churn, and drive referrals — not just answer questions.\n\n"
                "2. REVENUE POTENTIAL (0-10): How much money can this agency generate? "
                "Could someone charge $5K-$50K/month for this as a service? "
                "Is it replacing $200K+ worth of human employees?\n\n"
                "3. COMPETITIVE MOAT (0-10): What stops someone from copying this? "
                "Does it have network effects? Data advantages? Proprietary tools? "
                "Or is it just a glorified chatbot wrapper?\n\n"
                "4. SCALABILITY (0-10): Can this serve 1 customer or 10,000 with the same codebase? "
                "Does revenue scale faster than costs?\n\n"
                "5. CUSTOMER LOCK-IN (0-10): Once a customer starts using this, how hard is it to leave? "
                "Does the agency accumulate knowledge/data that makes it more valuable over time?\n\n"
                "6. MARKET SIZE (0-10): How big is the addressable market? Is this a $10M market or $10B?\n\n"
                "7. TIME TO REVENUE (0-10): How quickly can this start generating revenue? "
                "Days? Weeks? Months? The faster the better.\n\n"
                "Be BRUTALLY HONEST. If this agency is mediocre, say so. If it's missing obvious "
                "money-making opportunities, call them out. Give specific, actionable feedback on "
                "how to make this a money-printing machine.\n\n"
                "Your improvement_instructions should read like a battle plan for turning this "
                "into a high-revenue business. Be specific: which agents to add, which tools to build, "
                "which workflows to create."
            )},
            {"role": "user", "content": (
                f"DOMAIN DESCRIPTION:\n{domain_description}\n\n"
                f"AGENCY BLUEPRINT:\n{bp_summary}\n\n"
                f"Judge this against the most ambitious aim: building an AI agency that generates "
                f"serious revenue. Score 0.0-1.0 overall. Be ruthless."
            )},
        ]

        result = await self.llm.complete_structured(messages, CritiqueResult)
        return result


class RefinementLoop:
    """
    Iterative refinement loop that critiques and improves blueprints
    until they meet quality standards.
    
    The loop:
    1. Evaluate blueprint (structural checks)
    2. Critique blueprint (LLM semantic review)
    3. If passing → done
    4. If failing → feed critique back to domain analyzer → regenerate → repeat
    
    The loop runs as many times as needed (configurable max, default 10).
    """

    def __init__(
        self,
        llm: LLMClient,
        evaluator: BlueprintEvaluator | None = None,
        critic: BlueprintCritic | None = None,
        max_iterations: int = 10,
        min_score: float = 0.8,
    ):
        self.llm = llm
        self.evaluator = evaluator or BlueprintEvaluator()
        self.critic = critic or BlueprintCritic(llm)
        self.business_critic = BusinessAmbitionCritic(llm)
        self.max_iterations = max_iterations
        self.min_score = min_score
        self._history: list[dict[str, Any]] = []

    async def refine(
        self,
        blueprint: AgencyBlueprint,
        domain_description: str,
        refine_callback: Any = None,  # Callable to regenerate parts of blueprint
    ) -> tuple[AgencyBlueprint, list[dict[str, Any]]]:
        """
        Iteratively refine a blueprint until it meets quality standards.
        
        Returns the refined blueprint and the history of iterations.
        """
        current_blueprint = blueprint
        previous_critique: CritiqueResult | None = None
        # Reset history for this refinement run
        self._history = []

        for iteration in range(self.max_iterations):
            logger.info(f"=== Refinement Iteration {iteration + 1}/{self.max_iterations} ===")

            # Step 1: Structural evaluation
            structural_score = self.evaluator.evaluate(current_blueprint, iteration=iteration)
            logger.info(f"Structural score: {structural_score.overall_score:.1%}")

            # Step 2: LLM critique
            critique = await self.critic.critique(
                current_blueprint,
                previous_critique=previous_critique,
                iteration=iteration,
            )
            logger.info(f"Critic score: {critique.score:.1%} | Issues: {len(critique.issues)}")

            # Step 2b: Business ambition critique
            biz_critique = await self.business_critic.critique(current_blueprint, domain_description)
            logger.info(f"Business ambition score: {biz_critique.score:.1%}")

            # Combined score: structural (25%) + technical critique (35%) + business ambition (40%)
            combined_score = (
                structural_score.overall_score * 0.25
                + critique.score * 0.35
                + biz_critique.score * 0.40
            )

            # Identify dimensions that scored 0.0 (completely missing)
            zero_dims = [
                ds.dimension.value
                for ds in structural_score.dimension_scores
                if ds.score == 0.0
            ]

            # Record iteration
            iteration_record = {
                "iteration": iteration,
                "structural_score": structural_score.overall_score,
                "critic_score": critique.score,
                "business_ambition_score": biz_critique.score,
                "combined_score": round(combined_score, 3),
                "zero_dimensions": zero_dims,
                "issues_count": len(critique.issues) + len(biz_critique.issues),
                "critical_issues": (
                    [i.description for i in critique.issues if i.severity == "critical"]
                    + [i.description for i in biz_critique.issues if i.severity == "critical"]
                ),
                "passed": combined_score >= self.min_score and not any(
                    i.severity == "critical" for i in critique.issues + biz_critique.issues
                ),
            }
            self._history.append(iteration_record)

            # Check if passing
            all_issues = critique.issues + biz_critique.issues
            has_critical = any(i.severity == "critical" for i in all_issues)
            if combined_score >= self.min_score and not has_critical:
                logger.info(f"✅ Blueprint PASSED at iteration {iteration + 1} (score: {combined_score:.1%})")
                return current_blueprint, self._history

            # Step 3: Improve blueprint based on critique
            logger.info(f"Blueprint needs improvement (score: {combined_score:.1%}, threshold: {self.min_score:.0%})")

            if refine_callback:
                current_blueprint = await refine_callback(
                    current_blueprint, critique, structural_score, iteration
                )
            else:
                current_blueprint = await self._auto_refine(
                    current_blueprint, critique, structural_score, domain_description
                )

            previous_critique = critique

        # Max iterations reached — record final state so callers can inspect the score
        final_record = self._history[-1] if self._history else {"combined_score": 0}
        logger.warning(
            f"Max iterations ({self.max_iterations}) reached. "
            f"Final score: {final_record['combined_score']:.0%}. Returning best blueprint."
        )
        return current_blueprint, self._history

    async def _auto_refine(
        self,
        blueprint: AgencyBlueprint,
        critique: CritiqueResult,
        structural_score: QualityScore,
        domain_description: str,
    ) -> AgencyBlueprint:
        """
        Automatically refine a blueprint based on critique feedback.
        
        Uses LLM to surgically improve the blueprint rather than regenerating everything.
        """
        # Collect all improvement instructions
        improvements = []
        for issue in critique.issues:
            improvements.append(f"[{issue.severity}] {issue.description}: {issue.suggestion}")
        for issue in structural_score.critical_issues:
            improvements.append(f"[structural] {issue}")
        if critique.improvement_instructions:
            improvements.append(f"[general] {critique.improvement_instructions}")

        # Add business ambition feedback
        # (We pass the business critique via the structural_score's recommendations as a workaround,
        #  but ideally we'd pass it as a separate parameter. For now, include domain-level business push.)
        improvements.append("[business] Ensure the agency is designed to MAXIMIZE REVENUE. "
                          "Every agent should have a revenue angle. Every workflow should drive business value. "
                          "Think: what would make someone pay $10K+/month for this agency?")

        improvement_text = "\n".join(improvements)

        # Ask LLM to produce an improved blueprint
        messages = [
            {"role": "system", "content": (
                "You are an AI agency architect improving a blueprint based on reviewer feedback. "
                "You must return a complete, corrected AgencyBlueprint as JSON. "
                "Make targeted improvements — don't throw away what's already good. "
                "Focus on fixing the identified issues while preserving working elements."
            )},
            {"role": "user", "content": (
                f"DOMAIN: {domain_description}\n\n"
                f"CURRENT BLUEPRINT (JSON):\n{blueprint.model_dump_json(indent=2)}\n\n"
                f"IMPROVEMENTS NEEDED:\n{improvement_text}\n\n"
                f"Produce an improved version of this blueprint. Return the complete "
                f"AgencyBlueprint as JSON. Fix all identified issues."
            )},
        ]

        try:
            improved = await self.llm.complete_structured(messages, AgencyBlueprint)
            logger.info(f"Auto-refinement produced updated blueprint: {improved.name}")
            return improved
        except Exception as e:
            logger.warning(f"Auto-refinement failed: {e}. Returning original blueprint.")
            return blueprint
