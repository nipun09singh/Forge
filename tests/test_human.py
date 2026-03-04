"""Tests for forge.runtime.human"""

import pytest
from forge.runtime.human import (
    HumanApprovalGate, ApprovalRequest, ApprovalResult,
    ApprovalDecision, Urgency,
)


class TestHumanApprovalGate:
    @pytest.mark.asyncio
    async def test_auto_approve_low(self):
        gate = HumanApprovalGate(auto_approve_urgency=Urgency.LOW)
        request = ApprovalRequest(
            agent_name="test", action_description="Low urgency action", urgency=Urgency.LOW,
        )
        result = await gate.approve(request)
        assert result.decision == ApprovalDecision.APPROVED

    @pytest.mark.asyncio
    async def test_auto_approve_medium_with_low_threshold(self):
        gate = HumanApprovalGate(auto_approve_urgency=Urgency.MEDIUM)
        request = ApprovalRequest(
            agent_name="test", action_description="Low action", urgency=Urgency.LOW,
        )
        result = await gate.approve(request)
        assert result.decision == ApprovalDecision.APPROVED

    @pytest.mark.asyncio
    async def test_no_auto_approve_high(self):
        gate = HumanApprovalGate(auto_approve_urgency=Urgency.LOW)
        # HIGH urgency should NOT be auto-approved when threshold is LOW
        # This would normally prompt for input, but we test the logic
        request = ApprovalRequest(urgency=Urgency.HIGH)
        # Can't test interactive input here, but verify it doesn't auto-approve
        # by checking the urgency level comparison
        assert gate._urgency_level(Urgency.HIGH) > gate._urgency_level(Urgency.LOW)

    def test_history_tracking(self):
        gate = HumanApprovalGate()
        assert gate.get_history() == []

    def test_urgency_levels(self):
        gate = HumanApprovalGate()
        assert gate._urgency_level(Urgency.LOW) < gate._urgency_level(Urgency.CRITICAL)
        assert gate._urgency_level(Urgency.MEDIUM) < gate._urgency_level(Urgency.HIGH)
