"""Structured output types for Forge agent responses.

These models define the schema for agent LLM responses, enabling
validated structured output instead of ad-hoc string parsing.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class TaskStatus(str, Enum):
    """Status of an agent's current task."""
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    BLOCKED = "blocked"


class AgentResponse(BaseModel):
    """Structured response from an agent LLM call.
    
    Used to parse and validate agent output instead of treating
    it as an opaque string.
    """
    status: TaskStatus = Field(default=TaskStatus.IN_PROGRESS, description="Current task status")
    content: str = Field(default="", description="Text response content")
    reasoning: str = Field(default="", description="Agent's reasoning for this action")
    next_step: str = Field(default="", description="What should happen next")
    completion_score: float = Field(default=0.0, ge=0.0, le=1.0, description="Estimated task completion percentage")


class ProjectCompletion(BaseModel):
    """Structured project completion signal from the orchestrator.
    
    When the orchestrator decides the project is done, it should 
    return this structured format instead of just saying "DONE".
    """
    status: str = Field(default="DONE", description="Must be 'DONE'")
    summary: str = Field(default="", description="Brief summary of what was built")
    files_created: int = Field(default=0, ge=0, description="Number of files created")
    quality_notes: str = Field(default="", description="Quality assessment notes")


def parse_agent_response(text: str) -> AgentResponse | None:
    """Try to parse text as a structured AgentResponse.
    
    Returns None if the text is not valid JSON or doesn't match the schema.
    Handles both strict JSON and relaxed formats.
    """
    if not text or not text.strip():
        return None
    
    try:
        import json
        data = json.loads(text.strip())
        if isinstance(data, dict):
            return AgentResponse.model_validate(data)
    except (json.JSONDecodeError, Exception):
        pass
    return None


def parse_completion_signal(text: str) -> ProjectCompletion | None:
    """Try to parse text as a structured project completion signal.
    
    Returns None if not a valid completion signal. Handles both
    structured JSON and simple "DONE" string patterns.
    """
    if not text or not text.strip():
        return None
    
    import json
    stripped = text.strip()
    
    # Try JSON first (preferred)
    try:
        data = json.loads(stripped)
        if isinstance(data, dict):
            status = str(data.get("status", "")).upper()
            if status == "DONE" or status == "COMPLETED":
                return ProjectCompletion.model_validate(data)
    except (json.JSONDecodeError, Exception):
        pass
    
    # Fall back to string patterns
    text_upper = stripped.upper()
    is_done = any([
        text_upper == "DONE",
        text_upper == "DONE.",
        text_upper.startswith("DONE\n") or text_upper.startswith("DONE."),
        text_upper.endswith("\nDONE") or text_upper.endswith("\nDONE."),
        "PROJECT IS COMPLETE" in text_upper,
        "\nDONE\n" in f"\n{stripped}\n",
    ])
    
    if is_done:
        return ProjectCompletion(status="DONE", summary=stripped[:200])
    
    return None
