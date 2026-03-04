"""Human-in-the-loop — approval gates for agent actions."""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Awaitable

logger = logging.getLogger(__name__)


class ApprovalDecision(str, Enum):
    """Decision on an approval request."""
    APPROVED = "approved"
    REJECTED = "rejected"
    MODIFIED = "modified"  # Approved with modifications


class Urgency(str, Enum):
    """Urgency level of an approval request."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class ApprovalRequest:
    """A request for human approval."""
    request_id: str = field(default_factory=lambda: f"approval-{uuid.uuid4().hex[:8]}")
    agent_name: str = ""
    action_description: str = ""
    action_type: str = ""  # "tool_call", "final_output", "delegation"
    context: dict[str, Any] = field(default_factory=dict)
    urgency: Urgency = Urgency.MEDIUM


@dataclass
class ApprovalResult:
    """Result of a human approval decision."""
    decision: ApprovalDecision
    feedback: str = ""
    modified_action: str = ""  # If decision is MODIFIED, this contains the revised action
    approver: str = "human"


class HumanApprovalGate:
    """
    Gate that pauses agent execution and requests human approval.
    
    By default uses console-based interaction (rich-formatted prompts).
    Subclass and override `_request_approval` for webhook/API/Slack integration.
    
    Configuration:
    - auto_approve_urgency: Urgency level at or below which to auto-approve (default: None = always ask)
    - timeout_seconds: How long to wait for human response (default: 300 = 5 minutes)
    """

    def __init__(
        self,
        auto_approve_urgency: Urgency | None = None,
        timeout_seconds: int = 300,
    ):
        self.auto_approve_urgency = auto_approve_urgency
        self.timeout_seconds = timeout_seconds
        self._history: list[tuple[ApprovalRequest, ApprovalResult]] = []

    def __repr__(self) -> str:
        return f"HumanApprovalGate(auto_approve={self.auto_approve_urgency}, history={len(self._history)})"

    async def approve(self, request: ApprovalRequest) -> ApprovalResult:
        """
        Request human approval for an action.
        
        Returns the approval decision.
        """
        # Auto-approve if urgency is at or below threshold
        if self.auto_approve_urgency and self._urgency_level(request.urgency) <= self._urgency_level(self.auto_approve_urgency):
            result = ApprovalResult(decision=ApprovalDecision.APPROVED, feedback="Auto-approved (below urgency threshold)")
            self._history.append((request, result))
            logger.info(f"Auto-approved: {request.action_description[:80]}")
            return result

        # Request human approval
        result = await self._request_approval(request)
        self._history.append((request, result))
        logger.info(f"Human decision for '{request.request_id}': {result.decision.value}")
        return result

    async def _request_approval(self, request: ApprovalRequest) -> ApprovalResult:
        """
        Request approval via console. Override for other channels (API, Slack, etc.).
        """
        try:
            from rich.console import Console
            from rich.panel import Panel
            from rich.table import Table
            console = Console()
        except ImportError:
            console = None

        # Display the request
        urgency_icons = {"low": "🟢", "medium": "🟡", "high": "🟠", "critical": "🔴"}
        icon = urgency_icons.get(request.urgency.value, "❓")

        if console:
            content = (
                f"[bold]{icon} Urgency: {request.urgency.value.upper()}[/bold]\n\n"
                f"[bold]Agent:[/bold] {request.agent_name}\n"
                f"[bold]Action Type:[/bold] {request.action_type}\n\n"
                f"[bold]Action:[/bold]\n{request.action_description}\n"
            )
            if request.context:
                ctx_str = "\n".join(f"  {k}: {str(v)[:100]}" for k, v in request.context.items())
                content += f"\n[bold]Context:[/bold]\n{ctx_str}"

            console.print(Panel(content, title="🙋 Human Approval Required", border_style="yellow"))
        else:
            print(f"\n{'='*60}")
            print(f"🙋 HUMAN APPROVAL REQUIRED")
            print(f"Agent: {request.agent_name}")
            print(f"Urgency: {icon} {request.urgency.value}")
            print(f"Action: {request.action_description}")
            print(f"{'='*60}")

        # Get decision via console input
        while True:
            try:
                choice = await asyncio.get_event_loop().run_in_executor(None, input, "\n[A]pprove / [R]eject / [M]odify? ")
                choice = choice.strip().lower()
            except (EOFError, KeyboardInterrupt):
                return ApprovalResult(decision=ApprovalDecision.REJECTED, feedback="Interrupted by user")

            if choice in ("a", "approve", "y", "yes"):
                feedback = await asyncio.get_event_loop().run_in_executor(None, input, "Feedback (optional, press Enter to skip): ")
                feedback = feedback.strip()
                return ApprovalResult(decision=ApprovalDecision.APPROVED, feedback=feedback)
            elif choice in ("r", "reject", "n", "no"):
                feedback = await asyncio.get_event_loop().run_in_executor(None, input, "Reason for rejection: ")
                feedback = feedback.strip()
                return ApprovalResult(decision=ApprovalDecision.REJECTED, feedback=feedback)
            elif choice in ("m", "modify"):
                modification = await asyncio.get_event_loop().run_in_executor(None, input, "Describe the modification: ")
                modification = modification.strip()
                return ApprovalResult(
                    decision=ApprovalDecision.MODIFIED,
                    feedback="Modified by human",
                    modified_action=modification,
                )
            else:
                print("Please enter A (approve), R (reject), or M (modify)")

    @staticmethod
    def _urgency_level(urgency: Urgency) -> int:
        return {"low": 0, "medium": 1, "high": 2, "critical": 3}.get(urgency.value, 1)

    def get_history(self) -> list[dict[str, Any]]:
        """Get approval history."""
        return [
            {
                "request_id": req.request_id,
                "agent": req.agent_name,
                "action": req.action_description[:100],
                "urgency": req.urgency.value,
                "decision": result.decision.value,
                "feedback": result.feedback,
            }
            for req, result in self._history
        ]


class WebhookApprovalGate(HumanApprovalGate):
    """
    Approval gate that sends requests via webhook and polls for response.
    
    Useful for Slack, Teams, email, or custom approval UIs.
    """

    def __init__(
        self,
        webhook_url: str,
        poll_url: str = "",
        poll_interval: int = 5,
        **kwargs: Any,
    ):
        super().__init__(**kwargs)
        self.webhook_url = webhook_url
        self.poll_url = poll_url
        self.poll_interval = poll_interval

    async def _request_approval(self, request: ApprovalRequest) -> ApprovalResult:
        """Send approval request via webhook, poll for response."""
        import urllib.request
        import urllib.error

        # Send the request
        payload = json.dumps({
            "request_id": request.request_id,
            "agent_name": request.agent_name,
            "action": request.action_description,
            "action_type": request.action_type,
            "urgency": request.urgency.value,
            "context": {k: str(v)[:200] for k, v in request.context.items()},
        }).encode()

        try:
            req = urllib.request.Request(
                self.webhook_url,
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            urllib.request.urlopen(req, timeout=10)
        except Exception as e:
            logger.error(f"Failed to send approval webhook: {e}")
            return ApprovalResult(decision=ApprovalDecision.REJECTED, feedback=f"Webhook failed: {e}")

        # Poll for response (if poll URL configured)
        if self.poll_url:
            for _ in range(self.timeout_seconds // self.poll_interval):
                await asyncio.sleep(self.poll_interval)
                try:
                    poll_req = urllib.request.Request(f"{self.poll_url}?id={request.request_id}")
                    with urllib.request.urlopen(poll_req, timeout=5) as resp:
                        data = json.loads(resp.read().decode())
                        if data.get("decision"):
                            return ApprovalResult(
                                decision=ApprovalDecision(data["decision"]),
                                feedback=data.get("feedback", ""),
                                modified_action=data.get("modified_action", ""),
                            )
                except Exception:
                    continue

        # Timeout — reject by default
        return ApprovalResult(decision=ApprovalDecision.REJECTED, feedback="Approval timed out")
