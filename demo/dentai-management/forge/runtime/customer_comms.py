"""Customer communication hub — notifications, feedback collection, and satisfaction tracking."""

from __future__ import annotations

import json
import logging
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class CustomerNotification:
    """A notification to send to a customer."""
    id: str = field(default_factory=lambda: f"notif-{uuid.uuid4().hex[:8]}")
    customer_id: str = ""
    task_id: str = ""
    agent_name: str = ""
    message: str = ""
    priority: str = "info"  # info, success, warning, critical
    channel: str = "webhook"  # webhook, email, log
    action_url: str = ""
    sent: bool = False
    sent_at: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class CustomerFeedback:
    """Feedback from a customer on an agent's work."""
    id: str = field(default_factory=lambda: f"fb-{uuid.uuid4().hex[:8]}")
    customer_id: str = ""
    task_id: str = ""
    agent_name: str = ""
    rating: int = 0  # 1-5 stars
    sentiment: str = ""  # very_helpful, okay, unhelpful, wrong
    comment: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class CustomerCommunicationHub:
    """
    Manages all customer-facing communication for an agency.
    
    Responsibilities:
    1. Send task completion notifications to customers
    2. Collect and aggregate customer feedback
    3. Track customer satisfaction scores (CSAT, NPS)
    4. Route notifications via configured channels (webhook, email, log)
    """

    def __init__(
        self,
        webhook_url: str = "",
        memory: Any = None,  # SharedMemory instance
        max_history: int = 10_000,
    ):
        self.webhook_url = webhook_url
        self._memory = memory
        self._notifications: list[CustomerNotification] = []
        self._feedback: list[CustomerFeedback] = []
        self._by_customer: dict[str, list[CustomerFeedback]] = defaultdict(list)
        self.max_history = max_history

    def set_memory(self, memory: Any) -> None:
        """Set shared memory for persistent storage."""
        self._memory = memory

    async def notify_task_completion(
        self,
        task_id: str,
        agent_name: str,
        output_summary: str,
        customer_id: str = "",
        channel: str = "log",
    ) -> CustomerNotification:
        """Send a task completion notification."""
        notif = CustomerNotification(
            customer_id=customer_id,
            task_id=task_id,
            agent_name=agent_name,
            message=f"Task completed by {agent_name}: {output_summary[:200]}",
            priority="success",
            channel=channel,
        )

        await self._send_notification(notif)
        return notif

    async def notify_approval_needed(
        self,
        task_id: str,
        agent_name: str,
        proposed_action: str,
        customer_id: str = "",
        urgency: str = "high",
    ) -> CustomerNotification:
        """Request customer approval for a high-stakes action."""
        notif = CustomerNotification(
            customer_id=customer_id,
            task_id=task_id,
            agent_name=agent_name,
            message=f"Approval required: {proposed_action[:200]}",
            priority=urgency,
            channel="webhook" if self.webhook_url else "log",
        )

        await self._send_notification(notif)
        return notif

    async def _send_notification(self, notif: CustomerNotification) -> None:
        """Send a notification via the configured channel."""
        self._notifications.append(notif)
        if len(self._notifications) > self.max_history:
            self._notifications = self._notifications[-self.max_history:]

        if notif.channel == "webhook" and self.webhook_url:
            try:
                import urllib.request
                payload = json.dumps({
                    "id": notif.id,
                    "customer_id": notif.customer_id,
                    "task_id": notif.task_id,
                    "agent": notif.agent_name,
                    "message": notif.message,
                    "priority": notif.priority,
                }).encode()
                req = urllib.request.Request(
                    self.webhook_url, data=payload,
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                urllib.request.urlopen(req, timeout=10)
                notif.sent = True
            except Exception as e:
                logger.warning(f"Failed to send webhook notification: {e}")
        elif notif.channel == "log":
            logger.info(f"[NOTIFICATION] {notif.priority.upper()}: {notif.message}")
            notif.sent = True

        notif.sent_at = datetime.now(timezone.utc).isoformat()

        # Store in memory for persistence
        if self._memory:
            self._memory.store(
                f"notification:{notif.id}",
                {"message": notif.message, "customer": notif.customer_id, "priority": notif.priority},
                author=notif.agent_name,
                tags=["notification", notif.priority],
            )

    def collect_feedback(self, feedback: CustomerFeedback) -> None:
        """Record customer feedback."""
        self._feedback.append(feedback)
        self._by_customer[feedback.customer_id].append(feedback)

        if len(self._feedback) > self.max_history:
            self._feedback = self._feedback[-self.max_history:]

        # Store in memory
        if self._memory:
            self._memory.store(
                f"feedback:{feedback.id}",
                {
                    "rating": feedback.rating,
                    "sentiment": feedback.sentiment,
                    "comment": feedback.comment,
                    "agent": feedback.agent_name,
                    "customer": feedback.customer_id,
                },
                author="customer",
                tags=["customer_feedback", feedback.sentiment],
            )

        logger.info(f"Feedback received: {feedback.rating}/5 from {feedback.customer_id} for {feedback.agent_name}")

    def get_satisfaction_score(self, customer_id: str = "") -> dict[str, Any]:
        """Get customer satisfaction metrics (CSAT)."""
        feedback = self._by_customer.get(customer_id, self._feedback) if customer_id else self._feedback

        if not feedback:
            return {"csat_score": 0, "total_feedback": 0, "avg_rating": 0}

        ratings = [f.rating for f in feedback if f.rating > 0]
        satisfied = sum(1 for r in ratings if r >= 4)  # 4-5 = satisfied
        total = len(ratings)

        sentiments = defaultdict(int)
        for f in feedback:
            if f.sentiment:
                sentiments[f.sentiment] += 1

        return {
            "csat_score": round(satisfied / max(total, 1) * 100, 1),
            "avg_rating": round(sum(ratings) / max(len(ratings), 1), 2),
            "total_feedback": total,
            "sentiment_distribution": dict(sentiments),
            "recent_comments": [f.comment for f in feedback[-5:] if f.comment],
        }

    def get_agent_satisfaction(self, agent_name: str) -> dict[str, Any]:
        """Get satisfaction metrics for a specific agent."""
        agent_feedback = [f for f in self._feedback if f.agent_name == agent_name]
        if not agent_feedback:
            return {"agent": agent_name, "total_feedback": 0}

        ratings = [f.rating for f in agent_feedback if f.rating > 0]
        return {
            "agent": agent_name,
            "avg_rating": round(sum(ratings) / max(len(ratings), 1), 2),
            "total_feedback": len(agent_feedback),
            "positive_pct": round(sum(1 for r in ratings if r >= 4) / max(len(ratings), 1) * 100, 1),
        }

    def get_notifications(self, customer_id: str = "", limit: int = 50) -> list[dict]:
        """Get notification history."""
        notifs = self._notifications
        if customer_id:
            notifs = [n for n in notifs if n.customer_id == customer_id]
        return [
            {"id": n.id, "message": n.message, "priority": n.priority, "sent": n.sent, "timestamp": n.timestamp}
            for n in notifs[-limit:]
        ]

    def __repr__(self) -> str:
        return f"CustomerCommunicationHub(notifications={len(self._notifications)}, feedback={len(self._feedback)})"
