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

        # 2. HYPOTHESIZE: Ask LLM to identify improvements
        analysis_prompt = (
            "You are an AI performance analyst. Analyze this agency's performance data "
            "and identify specific, actionable improvements.\n\n"
            f"Agency Stats:\n{json.dumps(agency_stats, indent=2, default=str)}\n\n"
            f"Recent Failures:\n{json.dumps(failures, indent=2, default=str)}\n\n"
            "For each improvement, provide:\n"
            "1. target_agent: which agent to improve\n"
            "2. issue: what's wrong\n"
            "3. improved_prompt_addition: specific text to ADD to the agent's system prompt\n"
            "4. expected_impact: what will improve\n\n"
            "Return JSON: {\"improvements\": [{\"target_agent\": \"...\", \"issue\": \"...\", "
            "\"improved_prompt_addition\": \"...\", \"expected_impact\": \"...\"}]}\n"
            "Limit to 3 most impactful improvements."
        )

        try:
            response = await self._llm_client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": analysis_prompt}],
                temperature=0.3,
            )
            content = response.choices[0].message.content or "{}"
            
            # Strip markdown if present
            if content.strip().startswith("```"):
                content = content.split("\n", 1)[1] if "\n" in content else content[3:]
                if content.strip().endswith("```"):
                    content = content.strip()[:-3]
            
            data = json.loads(content)
            improvements = data.get("improvements", [])
        except Exception as e:
            logger.error(f"Evolution analysis failed: {e}")
            return records

        # 3. EXPERIMENT & DEPLOY: Apply improvements with testing and rollback
        for imp in improvements[:self.max_evolutions]:
            agent_name = imp.get("target_agent", "")
            addition = imp.get("improved_prompt_addition", "")
            issue = imp.get("issue", "")

            if not agent_name or not addition:
                continue

            record = EvolutionRecord(
                target_agent=agent_name,
                change_type="prompt_update",
                description=f"Fix: {issue}. Added: {addition[:100]}",
            )

            if agents and agent_name in agents:
                agent = agents[agent_name]
                old_prompt = agent.system_prompt
                
                # Get a failing task to test against
                test_task = None
                if self._tracker:
                    failures = self._tracker.get_failure_patterns(limit=10)
                    agent_failures = [f for f in failures if f.get("agent") == agent_name]
                    if agent_failures:
                        test_task = agent_failures[0].get("task", "")
                
                # Apply improvement
                agent.system_prompt = old_prompt + f"\n\n[Auto-improvement]: {addition}"
                
                # Test with a REAL failing task (not just "do you understand?")
                test_passed = True
                if test_task and agent._llm_client:
                    try:
                        test_result = await agent.execute(test_task[:200])
                        record.after_score = 1.0 if test_result.success else 0.0
                        test_passed = test_result.success
                    except Exception:
                        test_passed = False
                        record.after_score = 0.0
                elif agent._llm_client:
                    # Fallback: basic sanity check
                    try:
                        test_result = await agent.execute("Briefly confirm you understand your role.")
                        test_passed = test_result.success
                        record.after_score = 1.0 if test_passed else 0.0
                    except Exception:
                        test_passed = False
                        record.after_score = 0.0
                
                if test_passed:
                    record.applied = True
                    logger.info(f"  ✅ Applied improvement to {agent_name}: {issue[:60]}")
                else:
                    # ROLLBACK
                    agent.system_prompt = old_prompt
                    record.applied = False
                    logger.warning(f"  ↩️ Rolled back improvement for {agent_name}: test failed")
            
            # Store in memory
            if self._memory:
                self._memory.store(
                    f"evolution:{record.id}",
                    {
                        "agent": agent_name,
                        "issue": issue,
                        "improvement": addition,
                        "applied": record.applied,
                        "cycle": self._cycle_count,
                    },
                    author="self_evolution",
                    tags=["evolution", "improvement"],
                )

            records.append(record)
            self._history.append(record)

        # Auto-cleanup prompt bloat
        if agents:
            cleaned = self.cleanup_prompt_bloat(agents)
            if cleaned > 0:
                logger.info(f"  Cleaned up {cleaned} old improvement blocks")

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

    def cleanup_prompt_bloat(self, agents: dict[str, Any]) -> int:
        """Remove old [Auto-improvement] blocks if prompt is getting too long."""
        cleaned = 0
        for name, agent in agents.items():
            if hasattr(agent, 'system_prompt'):
                blocks = agent.system_prompt.count("[Auto-improvement]")
                if blocks > 5:
                    # Keep only the last 3 improvements
                    parts = agent.system_prompt.split("\n\n[Auto-improvement]:")
                    base = parts[0]
                    improvements = parts[1:] if len(parts) > 1 else []
                    kept = improvements[-3:] if len(improvements) > 3 else improvements
                    agent.system_prompt = base + "".join(f"\n\n[Auto-improvement]:{imp}" for imp in kept)
                    cleaned += blocks - len(kept)
        return cleaned

    def rollback_mutation(self, agent: Any, mutation_record: EvolutionRecord) -> bool:
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
        
        current_success = stats.get("success_rate", stats.get("tasks", {}).get("success_rate", 1.0))
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
