"""Unified execution strategy for Forge projects."""

from __future__ import annotations

from enum import Enum


class ExecutionStrategy(str, Enum):
    """How to execute a project task.

    ORCHESTRATOR: Single agent with all tools in an unbounded loop.
        Best for: Most tasks. Research shows single-agent outperforms multi-agent.
    TEAM: Team lead delegates to specialist agents.
        Best for: Large projects with distinct specialist roles.
    """
    ORCHESTRATOR = "orchestrator"
    TEAM = "team"
