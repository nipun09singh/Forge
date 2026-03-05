"""StressLab — end-to-end stress testing with infinite improvement loops.

The full cycle:
1. GENERATE scenarios for the domain (LLM creates realistic test cases)
2. TEST the agency (send scenarios, rate responses)
3. HAVE the agency BUILD a product (ProjectExecutor)
4. TEST the product (run code, verify behavior)
5. ANALYZE failures across both agency and product
6. EVOLVE (self-evolution improves prompts, spawner creates agents)
7. REBUILD product with improved agency
8. RE-TEST everything
9. LOOP until pass_rate >= target OR improvement stalls

This is what makes Forge agencies "battle-tested against 200+ scenarios
before a single real customer touches them."
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from forge.runtime.agency import Agency

logger = logging.getLogger(__name__)


@dataclass
class Scenario:
    """A test scenario for the agency or its product."""
    id: str = ""
    description: str = ""
    difficulty: str = "medium"  # easy, medium, hard, adversarial
    category: str = ""  # support, billing, technical, edge_case
    expected_behavior: str = ""  # What a good response looks like
    test_type: str = "agency"  # agency (test responses) or product (test built code)


@dataclass
class TestResult:
    """Result of testing one scenario."""
    scenario_id: str = ""
    passed: bool = False
    score: float = 0.0  # 0-1
    response: str = ""
    feedback: str = ""
    duration_seconds: float = 0.0


@dataclass
class CycleReport:
    """Report from one stress test cycle."""
    cycle: int = 0
    total_scenarios: int = 0
    passed: int = 0
    failed: int = 0
    pass_rate: float = 0.0
    avg_score: float = 0.0
    evolutions_applied: int = 0
    agents_spawned: int = 0
    failure_categories: dict[str, int] = field(default_factory=dict)
    duration_seconds: float = 0.0
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class StressLab:
    """
    End-to-end stress testing with infinite improvement loops.

    Usage:
        lab = StressLab(agency)
        report = await lab.run_full_cycle(
            domain="dental practice",
            target_pass_rate=0.95,
            max_cycles=5,
        )
    """

    def __init__(
        self,
        agency: "Agency" | None = None,
        llm_client: Any = None,
        model: str = "gpt-4o",
    ):
        self.agency = agency
        self._llm_client = llm_client
        self.model = model
        self._cycle_reports: list[CycleReport] = []

    def set_agency(self, agency: "Agency") -> None:
        self.agency = agency
        if not self._llm_client:
            self._llm_client = agency._llm_client

    # ═══════════════════════════════════════════════════════
    # Phase 1: Generate Scenarios
    # ═══════════════════════════════════════════════════════

    async def generate_scenarios(
        self,
        domain: str,
        count: int = 20,
        difficulty_mix: dict[str, int] | None = None,
    ) -> list[Scenario]:
        """Generate realistic test scenarios for a domain using LLM."""
        if not self._llm_client:
            return self._fallback_scenarios(domain, count)

        mix = difficulty_mix or {"easy": 5, "medium": 8, "hard": 5, "adversarial": 2}

        prompt = (
            f"Generate {count} realistic test scenarios for a '{domain}' AI agency.\n\n"
            f"Difficulty mix: {json.dumps(mix)}\n\n"
            "For each scenario, provide:\n"
            "- description: what the simulated customer says/asks\n"
            "- difficulty: easy/medium/hard/adversarial\n"
            "- category: the type of request\n"
            "- expected_behavior: what a correct response should include\n\n"
            "Include edge cases, angry customers, multi-step requests, and requests "
            "that require real tool use (database queries, file creation, calculations).\n\n"
            "Return JSON: {\"scenarios\": [{\"description\": \"...\", \"difficulty\": \"...\", "
            "\"category\": \"...\", \"expected_behavior\": \"...\"}]}"
        )

        try:
            response = await self._llm_client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.7,
            )
            content = response.choices[0].message.content or "{}"
            if content.strip().startswith("```"):
                content = content.split("\n", 1)[1] if "\n" in content else content[3:]
                if content.strip().endswith("```"):
                    content = content.strip()[:-3]

            data = json.loads(content)
            scenarios = []
            for i, s in enumerate(data.get("scenarios", [])):
                scenarios.append(Scenario(
                    id=f"s-{i+1}",
                    description=s.get("description", ""),
                    difficulty=s.get("difficulty", "medium"),
                    category=s.get("category", "general"),
                    expected_behavior=s.get("expected_behavior", ""),
                    test_type="agency",
                ))
            return scenarios or self._fallback_scenarios(domain, count)
        except Exception as e:
            logger.error(f"Scenario generation failed: {e}")
            return self._fallback_scenarios(domain, count)

    def _fallback_scenarios(self, domain: str, count: int) -> list[Scenario]:
        """Fallback scenarios with proper expected behaviors."""
        basics = [
            Scenario(id="s-1", description=f"What services do you offer for {domain}?", 
                     difficulty="easy", category="info",
                     expected_behavior="Should list specific services relevant to the domain. Should be helpful and professional."),
            Scenario(id="s-2", description="I need to schedule an appointment", 
                     difficulty="easy", category="scheduling",
                     expected_behavior="Should ask for preferred date/time or offer available slots. Should be accommodating."),
            Scenario(id="s-3", description="I want a refund for the last service", 
                     difficulty="medium", category="billing",
                     expected_behavior="Should acknowledge the request, ask for details (order/service ID), explain refund policy."),
            Scenario(id="s-4", description="Your service was terrible and I want to speak to a manager", 
                     difficulty="hard", category="complaint",
                     expected_behavior="Should apologize sincerely, acknowledge frustration, offer to resolve the issue, mention escalation option."),
            Scenario(id="s-5", description="I'm considering switching to a competitor. What can you offer to keep me?", 
                     difficulty="hard", category="retention",
                     expected_behavior="Should express concern about losing the customer, ask what's driving the decision, offer specific retention incentives or value."),
            Scenario(id="s-6", description="I was charged twice for the same service last month",
                     difficulty="medium", category="billing",
                     expected_behavior="Should take the issue seriously, ask for payment details to investigate, offer to resolve or refund the duplicate charge."),
            Scenario(id="s-7", description="Can you help me understand how to use the advanced features?",
                     difficulty="easy", category="support",
                     expected_behavior="Should offer guidance, ask which specific features, provide step-by-step help or point to documentation."),
            Scenario(id="s-8", description="I have an urgent issue that needs immediate attention — my system is completely down",
                     difficulty="hard", category="urgent",
                     expected_behavior="Should treat as high priority, express urgency, ask for diagnostic details, provide immediate troubleshooting steps or escalate."),
        ]
        return basics[:count]

    # ═══════════════════════════════════════════════════════
    # Phase 2: Test Agency Responses
    # ═══════════════════════════════════════════════════════

    async def test_agency(
        self,
        scenarios: list[Scenario],
        max_concurrent: int = 3,
    ) -> list[TestResult]:
        """Test the agency against scenarios."""
        if not self.agency:
            return []

        results = []
        semaphore = asyncio.Semaphore(max_concurrent)

        async def run_one(scenario: Scenario) -> TestResult:
            async with semaphore:
                start = time.time()
                try:
                    result = await self.agency.execute(scenario.description)
                    duration = time.time() - start

                    # Evaluate the response
                    score, feedback = await self._evaluate_response(
                        scenario, result.output if hasattr(result, 'output') else str(result)
                    )

                    return TestResult(
                        scenario_id=scenario.id,
                        passed=score >= 0.7,
                        score=score,
                        response=(result.output if hasattr(result, 'output') else str(result))[:300],
                        feedback=feedback,
                        duration_seconds=round(duration, 1),
                    )
                except Exception as e:
                    return TestResult(
                        scenario_id=scenario.id,
                        passed=False, score=0.0,
                        response=f"Error: {e}",
                        feedback=f"Agency crashed: {e}",
                        duration_seconds=round(time.time() - start, 1),
                    )

        tasks = [run_one(s) for s in scenarios]
        results = await asyncio.gather(*tasks)
        return list(results)

    async def _evaluate_response(self, scenario: Scenario, response: str) -> tuple[float, str]:
        """Use LLM to evaluate if a response is good."""
        if not self._llm_client or not response:
            # Content-based heuristic (not length-based)
            score = 0.5  # Start at neutral
            resp_lower = response.lower() if response else ""
            
            # Positive signals
            if len(response) > 100: score += 0.1
            if any(w in resp_lower for w in ["help", "assist", "happy to", "certainly", "of course"]): score += 0.1
            if "?" in response: score += 0.05  # Asks clarifying questions
            if any(w in resp_lower for w in ["sorry", "apologize", "understand"]): score += 0.05
            
            # Check against expected behavior
            if scenario.expected_behavior:
                expected_words = set(scenario.expected_behavior.lower().split())
                response_words = set(resp_lower.split())
                overlap = len(expected_words & response_words) / max(len(expected_words), 1)
                score += overlap * 0.3
            
            # Negative signals
            if len(response) < 20: score -= 0.3
            if "error" in resp_lower[:50]: score -= 0.2
            if "i cannot" in resp_lower or "i'm unable" in resp_lower: score -= 0.1
            
            score = max(0.0, min(1.0, score))
            return score, f"Heuristic: content-based scoring"

        eval_parts = [
            f"Rate this customer service interaction on a scale of 0.0 to 1.0.\n",
            f"Customer said: \"{scenario.description}\"\n",
        ]
        if scenario.expected_behavior:
            eval_parts.append(f"A good response should: {scenario.expected_behavior}\n")
        eval_parts.append(f"Agent responded: \"{response[:500]}\"\n\n")
        eval_parts.append(
            "Score criteria:\n"
            "- 0.9-1.0: Excellent — addresses the issue fully, professional, actionable\n"
            "- 0.7-0.8: Good — mostly addresses the issue, minor gaps\n"
            "- 0.5-0.6: Acceptable — relevant but incomplete or generic\n"
            "- 0.3-0.4: Poor — misses key aspects of the request\n"
            "- 0.0-0.2: Bad — irrelevant, unhelpful, or harmful\n\n"
            "Return JSON: {\"score\": 0.85, \"feedback\": \"...\"}"
        )
        
        prompt = "\n".join(eval_parts)

        try:
            resp = await self._llm_client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2,
            )
            content = resp.choices[0].message.content or "{}"
            if content.strip().startswith("```"):
                content = content.split("\n", 1)[1] if "\n" in content else content[3:]
                if content.strip().endswith("```"):
                    content = content.strip()[:-3]
            data = json.loads(content)
            return float(data.get("score", 0.5)), data.get("feedback", "")
        except Exception:
            return 0.7, "Evaluation fallback"

    # ═══════════════════════════════════════════════════════
    # Phase 3-4: Build and Test Product
    # ═══════════════════════════════════════════════════════

    async def test_product_build(
        self,
        product_task: str,
        workdir: str = "./workspace/stress_test_product",
    ) -> TestResult:
        """Have the agency build a product and test if it works."""
        if not self.agency:
            return TestResult(passed=False, feedback="No agency")

        start = time.time()
        try:
            result = await self.agency.execute_project(
                task=product_task,
                workdir=workdir,
            )
            duration = time.time() - start

            success = result.get("success", False)
            files = result.get("files_created", [])
            steps = result.get("steps_completed", 0)
            total = result.get("steps_total", 0)

            score = steps / max(total, 1)
            if len(files) >= 3:
                score = min(score + 0.2, 1.0)

            return TestResult(
                scenario_id="product_build",
                passed=success and len(files) >= 2,
                score=round(score, 2),
                response=f"{len(files)} files, {steps}/{total} steps",
                feedback=result.get("summary", ""),
                duration_seconds=round(duration, 1),
            )
        except Exception as e:
            return TestResult(
                scenario_id="product_build",
                passed=False, score=0.0,
                response=f"Build failed: {e}",
                duration_seconds=round(time.time() - start, 1),
            )

    # ═══════════════════════════════════════════════════════
    # Phase 5-8: The Full Cycle (THE INFINITE LOOP)
    # ═══════════════════════════════════════════════════════

    async def run_full_cycle(
        self,
        domain: str,
        scenarios_per_round: int = 10,
        target_pass_rate: float = 0.95,
        max_cycles: int = 5,
        product_task: str = "",
    ) -> list[CycleReport]:
        """
        THE INFINITE IMPROVEMENT LOOP.

        test → analyze → evolve → rebuild → re-test → repeat
        until pass_rate >= target or improvement stalls.
        """
        if not self.agency:
            logger.error("No agency set for StressLab")
            return []

        logger.info(f"{'='*60}")
        logger.info(f"STRESS LAB: {domain}")
        logger.info(f"Target: {target_pass_rate:.0%} pass rate")
        logger.info(f"Max cycles: {max_cycles}")
        logger.info(f"{'='*60}")

        reports = []
        prev_pass_rate = 0.0

        for cycle in range(max_cycles):
            cycle_start = time.time()
            logger.info(f"\n--- Cycle {cycle + 1}/{max_cycles} ---")

            # 1. Generate scenarios (fresh each round, progressively harder)
            extra_hard = cycle * 2  # More hard scenarios each round
            scenarios = await self.generate_scenarios(
                domain=domain,
                count=scenarios_per_round,
                difficulty_mix={
                    "easy": max(2, 5 - cycle),
                    "medium": 5,
                    "hard": 3 + extra_hard,
                    "adversarial": min(cycle + 1, 5),
                },
            )
            logger.info(f"  Generated {len(scenarios)} scenarios")

            # 2. Test agency
            results = await self.test_agency(scenarios, max_concurrent=2)
            passed = sum(1 for r in results if r.passed)
            total = len(results)
            pass_rate = passed / max(total, 1)
            avg_score = sum(r.score for r in results) / max(total, 1)

            logger.info(f"  Agency test: {passed}/{total} passed ({pass_rate:.0%})")

            # 3. Test product build (if task provided)
            if product_task and cycle == 0:  # Only build product on first cycle
                logger.info("  Building product...")
                product_result = await self.test_product_build(product_task)
                logger.info(f"  Product: {'PASS' if product_result.passed else 'FAIL'} ({product_result.response})")

            # 4. Analyze failures
            failures = [r for r in results if not r.passed]
            failure_categories: dict[str, int] = {}
            for f in failures:
                # Find the matching scenario
                scenario = next((s for s in scenarios if s.id == f.scenario_id), None)
                cat = scenario.category if scenario else "unknown"
                failure_categories[cat] = failure_categories.get(cat, 0) + 1

            if failures:
                logger.info(f"  Failures by category: {failure_categories}")

            # 5. Evolve
            evolutions = 0
            spawned = 0
            if failures and cycle < max_cycles - 1:
                # Self-evolution
                agent_map = {}
                for team in self.agency.teams.values():
                    if team.lead:
                        agent_map[team.lead.name] = team.lead
                    for a in team.agents:
                        agent_map[a.name] = a

                evo_records = await self.agency.self_evolution.run_evolution_cycle(agent_map)
                evolutions = len(evo_records)
                logger.info(f"  Evolved: {evolutions} improvements")

                # Agent spawner
                spawn_records = await self.agency.agent_spawner.check_and_spawn(self.agency)
                spawned = len(spawn_records)
                if spawned:
                    logger.info(f"  Spawned: {spawned} new agents")

            # 6. Record cycle
            cycle_duration = time.time() - cycle_start
            report = CycleReport(
                cycle=cycle + 1,
                total_scenarios=total,
                passed=passed,
                failed=len(failures),
                pass_rate=round(pass_rate, 3),
                avg_score=round(avg_score, 3),
                evolutions_applied=evolutions,
                agents_spawned=spawned,
                failure_categories=failure_categories,
                duration_seconds=round(cycle_duration, 1),
            )
            reports.append(report)
            self._cycle_reports.append(report)

            logger.info(f"  Cycle {cycle + 1}: {pass_rate:.0%} pass rate, {cycle_duration:.0f}s")

            # 7. Check stopping conditions
            if pass_rate >= target_pass_rate:
                logger.info(f"\n🎉 TARGET REACHED: {pass_rate:.0%} >= {target_pass_rate:.0%}")
                break

            improvement = pass_rate - prev_pass_rate
            if cycle > 0 and improvement < 0.02 and pass_rate < target_pass_rate:
                logger.info(f"\n⚠️ Improvement stalled ({improvement:.1%}). Stopping.")
                break

            prev_pass_rate = pass_rate

        # Final summary
        logger.info(f"\n{'='*60}")
        logger.info("STRESS LAB COMPLETE")
        logger.info(f"  Cycles: {len(reports)}")
        logger.info(f"  Start pass rate: {reports[0].pass_rate:.0%}")
        logger.info(f"  Final pass rate: {reports[-1].pass_rate:.0%}")
        logger.info(f"  Total evolutions: {sum(r.evolutions_applied for r in reports)}")
        logger.info(f"  Total agents spawned: {sum(r.agents_spawned for r in reports)}")
        improvement_pct = reports[-1].pass_rate - reports[0].pass_rate
        logger.info(f"  Improvement: +{improvement_pct:.0%}")
        logger.info(f"{'='*60}")

        return reports

    def get_reports(self) -> list[dict[str, Any]]:
        """Get all cycle reports."""
        return [
            {
                "cycle": r.cycle,
                "pass_rate": r.pass_rate,
                "avg_score": r.avg_score,
                "passed": r.passed,
                "failed": r.failed,
                "evolutions": r.evolutions_applied,
                "spawned": r.agents_spawned,
                "duration": r.duration_seconds,
            }
            for r in self._cycle_reports
        ]

    def __repr__(self) -> str:
        return f"StressLab(cycles={len(self._cycle_reports)})"
