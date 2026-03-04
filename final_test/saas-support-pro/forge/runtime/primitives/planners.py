"""Planner primitives — different strategies for decomposing tasks."""

from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class PlannedStep:
    """A single step in a plan."""
    id: str
    description: str
    depends_on: list[str] = field(default_factory=list)
    assigned_to: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


class PlannerBase(ABC):
    """Base class for all planners."""

    @abstractmethod
    async def plan(self, task: str, context: dict[str, Any] | None = None, llm_client: Any = None) -> list[PlannedStep]:
        """Decompose a task into steps."""
        ...

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}()"


class SimplePlanner(PlannerBase):
    """Single-step planner — task goes directly to execution without decomposition."""

    async def plan(self, task: str, context: dict[str, Any] | None = None, llm_client: Any = None) -> list[PlannedStep]:
        return [PlannedStep(id="execute", description=task)]


class SequentialPlanner(PlannerBase):
    """Breaks task into sequential steps using LLM."""

    def __init__(self, max_steps: int = 10, model: str = "gpt-4"):
        self.max_steps = max_steps
        self.model = model

    async def plan(self, task: str, context: dict[str, Any] | None = None, llm_client: Any = None) -> list[PlannedStep]:
        if not llm_client:
            return [PlannedStep(id="step-1", description=task)]

        messages = [
            {"role": "system", "content": (
                f"Break this task into {self.max_steps} or fewer sequential steps. "
                "Return JSON: {\"steps\": [{\"id\": \"step-1\", \"description\": \"...\"}]}"
            )},
            {"role": "user", "content": task},
        ]

        try:
            response = await llm_client.chat.completions.create(
                model=self.model, messages=messages, temperature=0.3,
                response_format={"type": "json_object"},
            )
            data = json.loads(response.choices[0].message.content or "{}")
            steps = []
            prev_id = ""
            for i, s in enumerate(data.get("steps", [])):
                step_id = s.get("id", f"step-{i+1}")
                steps.append(PlannedStep(
                    id=step_id,
                    description=s.get("description", ""),
                    depends_on=[prev_id] if prev_id else [],
                ))
                prev_id = step_id
            return steps or [PlannedStep(id="step-1", description=task)]
        except Exception as e:
            logger.warning(f"Sequential planning failed: {e}. Using single step.")
            return [PlannedStep(id="step-1", description=task)]


class DAGPlanner(PlannerBase):
    """Decomposes into a DAG with parallel execution where possible."""

    def __init__(self, max_steps: int = 15, model: str = "gpt-4"):
        self.max_steps = max_steps
        self.model = model

    async def plan(self, task: str, context: dict[str, Any] | None = None, llm_client: Any = None) -> list[PlannedStep]:
        if not llm_client:
            return [PlannedStep(id="step-1", description=task)]

        messages = [
            {"role": "system", "content": (
                f"Break this task into up to {self.max_steps} steps with dependencies. "
                "Steps with no shared dependencies can run in parallel. "
                "Return JSON: {\"steps\": [{\"id\": \"s1\", \"description\": \"...\", \"depends_on\": []}]}"
            )},
            {"role": "user", "content": task},
        ]

        try:
            response = await llm_client.chat.completions.create(
                model=self.model, messages=messages, temperature=0.3,
                response_format={"type": "json_object"},
            )
            data = json.loads(response.choices[0].message.content or "{}")
            return [
                PlannedStep(
                    id=s.get("id", f"s{i}"),
                    description=s.get("description", ""),
                    depends_on=s.get("depends_on", []),
                )
                for i, s in enumerate(data.get("steps", []))
            ] or [PlannedStep(id="step-1", description=task)]
        except Exception:
            return [PlannedStep(id="step-1", description=task)]


class ClassifyAndRoutePlanner(PlannerBase):
    """Classifies the task and routes to the right handler. Best for support/intake."""

    def __init__(self, categories: list[str] | None = None, model: str = "gpt-4"):
        self.categories = categories or ["technical", "billing", "general", "escalation"]
        self.model = model

    async def plan(self, task: str, context: dict[str, Any] | None = None, llm_client: Any = None) -> list[PlannedStep]:
        # Quick classification
        category = "general"
        task_lower = task.lower()
        keyword_map = {
            "technical": ["bug", "error", "crash", "broken", "fix", "code", "api", "deploy"],
            "billing": ["bill", "charge", "refund", "pay", "invoice", "price", "subscription"],
            "escalation": ["urgent", "critical", "manager", "escalate", "sue", "legal"],
        }
        for cat, keywords in keyword_map.items():
            if any(kw in task_lower for kw in keywords):
                category = cat
                break

        return [
            PlannedStep(id="classify", description=f"Classified as: {category}", metadata={"category": category}),
            PlannedStep(id="handle", description=task, depends_on=["classify"], assigned_to=category),
        ]
