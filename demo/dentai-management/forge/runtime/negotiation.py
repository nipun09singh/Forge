"""Multi-agent negotiation — agents debate and reach consensus on decisions."""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from forge.runtime.agent import Agent

logger = logging.getLogger(__name__)


class Vote(str, Enum):
    APPROVE = "approve"
    REJECT = "reject"
    ABSTAIN = "abstain"


@dataclass
class Stance:
    """An agent's position on a decision."""
    agent_name: str
    vote: Vote
    confidence: float = 0.5  # 0.0 to 1.0
    reasoning: str = ""


@dataclass
class NegotiationRound:
    """One round of debate."""
    round_number: int
    stances: list[Stance] = field(default_factory=list)
    consensus_reached: bool = False
    consensus_threshold: float = 0.75


@dataclass
class NegotiationResult:
    """Final outcome of a negotiation."""
    id: str = field(default_factory=lambda: f"neg-{uuid.uuid4().hex[:8]}")
    topic: str = ""
    decision: str = ""  # "approved", "rejected", "escalated"
    rounds: list[NegotiationRound] = field(default_factory=list)
    final_vote_tally: dict[str, int] = field(default_factory=dict)
    total_rounds: int = 0
    consensus_reached: bool = False
    escalated_to_human: bool = False
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "topic": self.topic,
            "decision": self.decision,
            "total_rounds": self.total_rounds,
            "consensus_reached": self.consensus_reached,
            "escalated_to_human": self.escalated_to_human,
            "vote_tally": self.final_vote_tally,
        }


class NegotiationEngine:
    """
    Enables agents to debate high-stakes decisions before committing.
    
    Process:
    1. Present topic to all participating agents
    2. Each agent votes (Approve/Reject/Abstain) with confidence + reasoning
    3. If consensus >= threshold: execute the decision
    4. If no consensus after max_rounds: escalate to human
    5. Log everything for audit trail
    """

    def __init__(self, consensus_threshold: float = 0.75, max_rounds: int = 3):
        self.consensus_threshold = consensus_threshold
        self.max_rounds = max_rounds
        self._history: list[NegotiationResult] = []

    async def negotiate(
        self,
        topic: str,
        proposal: str,
        agents: list[Any],  # Agent instances
        context: dict[str, Any] | None = None,
    ) -> NegotiationResult:
        """Run a multi-agent negotiation on a decision."""
        logger.info(f"Starting negotiation: {topic[:80]}...")
        
        result = NegotiationResult(topic=topic)
        prev_stances_text = ""

        for round_num in range(self.max_rounds):
            round_data = NegotiationRound(
                round_number=round_num + 1,
                consensus_threshold=self.consensus_threshold,
            )

            # Each agent deliberates and votes
            tasks = []
            for agent in agents:
                prompt = self._build_deliberation_prompt(
                    topic, proposal, round_num, prev_stances_text, context
                )
                tasks.append(self._get_agent_stance(agent, prompt))

            stances = await asyncio.gather(*tasks, return_exceptions=True)

            for stance in stances:
                if isinstance(stance, Stance):
                    round_data.stances.append(stance)
                elif isinstance(stance, Exception):
                    logger.warning(f"Agent failed to vote: {stance}")

            # Check for consensus
            votes = {"approve": 0, "reject": 0, "abstain": 0}
            total_confidence = 0.0
            for s in round_data.stances:
                votes[s.vote.value] += 1
                total_confidence += s.confidence

            total_votes = votes["approve"] + votes["reject"]  # Abstains don't count
            if total_votes > 0:
                approve_ratio = votes["approve"] / total_votes
                if approve_ratio >= self.consensus_threshold:
                    round_data.consensus_reached = True
                    result.decision = "approved"
                elif (1 - approve_ratio) >= self.consensus_threshold:
                    round_data.consensus_reached = True
                    result.decision = "rejected"

            result.rounds.append(round_data)
            result.final_vote_tally = votes

            if round_data.consensus_reached:
                result.consensus_reached = True
                result.total_rounds = round_num + 1
                logger.info(f"Consensus reached in round {round_num + 1}: {result.decision}")
                break

            # Build context for next round
            prev_stances_text = "\n".join(
                f"- {s.agent_name}: {s.vote.value} (confidence: {s.confidence:.0%}) — {s.reasoning[:100]}"
                for s in round_data.stances
            )

        if not result.consensus_reached:
            result.decision = "escalated"
            result.escalated_to_human = True
            result.total_rounds = self.max_rounds
            logger.info(f"No consensus after {self.max_rounds} rounds — escalating to human")

        self._history.append(result)
        return result

    async def _get_agent_stance(self, agent: Any, prompt: str) -> Stance:
        """Get a single agent's vote on the topic."""
        try:
            task_result = await agent.execute(prompt)
            output = task_result.output.lower()

            # Parse vote from output
            if "approve" in output or "agree" in output or "yes" in output:
                vote = Vote.APPROVE
            elif "reject" in output or "disagree" in output or "no" in output:
                vote = Vote.REJECT
            else:
                vote = Vote.ABSTAIN

            # Parse confidence (look for percentage or decimal)
            confidence = 0.7  # Default
            import re
            conf_match = re.search(r'confidence[:\s]*(\d+)%', output)
            if conf_match:
                confidence = int(conf_match.group(1)) / 100.0
            else:
                conf_match = re.search(r'confidence[:\s]*(0\.\d+)', output)
                if conf_match:
                    confidence = float(conf_match.group(1))

            return Stance(
                agent_name=agent.name,
                vote=vote,
                confidence=min(max(confidence, 0.0), 1.0),
                reasoning=task_result.output[:300],
            )
        except Exception as e:
            return Stance(agent_name=getattr(agent, 'name', 'unknown'), vote=Vote.ABSTAIN, reasoning=f"Error: {e}")

    def _build_deliberation_prompt(
        self, topic: str, proposal: str, round_num: int,
        prev_stances: str, context: dict | None,
    ) -> str:
        prompt = (
            f"DECISION REQUIRED — Round {round_num + 1}\n\n"
            f"Topic: {topic}\n"
            f"Proposal: {proposal}\n\n"
        )
        if context:
            prompt += f"Context: {json.dumps(context, default=str)[:500]}\n\n"
        if prev_stances:
            prompt += f"Previous round's positions:\n{prev_stances}\n\n"
        prompt += (
            "Please deliberate and state your position:\n"
            "1. Your vote: APPROVE, REJECT, or ABSTAIN\n"
            "2. Your confidence level (0-100%)\n"
            "3. Your reasoning (2-3 sentences)\n"
        )
        return prompt

    def get_history(self, limit: int = 20) -> list[dict]:
        """Get negotiation history."""
        return [r.to_dict() for r in self._history[-limit:]]

    def __repr__(self) -> str:
        return f"NegotiationEngine(threshold={self.consensus_threshold}, history={len(self._history)})"
