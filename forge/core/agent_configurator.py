"""Agent Configurator — maps domain requirements to primitive compositions.

Given a domain (e.g., "customer support") and an agent role (e.g., "technical support"),
this module selects the right planner, executor, critic, memory config, tools, and
escalation policy. This is what makes each agent GENUINELY specialized, not just
a different prompt on the same architecture.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class AgentConfig:
    """Complete primitive configuration for an agent."""
    # Planner
    planner_type: str = "simple"  # simple, sequential, dag, classify_and_route
    planner_max_steps: int = 10

    # Executor
    executor_type: str = "react"  # single_shot, react, multi_step
    max_iterations: int = 15

    # Critic
    critic_type: str = "scored"   # binary, scored, factual, compliance
    critic_min_score: float = 0.7
    critic_criteria: str = ""
    compliance_rules: list[str] = field(default_factory=list)
    knowledge_source: str = ""

    # Memory
    memory_type: str = "working"  # none, short_term, working, episodic
    
    # Tools (names of tools this agent should have access to)
    tools: list[str] = field(default_factory=list)
    
    # Escalation
    escalation_chain: list[str] = field(default_factory=lambda: ["retry:3", "different_model:2", "human:1"])
    
    # Model preferences
    preferred_model: str = ""  # Override agency default
    temperature: float = 0.7

    def to_dict(self) -> dict[str, Any]:
        """Serialize for blueprint storage."""
        return {
            "planner_type": self.planner_type,
            "executor_type": self.executor_type,
            "max_iterations": self.max_iterations,
            "critic_type": self.critic_type,
            "critic_min_score": self.critic_min_score,
            "memory_type": self.memory_type,
            "tools": self.tools,
            "escalation_chain": self.escalation_chain,
            "temperature": self.temperature,
        }


# ═══════════════════════════════════════════════════════════
# Role-based default configurations
# ═══════════════════════════════════════════════════════════

ROLE_CONFIGS: dict[str, AgentConfig] = {
    # ─── Management roles ─────────────────────────────────
    "manager": AgentConfig(
        planner_type="dag",
        executor_type="react",
        max_iterations=20,
        critic_type="scored",
        critic_min_score=0.8,
        memory_type="working",
        tools=["query_database", "send_email"],
        temperature=0.5,
    ),
    "coordinator": AgentConfig(
        planner_type="classify_and_route",
        executor_type="react",
        max_iterations=10,
        critic_type="binary",
        memory_type="working",
        tools=["classify_request", "route_to_team", "track_request"],
        temperature=0.4,
    ),

    # ─── Specialist roles ─────────────────────────────────
    "specialist": AgentConfig(
        planner_type="sequential",
        executor_type="react",
        max_iterations=15,
        critic_type="scored",
        critic_min_score=0.7,
        memory_type="episodic",
        tools=["query_database", "http_request", "read_write_file", "run_command"],
        temperature=0.5,
    ),
    "researcher": AgentConfig(
        planner_type="dag",
        executor_type="react",
        max_iterations=20,
        critic_type="factual",
        memory_type="episodic",
        tools=["http_request", "query_database", "read_write_file"],
        temperature=0.6,
    ),

    # ─── Support roles ────────────────────────────────────
    "support": AgentConfig(
        planner_type="simple",
        executor_type="react",
        max_iterations=10,
        critic_type="scored",
        critic_min_score=0.7,
        memory_type="episodic",
        tools=["query_database", "send_email"],
        temperature=0.6,
    ),

    # ─── Quality roles ────────────────────────────────────
    "reviewer": AgentConfig(
        planner_type="simple",
        executor_type="single_shot",
        max_iterations=5,
        critic_type="scored",
        critic_min_score=0.9,
        critic_criteria="accuracy, completeness, factual correctness, professionalism",
        memory_type="working",
        tools=["score_output", "log_quality_result"],
        temperature=0.3,
    ),

    # ─── Analyst roles ────────────────────────────────────
    "analyst": AgentConfig(
        planner_type="sequential",
        executor_type="react",
        max_iterations=15,
        critic_type="scored",
        memory_type="working",
        tools=["query_metrics", "generate_report", "query_database"],
        temperature=0.4,
    ),

    # ─── Writer roles ─────────────────────────────────────
    "writer": AgentConfig(
        planner_type="sequential",
        executor_type="react",
        max_iterations=10,
        critic_type="scored",
        critic_min_score=0.8,
        critic_criteria="clarity, engagement, accuracy, tone",
        memory_type="short_term",
        tools=["read_write_file", "http_request"],
        temperature=0.8,
    ),
}


# ═══════════════════════════════════════════════════════════
# Domain-specific overrides
# ═══════════════════════════════════════════════════════════

DOMAIN_OVERRIDES: dict[str, dict[str, Any]] = {
    "customer_support": {
        "specialist": {
            "critic_type": "factual",
            "knowledge_source": "company_docs",
            "escalation_chain": ["retry:3", "human:1"],
            "tools": ["query_database", "send_email", "http_request"],
        },
        "support": {
            "planner_type": "classify_and_route",
            "critic_type": "compliance",
            "compliance_rules": [
                "MUST: acknowledge the customer's issue",
                "MUST: provide a solution or next step",
                "NEVER: share internal system details",
                "NEVER: make promises about timelines without checking",
            ],
        },
    },
    "software_development": {
        "specialist": {
            "executor_type": "react",
            "max_iterations": 25,
            "tools": ["read_write_file", "run_command", "http_request", "query_database"],
            "critic_type": "binary",
            "escalation_chain": ["retry:5", "different_model:2", "human:1"],
        },
        "reviewer": {
            "critic_type": "scored",
            "critic_criteria": "code correctness, security, performance, readability, test coverage",
            "critic_min_score": 0.85,
        },
    },
    "ecommerce": {
        "specialist": {
            "tools": ["query_database", "http_request", "send_email"],
            "compliance_rules": [
                "MUST: verify customer identity before account changes",
                "MUST: follow return policy (30 days unused, 14 days electronics)",
                "NEVER: process refunds over $500 without human approval",
            ],
        },
    },
    "real_estate": {
        "specialist": {
            "tools": ["query_database", "http_request", "send_email"],
            "critic_type": "compliance",
            "compliance_rules": [
                "MUST: comply with fair housing laws",
                "NEVER: discriminate based on protected characteristics",
                "MUST: disclose all known property defects",
            ],
        },
    },
}


class AgentConfigurator:
    """
    Configures agent primitives based on domain and role.
    
    Usage:
        configurator = AgentConfigurator(domain="customer_support")
        config = configurator.configure("technical_support", role="specialist")
        # Returns AgentConfig with domain-appropriate primitives
    """

    def __init__(self, domain: str = ""):
        self.domain = self._normalize_domain(domain)

    def configure(self, agent_name: str = "", role: str = "specialist") -> AgentConfig:
        """Get the optimal primitive configuration for this agent in this domain."""
        import copy
        # Start with role defaults — deep copy to avoid mutating global defaults
        base = ROLE_CONFIGS.get(role, ROLE_CONFIGS["specialist"])
        config = copy.deepcopy(base)

        # Apply domain overrides
        domain_overrides = DOMAIN_OVERRIDES.get(self.domain, {})
        role_overrides = domain_overrides.get(role, {})
        for key, value in role_overrides.items():
            if hasattr(config, key):
                setattr(config, key, value)

        return config

    def get_all_role_configs(self) -> dict[str, AgentConfig]:
        """Get configurations for all standard roles in this domain."""
        return {role: self.configure(role=role) for role in ROLE_CONFIGS}

    @staticmethod
    def _normalize_domain(domain: str) -> str:
        """Normalize domain string to a key."""
        domain = domain.lower().strip()
        # Map common phrases to domain keys
        mappings = {
            "customer support": "customer_support",
            "saas support": "customer_support",
            "software development": "software_development",
            "software dev": "software_development",
            "ai dev": "software_development",
            "coding": "software_development",
            "e-commerce": "ecommerce",
            "ecommerce": "ecommerce",
            "online retail": "ecommerce",
            "real estate": "real_estate",
            "property": "real_estate",
        }
        for phrase, key in mappings.items():
            if phrase in domain:
                return key
        return domain.replace(" ", "_")

    def __repr__(self) -> str:
        return f"AgentConfigurator(domain={self.domain!r})"
