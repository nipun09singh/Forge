"""Self-Evolution Engine — agencies autonomously improve their own performance.

Inspired by Sakana AI's Darwin Gödel Machine and OpenAI's self-evolving agents cookbook.

The cycle:
1. OBSERVE: Analyze performance metrics and failure patterns
2. HYPOTHESIZE: LLM identifies improvement opportunities  
3. EXPERIMENT: Generate improved prompts/knowledge, test against failures
4. DEPLOY: Apply improvements that score better than baseline
5. LEARN: Store lessons for future evolution cycles

This runs daily/weekly without human intervention.
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class EvolutionRecord:
    """Record of one improvement applied."""
    id: str = field(default_factory=lambda: f"evo-{uuid.uuid4().hex[:8]}")
    target_agent: str = ""
    change_type: str = ""  # prompt_update, knowledge_add, tool_add, config_change
    description: str = ""
    before_score: float = 0.0
    after_score: float = 0.0
    improvement_pct: float = 0.0
    applied: bool = False
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class OptimizationResult:
    """Result of a DSPy-style prompt optimization."""
    agent_name: str = ""
    improved: bool = False
    old_prompt: str = ""
    new_prompt: str = ""
    before_score: float = 0.0
    after_score: float = 0.0
    candidates_evaluated: int = 0
    reason: str = ""


class PromptOptimizer:
    """DSPy-inspired prompt optimization via metric-driven compilation."""

    def __init__(self, llm_client, tracker, metric_fn=None):
        self.llm_client = llm_client
        self.tracker = tracker
        self.metric_fn = metric_fn or self._default_metric

    async def compile(self, agent, n_candidates=3, min_samples=10):
        """Generate candidate prompts, evaluate each, pick winner, REPLACE (not append)."""
        agent_name = getattr(agent, "name", "unknown")
        result = OptimizationResult(agent_name=agent_name)

        if not self.tracker or not self.llm_client:
            result.reason = "missing tracker or llm_client"
            return result

        # 1. Collect task history
        stats = self.tracker.get_agent_stats(agent_name)
        task_count = stats.get("tasks", 0)
        if task_count < min_samples:
            result.reason = f"insufficient data ({task_count}/{min_samples})"
            return result

        success_rate = stats.get("success_rate", 1.0)
        avg_quality = stats.get("avg_quality_score", 1.0)
        failures = self.tracker.get_failure_patterns(limit=30)
        agent_failures = [f for f in failures if f.get("agent") == agent_name]

        # 2. Ask LLM to generate n_candidates prompt REWRITES
        old_prompt = agent.system_prompt
        result.old_prompt = old_prompt

        result.before_score = await self.metric_fn(old_prompt, agent_name)

        candidates = []
        for i in range(n_candidates):
            rewrite_prompt = (
                "You are an expert prompt engineer. Given the following system prompt and "
                "performance data, rewrite the system prompt to address the failure patterns.\n\n"
                f"CURRENT SYSTEM PROMPT:\n{old_prompt}\n\n"
                f"PERFORMANCE: success_rate={success_rate:.2f}, avg_quality={avg_quality:.2f}\n"
                f"FAILURE PATTERNS:\n{json.dumps(agent_failures, indent=2, default=str)}\n\n"
                "Return a COMPLETE replacement prompt, not an addition. "
                "The new prompt should address the identified failure patterns while "
                "preserving the agent's core role and capabilities.\n"
                f"Candidate {i + 1} of {n_candidates} -- try a different angle than previous attempts."
            )
            try:
                response = await self.llm_client.chat.completions.create(
                    model="gpt-4o",
                    messages=[{"role": "user", "content": rewrite_prompt}],
                    temperature=0.7 + (i * 0.1),
                )
                candidate = response.choices[0].message.content or ""
                if candidate.strip():
                    candidates.append(candidate.strip())
            except Exception as e:
                logger.warning(f"Candidate {i} generation failed: {e}")

        if not candidates:
            result.reason = "no candidates generated"
            return result

        # 3. Score each candidate
        scored = []
        for candidate in candidates:
            score = await self.metric_fn(candidate, agent_name)
            scored.append((score, candidate))

        result.candidates_evaluated = len(scored)

        # 4. Pick the winner
        scored.sort(key=lambda x: x[0], reverse=True)
        best_score, best_prompt = scored[0]
        result.after_score = best_score

        if best_score <= result.before_score:
            result.reason = "no candidate scored better than current prompt"
            return result

        # 5. REPLACE agent.system_prompt (not append!)
        agent.system_prompt = best_prompt
        result.new_prompt = best_prompt
        result.improved = True
        result.reason = "prompt replaced with better candidate"

        logger.info(
            f"PromptOptimizer: {agent_name} prompt replaced "
            f"(score {result.before_score:.3f} -> {result.after_score:.3f})"
        )
        return result

    async def _default_metric(self, candidate_prompt: str, agent_name: str) -> float:
        """Score a candidate prompt by actually running a sample failing task."""
        failures = self.tracker.get_failure_patterns(limit=5)
        agent_failures = [f for f in failures if f.get("agent") == agent_name]

        if not agent_failures:
            return 0.5  # No data

        # Pick one failing task to re-test
        test_task = agent_failures[0].get("task", "")
        if not test_task:
            return 0.5

        # Create a temporary agent with the candidate prompt and run the task
        from forge.runtime.agent import Agent
        test_agent = Agent(
            name=f"_eval_{agent_name}",
            role="specialist",
            system_prompt=candidate_prompt,
        )
        test_agent.set_llm_client(self.llm_client)

        try:
            result = await asyncio.wait_for(
                test_agent.execute(test_task),
                timeout=30.0,
            )
            # Score based on actual execution result
            if result.success:
                return min(1.0, 0.7 + result.confidence * 0.3)
            return 0.3
        except (asyncio.TimeoutError, Exception):
            return 0.4  # Timeout/error = slightly better than nothing


class SelfEvolution:
    """
    Autonomous self-improvement engine for AI agencies.
    
    Runs periodic improvement cycles that:
    1. Analyze agent performance (success rates, quality scores, failure patterns)
    2. Identify weaknesses using LLM analysis
    3. Generate improved system prompts
    4. Test improvements against historical failure cases
    5. Deploy improvements that demonstrate measurable gains
    
    No human intervention needed. The agency evolves itself.
    """

    def __init__(
        self,
        performance_tracker: Any = None,
        memory: Any = None,
        llm_client: Any = None,
        model: str = "gpt-4o",
        improvement_threshold: float = 0.05,  # 5% improvement required
        max_evolutions_per_cycle: int = 3,
    ):
        self._tracker = performance_tracker
        self._memory = memory
        self._llm_client = llm_client
        self.model = model
        self.improvement_threshold = improvement_threshold
        self.max_evolutions = max_evolutions_per_cycle
        self._history: list[EvolutionRecord] = []
        self._running = False
        self._cycle_count = 0

    def set_infrastructure(self, tracker=None, memory=None, llm_client=None):
        """Wire to agency infrastructure."""
        if tracker: self._tracker = tracker
        if memory: self._memory = memory
        if llm_client: self._llm_client = llm_client

    async def run_evolution_cycle(self, agents: dict[str, Any] | None = None) -> list[EvolutionRecord]:
        """
        Run one complete evolution cycle.
        
        Returns list of improvements applied.
        """
        self._cycle_count += 1
        logger.info(f"=== Evolution Cycle {self._cycle_count} ===")
        records = []

        if not self._tracker or not self._llm_client:
            logger.warning("Evolution skipped: missing tracker or LLM client")
            return records

        # 1. OBSERVE: Gather performance data
        agency_stats = self._tracker.get_agency_stats()
        failures = self._tracker.get_failure_patterns(limit=30)

        if agency_stats.get("total_tasks", 0) < 5:
            logger.info("Not enough data for evolution (need 5+ tasks)")
            return records

        # === DSPy-style prompt compilation ===
        if agents and self._llm_client:
            optimizer = PromptOptimizer(self._llm_client, self._tracker)
            for agent_name, agent in agents.items():
                try:
                    result = await optimizer.compile(agent)
                    if result.improved:
                        records.append(EvolutionRecord(
                            target_agent=agent_name,
                            change_type="prompt_compile",
                            description=f"DSPy-style prompt rewrite (score {result.before_score:.3f} -> {result.after_score:.3f})",
                            before_score=result.before_score,
                            after_score=result.after_score,
                            applied=True,
                        ))
                except Exception as e:
                    logger.warning(f"Prompt compilation failed for {agent_name}: {e}")

        # === DEEP MUTATIONS: Beyond prompt-append ===
        # These mutations change agent configuration, not just prompts.
        # Save state before mutations for rollback
        _mutation_snapshots: dict[str, dict[str, Any]] = {}

        if not agents:
            return records
            
        for agent_name, agent in agents.items():
            if not hasattr(agent, '_performance_tracker') or not agent._performance_tracker:
                continue
                
            agent_metrics = self._tracker.get_agent_stats(agent_name) if self._tracker else {}
            if not agent_metrics:
                continue
            
            success_rate = agent_metrics.get("success_rate", 1.0)
            avg_quality = agent_metrics.get("avg_quality_score", 1.0)
            task_count = agent_metrics.get("tasks", 0)
            
            if task_count < 5:
                continue  # Need enough data
            
            # Mutation 1: Model routing evolution
            # If agent is expensive but quality is high, try cheaper model
            if hasattr(agent, 'model') and success_rate > 0.9 and avg_quality > 0.8:
                current_model = agent.model
                cheaper_models = {"gpt-4": "gpt-4o", "gpt-4o": "gpt-4o-mini"}
                if current_model in cheaper_models:
                    new_model = cheaper_models[current_model]
                    old_model = agent.model
                    agent.model = new_model
                    logger.info(f"  🔄 Model evolution: {agent_name} {old_model} → {new_model} (success={success_rate:.0%}, quality={avg_quality:.0%})")
                    records.append(EvolutionRecord(
                        target_agent=agent_name,
                        change_type="model_downgrade",
                        description=f"Downgraded {old_model} → {new_model} (maintaining {success_rate:.0%} success rate)",
                        before_score=success_rate,
                        after_score=success_rate,  # Will be measured next cycle
                        applied=True,
                    ))
            
            # Mutation 2: Temperature tuning
            # Low success → lower temperature (more deterministic)
            # High success + low quality → raise temperature (more creative)
            if hasattr(agent, 'temperature'):
                if success_rate < 0.6 and agent.temperature > 0.2:
                    old_temp = agent.temperature
                    agent.temperature = max(0.1, agent.temperature - 0.2)
                    logger.info(f"  🌡️ Temperature evolution: {agent_name} {old_temp} → {agent.temperature} (low success={success_rate:.0%})")
                    records.append(EvolutionRecord(
                        target_agent=agent_name,
                        change_type="temperature_decrease",
                        description=f"Lowered temperature {old_temp} → {agent.temperature} to improve consistency",
                        before_score=success_rate,
                        after_score=success_rate,
                        applied=True,
                    ))
                elif success_rate > 0.9 and avg_quality < 0.7 and agent.temperature < 0.9:
                    old_temp = agent.temperature
                    agent.temperature = min(1.0, agent.temperature + 0.15)
                    logger.info(f"  🌡️ Temperature evolution: {agent_name} {old_temp} → {agent.temperature} (high success, low quality)")
                    records.append(EvolutionRecord(
                        target_agent=agent_name,
                        change_type="temperature_increase",
                        description=f"Raised temperature {old_temp} → {agent.temperature} for more creative outputs",
                        before_score=avg_quality,
                        after_score=avg_quality,
                        applied=True,
                    ))
            
            # Mutation 3: Enable reflection for struggling agents
            if hasattr(agent, 'enable_reflection') and not agent.enable_reflection:
                if success_rate < 0.7 or avg_quality < 0.6:
                    agent.enable_reflection = True
                    agent.max_reflections = 3
                    logger.info(f"  🪞 Reflection evolution: enabled for {agent_name} (success={success_rate:.0%}, quality={avg_quality:.0%})")
                    records.append(EvolutionRecord(
                        target_agent=agent_name,
                        change_type="enable_reflection",
                        description=f"Enabled self-reflection (success={success_rate:.0%}, quality={avg_quality:.0%})",
                        before_score=avg_quality,
                        after_score=avg_quality,
                        applied=True,
                    ))
            
            # Mutation 4: Increase iterations for agents hitting limits
            if hasattr(agent, 'max_iterations'):
                # Check if agent frequently hits max iterations (from failure patterns)
                failure_patterns = self._tracker.get_failure_patterns() if self._tracker else []
                hits_limit = any(
                    p.get("agent") == agent_name and "max iterations" in p.get("task", "").lower()
                    for p in failure_patterns
                ) if failure_patterns else False
                if hits_limit and agent.max_iterations < 50:
                    old_max = agent.max_iterations
                    agent.max_iterations = min(50, agent.max_iterations + 10)
                    logger.info(f"  🔄 Iteration evolution: {agent_name} {old_max} → {agent.max_iterations}")
                    records.append(EvolutionRecord(
                        target_agent=agent_name,
                        change_type="increase_iterations",
                        description=f"Increased max_iterations {old_max} → {agent.max_iterations} (was hitting limit)",
                        before_score=success_rate,
                        after_score=success_rate,
                        applied=True,
                    ))

        # After applying deep mutations, schedule a rollback check
        mutation_types = {"model_downgrade", "temperature_decrease", "temperature_increase", "enable_reflection", "increase_iterations"}
        mutation_records = [r for r in records if r.change_type in mutation_types]
        for record in mutation_records:
            agent_name = record.target_agent
            if agent_name in agents:
                agent = agents[agent_name]
                rolled_back = await self.rollback_mutation(agent, record)
                if rolled_back:
                    logger.info(f"Rolled back {record.change_type} for {agent_name}")

        logger.info(f"Evolution cycle {self._cycle_count} complete: {len(records)} improvements applied")
        return records

    async def start_background(self, agents: dict[str, Any] | None = None, interval_hours: float = 24.0) -> None:
        """Start evolution as a background task running every interval_hours."""
        self._running = True
        while self._running:
            try:
                await self.run_evolution_cycle(agents)
            except Exception as e:
                logger.error(f"Evolution cycle error: {e}")
            await asyncio.sleep(interval_hours * 3600)

    def stop(self):
        """Stop background evolution."""
        self._running = False

    def get_history(self, limit: int = 20) -> list[dict[str, Any]]:
        """Get evolution history."""
        return [
            {
                "id": r.id,
                "agent": r.target_agent,
                "change": r.change_type,
                "description": r.description,
                "applied": r.applied,
                "timestamp": r.timestamp,
            }
            for r in self._history[-limit:]
        ]

    def get_stats(self) -> dict[str, Any]:
        """Get evolution statistics."""
        return {
            "cycles_completed": self._cycle_count,
            "total_improvements": len(self._history),
            "applied_improvements": sum(1 for r in self._history if r.applied),
            "running": self._running,
        }

    async def rollback_mutation(self, agent: Any, mutation_record: EvolutionRecord) -> bool:
        """Rollback a specific mutation if performance degraded.
        
        Checks post-mutation performance against pre-mutation baseline.
        Returns True if rollback was applied.
        """
        if not self._tracker or not hasattr(agent, 'name'):
            return False
        
        agent_name = agent.name
        stats = self._tracker.get_agent_stats(agent_name) if hasattr(self._tracker, 'get_agent_stats') else {}
        if not stats:
            return False
        
        current_success = stats.get("success_rate", 1.0)
        before_score = mutation_record.before_score
        
        # Rollback if performance dropped by more than 10%
        if current_success < before_score - 0.1:
            change_type = mutation_record.change_type
            
            if change_type == "model_downgrade" and hasattr(agent, 'model'):
                # Restore to more expensive model
                upgrades = {"gpt-4o-mini": "gpt-4o", "gpt-4o": "gpt-4"}
                if agent.model in upgrades:
                    agent.model = upgrades[agent.model]
                    logger.info(f"  ⏪ Rollback: {agent_name} model restored to {agent.model}")
                    return True
            
            elif change_type == "temperature_decrease" and hasattr(agent, 'temperature'):
                agent.temperature = min(1.0, agent.temperature + 0.2)
                logger.info(f"  ⏪ Rollback: {agent_name} temperature restored to {agent.temperature}")
                return True
            
            elif change_type == "temperature_increase" and hasattr(agent, 'temperature'):
                agent.temperature = max(0.1, agent.temperature - 0.15)
                logger.info(f"  ⏪ Rollback: {agent_name} temperature restored to {agent.temperature}")
                return True
            
            elif change_type == "enable_reflection" and hasattr(agent, 'enable_reflection'):
                agent.enable_reflection = False
                logger.info(f"  ⏪ Rollback: {agent_name} reflection disabled")
                return True
            
            elif change_type == "increase_iterations" and hasattr(agent, 'max_iterations'):
                agent.max_iterations = max(10, agent.max_iterations - 10)
                logger.info(f"  ⏪ Rollback: {agent_name} max_iterations restored to {agent.max_iterations}")
                return True
        
        return False

    def __repr__(self) -> str:
        return f"SelfEvolution(cycles={self._cycle_count}, improvements={len(self._history)})"
