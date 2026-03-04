"""Typed agent messages — structured communication between agents."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class MessageType(str, Enum):
    """Types of messages agents can exchange."""
    TASK = "task"                 # A task assignment
    RESULT = "result"            # A completed task result
    DELEGATION = "delegation"    # Delegating work to another agent
    FEEDBACK = "feedback"        # Feedback on work done
    QUESTION = "question"        # A clarifying question
    ESCALATION = "escalation"    # Escalating to a higher authority
    STATUS = "status"            # Status update
    ERROR = "error"              # Error notification


class Priority(str, Enum):
    """Message priority levels."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class AgentMessage(BaseModel):
    """
    Typed message for agent-to-agent communication.
    
    Replaces raw strings with structured, validated, traceable messages.
    Every message has a sender, receiver, type, and optional structured data.
    """
    id: str = Field(default_factory=lambda: f"msg-{uuid.uuid4().hex[:8]}")
    sender: str = Field(description="Sending agent name")
    receiver: str = Field(default="", description="Target agent name (empty = broadcast)")
    content: str = Field(description="Human-readable message content")
    message_type: MessageType = Field(default=MessageType.TASK, description="Type of message")
    priority: Priority = Field(default=Priority.MEDIUM, description="Message priority")
    data: dict[str, Any] = Field(default_factory=dict, description="Structured payload data")
    trace_id: str = Field(default="", description="Trace ID for distributed tracing")
    parent_message_id: str = Field(default="", description="ID of the message this replies to")
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    metadata: dict[str, Any] = Field(default_factory=dict, description="Additional metadata")

    def reply(
        self,
        sender: str,
        content: str,
        message_type: MessageType = MessageType.RESULT,
        data: dict[str, Any] | None = None,
    ) -> "AgentMessage":
        """Create a reply to this message."""
        return AgentMessage(
            sender=sender,
            receiver=self.sender,
            content=content,
            message_type=message_type,
            data=data or {},
            trace_id=self.trace_id,
            parent_message_id=self.id,
        )

    def escalate(self, sender: str, reason: str) -> "AgentMessage":
        """Create an escalation message."""
        return AgentMessage(
            sender=sender,
            receiver="",  # Broadcast — whoever handles escalations
            content=f"Escalation: {reason}\n\nOriginal: {self.content[:200]}",
            message_type=MessageType.ESCALATION,
            priority=Priority.HIGH,
            data={"original_message_id": self.id, "reason": reason, **self.data},
            trace_id=self.trace_id,
            parent_message_id=self.id,
        )


class MessageBus:
    """
    Simple message bus for routing typed messages between agents.
    
    Maintains a history of all messages for auditing and debugging.
    Supports direct messaging, broadcasting, and filtering.
    """

    def __init__(self, max_history: int = 10_000) -> None:
        self._history: list[AgentMessage] = []
        self._subscribers: dict[str, list] = {}  # agent_name → callback list
        self.max_history = max_history

    def send(self, message: AgentMessage) -> None:
        """Send a message. Stores in history and notifies subscribers."""
        self._history.append(message)
        if len(self._history) > self.max_history:
            self._history = self._history[-self.max_history:]

        # Notify direct receiver
        if message.receiver and message.receiver in self._subscribers:
            for callback in self._subscribers[message.receiver]:
                callback(message)

        # Notify broadcast subscribers (empty receiver = broadcast)
        if not message.receiver:
            for name, callbacks in self._subscribers.items():
                for callback in callbacks:
                    callback(message)

    def subscribe(self, agent_name: str, callback) -> None:
        """Subscribe an agent to receive messages."""
        self._subscribers.setdefault(agent_name, []).append(callback)

    def unsubscribe(self, agent_name: str) -> None:
        """Remove all subscriptions for an agent."""
        self._subscribers.pop(agent_name, None)

    def get_history(
        self,
        sender: str | None = None,
        receiver: str | None = None,
        message_type: MessageType | None = None,
        trace_id: str | None = None,
        limit: int = 50,
    ) -> list[AgentMessage]:
        """Get message history with optional filters."""
        results = self._history
        if sender:
            results = [m for m in results if m.sender == sender]
        if receiver:
            results = [m for m in results if m.receiver == receiver]
        if message_type:
            results = [m for m in results if m.message_type == message_type]
        if trace_id:
            results = [m for m in results if m.trace_id == trace_id]
        return results[-limit:]

    def get_conversation(self, agent_a: str, agent_b: str, limit: int = 50) -> list[AgentMessage]:
        """Get the conversation between two agents."""
        results = [
            m for m in self._history
            if (m.sender == agent_a and m.receiver == agent_b) or
               (m.sender == agent_b and m.receiver == agent_a)
        ]
        return results[-limit:]

    def __repr__(self) -> str:
        return f"MessageBus(messages={len(self._history)}, subscribers={len(self._subscribers)})"
