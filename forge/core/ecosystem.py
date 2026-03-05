"""Forge Ecosystem — cross-agency intelligence transfer and compound learning.

The Level 5 capability: when one agency learns something, ALL agencies benefit.

Example:
  Dental agency discovers a great complaint-handling prompt → 
  Ecosystem adapts it for restaurant agency → 
  Restaurant complaint resolution improves 12%

This creates a network effect: more agencies = smarter agencies = more value.
This is the moat that competitors cannot replicate without the same volume.
"""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class Insight:
    """A transferable insight from one agency to another."""
    id: str = field(default_factory=lambda: f"insight-{uuid.uuid4().hex[:8]}")
    source_domain: str = ""
    source_agent: str = ""
    insight_type: str = ""  # prompt_improvement, failure_pattern, knowledge, workflow
    description: str = ""
    original_context: str = ""
    improvement_data: dict[str, Any] = field(default_factory=dict)
    transferable_to: list[str] = field(default_factory=list)  # target domains
    applied_count: int = 0
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class CrossPollination:
    """Record of applying an insight from one domain to another."""
    id: str = field(default_factory=lambda: f"xpol-{uuid.uuid4().hex[:8]}")
    insight_id: str = ""
    source_domain: str = ""
    target_domain: str = ""
    adaptation: str = ""
    success: bool = False
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class ForgeEcosystem:
    """
    Cross-agency intelligence transfer system.
    
    Observes performance across ALL generated agencies, identifies
    transferable improvements, adapts them across domains, and
    applies them — making every agency smarter when any agency learns.
    
    This is Forge's ultimate moat: a network of self-improving AI
    workforces that compound each other's intelligence.
    """

    def __init__(self, data_dir: str = "./ecosystem"):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self._insights: list[Insight] = []
        self._pollinations: list[CrossPollination] = []
        self._agency_registry: dict[str, dict[str, Any]] = {}
        self._load_insights()

    def register_agency(self, agency_id: str, domain: str, metadata: dict | None = None) -> None:
        """Register an agency in the ecosystem."""
        self._agency_registry[agency_id] = {
            "domain": domain,
            "registered_at": datetime.now(timezone.utc).isoformat(),
            "metadata": metadata or {},
        }
        logger.info(f"Ecosystem: registered agency '{agency_id}' (domain: {domain})")

    def contribute_insight(
        self,
        source_domain: str,
        source_agent: str,
        insight_type: str,
        description: str,
        improvement_data: dict[str, Any] | None = None,
    ) -> Insight:
        """
        Contribute an insight from an agency's learning.
        
        Called when an agency's self-evolution discovers something useful.
        """
        # Determine which domains this insight might transfer to
        universal_types = ["complaint_handling", "onboarding", "scheduling", "billing", "retention"]
        transferable = []
        desc_lower = description.lower()
        for domain_id, info in self._agency_registry.items():
            if info["domain"] != source_domain:
                transferable.append(info["domain"])

        insight = Insight(
            source_domain=source_domain,
            source_agent=source_agent,
            insight_type=insight_type,
            description=description,
            improvement_data=improvement_data or {},
            transferable_to=transferable,
        )
        self._insights.append(insight)

        logger.info(f"Ecosystem: new insight from {source_domain}/{source_agent} — transferable to {len(transferable)} domains")
        self._save_insights()
        return insight

    async def cross_pollinate(
        self,
        insight: Insight,
        target_domain: str,
        llm_client: Any = None,
        model: str = "gpt-4o",
    ) -> CrossPollination:
        """
        Adapt an insight from one domain to another.
        
        Uses LLM to translate context-specific learnings into
        domain-appropriate improvements.
        """
        if not llm_client:
            return CrossPollination(
                insight_id=insight.id,
                source_domain=insight.source_domain,
                target_domain=target_domain,
                success=False,
                adaptation="No LLM client available",
            )

        prompt = (
            f"An AI agency in the '{insight.source_domain}' domain discovered this improvement:\n"
            f"  Agent: {insight.source_agent}\n"
            f"  Insight: {insight.description}\n"
            f"  Data: {json.dumps(insight.improvement_data, default=str)[:500]}\n\n"
            f"Adapt this insight for the '{target_domain}' domain.\n"
            f"How would you apply the same principle in a different business context?\n\n"
            f"Return JSON: {{\"applicable\": true/false, \"adapted_insight\": \"...\", "
            f"\"recommended_prompt_addition\": \"...\"}}"
        )

        try:
            response = await llm_client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.4,
            )
            content = response.choices[0].message.content or "{}"
            if content.strip().startswith("```"):
                content = content.split("\n", 1)[1] if "\n" in content else content[3:]
                if content.strip().endswith("```"):
                    content = content.strip()[:-3]

            data = json.loads(content)
            applicable = data.get("applicable", False)

            record = CrossPollination(
                insight_id=insight.id,
                source_domain=insight.source_domain,
                target_domain=target_domain,
                adaptation=data.get("adapted_insight", ""),
                success=applicable,
            )
            self._pollinations.append(record)

            if applicable:
                insight.applied_count += 1
                logger.info(f"Ecosystem: cross-pollinated from {insight.source_domain} → {target_domain}")
            
            return record

        except Exception as e:
            logger.error(f"Cross-pollination failed: {e}")
            return CrossPollination(
                insight_id=insight.id, source_domain=insight.source_domain,
                target_domain=target_domain, success=False,
                adaptation=f"Error: {e}",
            )

    async def apply_insight_to_agency(
        self,
        insight: Insight,
        target_agents: dict[str, Any],
        llm_client: Any = None,
        target_domain: str = "",
    ) -> bool:
        """
        Actually APPLY an insight to agents in a target agency.
        
        This closes the loop: detect insight → adapt → APPLY → verify.
        """
        if not target_domain:
            return False
        
        # Cross-pollinate to get adapted text
        pollination = await self.cross_pollinate(insight, target_domain, llm_client)
        
        if not pollination.success or not pollination.adaptation:
            return False
        
        # Apply to matching agents
        applied = False
        for agent_name, agent in target_agents.items():
            if hasattr(agent, 'system_prompt'):
                agent.system_prompt += f"\n\n[Cross-domain insight from {insight.source_domain}]: {pollination.adaptation[:300]}"
                applied = True
                logger.info(f"Ecosystem: applied insight to {agent_name} in {target_domain}")
        
        return applied

    def get_insights_for_domain(self, domain: str) -> list[Insight]:
        """Get insights that are transferable to a specific domain."""
        return [i for i in self._insights if domain in i.transferable_to or not i.transferable_to]

    def get_stats(self) -> dict[str, Any]:
        """Get ecosystem statistics."""
        return {
            "total_agencies": len(self._agency_registry),
            "total_insights": len(self._insights),
            "total_cross_pollinations": len(self._pollinations),
            "successful_transfers": sum(1 for p in self._pollinations if p.success),
            "domains": list(set(info["domain"] for info in self._agency_registry.values())),
            "insight_types": list(set(i.insight_type for i in self._insights)),
        }

    def _save_insights(self) -> None:
        """Persist insights to disk."""
        try:
            data = [
                {
                    "id": i.id, "source_domain": i.source_domain,
                    "source_agent": i.source_agent, "type": i.insight_type,
                    "description": i.description, "applied_count": i.applied_count,
                }
                for i in self._insights
            ]
            (self.data_dir / "insights.json").write_text(
                json.dumps(data, indent=2), encoding="utf-8"
            )
        except Exception as e:
            logger.warning(f"Failed to save insights: {e}")

    def _load_insights(self) -> None:
        """Load insights from disk on initialization."""
        insights_file = self.data_dir / "insights.json"
        if insights_file.exists():
            try:
                data = json.loads(insights_file.read_text(encoding="utf-8"))
                for item in data:
                    self._insights.append(Insight(
                        id=item.get("id", ""),
                        source_domain=item.get("source_domain", ""),
                        source_agent=item.get("source_agent", ""),
                        insight_type=item.get("type", ""),
                        description=item.get("description", ""),
                        applied_count=item.get("applied_count", 0),
                    ))
                logger.info(f"Loaded {len(self._insights)} insights from disk")
            except Exception as e:
                logger.warning(f"Failed to load insights: {e}")

    def __repr__(self) -> str:
        return (f"ForgeEcosystem(agencies={len(self._agency_registry)}, "
                f"insights={len(self._insights)}, transfers={len(self._pollinations)})")
