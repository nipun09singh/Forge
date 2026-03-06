"""Tests for escalation policy wiring into Agent execution."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from forge.runtime.agent import Agent, AgentStatus, TaskResult
from forge.runtime.primitives.escalation import (
    EscalationPolicy, EscalationLevel, EscalationStep,
)
from forge.runtime.human import (
    HumanApprovalGate, ApprovalRequest, ApprovalResult, ApprovalDecision, Urgency,
)


def _make_llm_response(content="Test response", tool_calls=None):
    """Build a mock LLM response."""
    response = MagicMock()
    response.choices = [MagicMock()]
    response.choices[0].message.content = content
    response.choices[0].message.tool_calls = tool_calls
    response.usage = MagicMock(prompt_tokens=10, completion_tokens=5, total_tokens=15)
    return response


def _make_agent(**overrides):
    """Build a test agent with sensible defaults."""
    kwargs = dict(
        name="TestAgent",
        role="specialist",
        system_prompt="You are a test agent.",
        model="gpt-4o-mini",
        temperature=0.5,
        max_iterations=5,
    )
    kwargs.update(overrides)
    return Agent(**kwargs)


# ---------------------------------------------------------------------------
# EscalationPolicy unit tests
# ---------------------------------------------------------------------------

class TestEscalationPolicy:
    def test_default_chain(self):
        policy = EscalationPolicy()
        levels = [s.level for s in policy.steps]
        assert levels == [
            EscalationLevel.RETRY,
            EscalationLevel.DIFFERENT_MODEL,
            EscalationLevel.HUMAN,
        ]

    def test_custom_steps(self):
        steps = [EscalationStep(level=EscalationLevel.RETRY, max_attempts=1)]
        policy = EscalationPolicy(steps=steps)
        assert len(policy.steps) == 1

    def test_enabled_levels_filter(self):
        policy = EscalationPolicy(
            enabled_levels={EscalationLevel.RETRY, EscalationLevel.HUMAN},
        )
        levels = {s.level for s in policy.steps}
        assert EscalationLevel.DIFFERENT_MODEL not in levels
        assert EscalationLevel.RETRY in levels
        assert EscalationLevel.HUMAN in levels

    def test_should_escalate_on_failure(self):
        policy = EscalationPolicy()
        assert policy.should_escalate(success=False) is True

    def test_should_not_escalate_on_success(self):
        policy = EscalationPolicy()
        assert policy.should_escalate(success=True) is False

    def test_success_resets_state(self):
        policy = EscalationPolicy()
        policy.should_escalate(success=False)
        policy.get_next_action()
        assert policy._attempt_count == 1
        # Success should reset
        policy.should_escalate(success=True)
        assert policy._attempt_count == 0
        assert policy._current_step_idx == 0

    def test_max_total_attempts_exhaustion(self):
        policy = EscalationPolicy(max_total_attempts=2)
        assert policy.should_escalate(success=False) is True
        assert policy.should_escalate(success=False) is False

    def test_get_next_action_advances_steps(self):
        policy = EscalationPolicy(steps=[
            EscalationStep(level=EscalationLevel.RETRY, max_attempts=1),
            EscalationStep(level=EscalationLevel.HUMAN, max_attempts=1),
        ])
        step1 = policy.get_next_action()
        assert step1.level == EscalationLevel.RETRY
        # Exhaust retry → advances to human
        step2 = policy.get_next_action()
        assert step2.level == EscalationLevel.HUMAN

    def test_get_next_action_returns_none_when_exhausted(self):
        policy = EscalationPolicy(steps=[
            EscalationStep(level=EscalationLevel.RETRY, max_attempts=1),
        ])
        policy.get_next_action()  # consume the single step
        assert policy.get_next_action() is None

    def test_reset(self):
        policy = EscalationPolicy()
        policy.should_escalate(success=False)
        policy.get_next_action()
        policy.reset()
        assert policy._attempt_count == 0
        assert policy._current_step_idx == 0
        assert policy._step_attempts == {}


# ---------------------------------------------------------------------------
# Agent escalation integration tests
# ---------------------------------------------------------------------------

class TestAgentEscalationRetry:
    """Level 1: Retry with enhanced prompt."""

    @pytest.mark.asyncio
    async def test_retry_escalation_on_failure(self):
        """When first attempt fails, agent retries with error context."""
        agent = _make_agent(
            escalation_policy=EscalationPolicy(steps=[
                EscalationStep(level=EscalationLevel.RETRY, max_attempts=1),
            ]),
        )

        # First call raises, second call succeeds
        fail_response = _make_llm_response("I failed")
        success_response = _make_llm_response("Success on retry")

        client = AsyncMock()
        call_count = 0

        async def _side_effect(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # First attempt: raise to trigger failure
                raise RuntimeError("LLM connection error")
            return success_response

        client.chat.completions.create = AsyncMock(side_effect=_side_effect)
        agent.set_llm_client(client)

        result = await agent.execute("do something")
        assert result.success is True
        assert result.output == "Success on retry"
        # Verify error context was injected into conversation
        retry_msgs = [
            m for m in agent.conversation
            if m.get("role") == "user" and "previous attempt failed" in m.get("content", "").lower()
        ]
        assert len(retry_msgs) >= 1

    @pytest.mark.asyncio
    async def test_escalation_exhausted_returns_failure(self):
        """When all escalation steps are exhausted, returns failure."""
        agent = _make_agent(
            escalation_policy=EscalationPolicy(
                steps=[EscalationStep(level=EscalationLevel.RETRY, max_attempts=1)],
                max_total_attempts=3,
            ),
        )

        client = AsyncMock()
        client.chat.completions.create = AsyncMock(
            side_effect=RuntimeError("permanent failure")
        )
        agent.set_llm_client(client)

        result = await agent.execute("do something")
        assert result.success is False


class TestAgentEscalationModelUpgrade:
    """Level 2: Upgrade model."""

    @pytest.mark.asyncio
    async def test_model_upgrade_on_failure(self):
        """When retry fails, agent upgrades model."""
        agent = _make_agent(
            model="gpt-4o-mini",
            escalation_policy=EscalationPolicy(steps=[
                EscalationStep(level=EscalationLevel.DIFFERENT_MODEL, max_attempts=1, model_override="gpt-4"),
            ]),
        )

        success_response = _make_llm_response("Success with upgraded model")
        client = AsyncMock()
        call_count = 0
        models_used = []

        async def _side_effect(**kwargs):
            nonlocal call_count
            models_used.append(kwargs.get("model"))
            call_count += 1
            if call_count == 1:
                raise RuntimeError("Model too weak")
            return success_response

        client.chat.completions.create = AsyncMock(side_effect=_side_effect)
        agent.set_llm_client(client)

        result = await agent.execute("complex task")
        assert result.success is True
        # First call used fast model, second used upgraded model
        assert models_used[0] == "gpt-4o-mini"
        assert "gpt-4" in models_used[1]
        # Model should be restored after escalation
        assert agent.model == "gpt-4o-mini"

    @pytest.mark.asyncio
    async def test_model_restored_even_on_failure(self):
        """Model is restored to original even if upgraded attempt fails."""
        agent = _make_agent(
            model="gpt-4o-mini",
            escalation_policy=EscalationPolicy(
                steps=[
                    EscalationStep(level=EscalationLevel.DIFFERENT_MODEL, max_attempts=1, model_override="gpt-4"),
                ],
                max_total_attempts=3,
            ),
        )

        client = AsyncMock()
        client.chat.completions.create = AsyncMock(
            side_effect=RuntimeError("always fails")
        )
        agent.set_llm_client(client)

        result = await agent.execute("task")
        assert result.success is False
        assert agent.model == "gpt-4o-mini"


class TestAgentEscalationHuman:
    """Level 3: Delegate to human."""

    @pytest.mark.asyncio
    async def test_human_escalation_with_approval_gate(self):
        """When escalated to human, uses approval gate and retries with guidance."""
        agent = _make_agent(
            escalation_policy=EscalationPolicy(steps=[
                EscalationStep(level=EscalationLevel.HUMAN, max_attempts=1),
            ]),
        )

        success_response = _make_llm_response("Fixed with human help")
        client = AsyncMock()
        call_count = 0

        async def _side_effect(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("Need help")
            return success_response

        client.chat.completions.create = AsyncMock(side_effect=_side_effect)
        agent.set_llm_client(client)

        # Mock approval gate
        gate = AsyncMock(spec=HumanApprovalGate)
        gate.approve = AsyncMock(return_value=ApprovalResult(
            decision=ApprovalDecision.APPROVED,
            feedback="Try using the search tool first",
            modified_action="",
            approver="human",
        ))
        agent.set_approval_gate(gate)

        result = await agent.execute("task needing help")
        assert result.success is True
        assert result.output == "Fixed with human help"
        gate.approve.assert_called_once()

    @pytest.mark.asyncio
    async def test_human_escalation_rejected(self):
        """When human rejects escalation, returns failure."""
        agent = _make_agent(
            escalation_policy=EscalationPolicy(steps=[
                EscalationStep(level=EscalationLevel.HUMAN, max_attempts=1),
            ]),
        )

        client = AsyncMock()
        client.chat.completions.create = AsyncMock(
            side_effect=RuntimeError("Need help")
        )
        agent.set_llm_client(client)

        gate = AsyncMock(spec=HumanApprovalGate)
        gate.approve = AsyncMock(return_value=ApprovalResult(
            decision=ApprovalDecision.REJECTED,
            feedback="Not worth retrying",
            modified_action="",
            approver="human",
        ))
        agent.set_approval_gate(gate)

        result = await agent.execute("task")
        assert result.success is False
        assert "rejected" in result.output.lower()

    @pytest.mark.asyncio
    async def test_human_escalation_without_gate(self):
        """Without an approval gate, human escalation returns needs_human."""
        agent = _make_agent(
            escalation_policy=EscalationPolicy(steps=[
                EscalationStep(level=EscalationLevel.HUMAN, max_attempts=1),
            ]),
        )

        client = AsyncMock()
        client.chat.completions.create = AsyncMock(
            side_effect=RuntimeError("Need help")
        )
        agent.set_llm_client(client)

        result = await agent.execute("task")
        assert result.success is False
        assert result.data.get("needs_human") is True


class TestAgentEscalationFullChain:
    """Full escalation chain: retry → model upgrade → human → fail."""

    @pytest.mark.asyncio
    async def test_full_chain_success_on_model_upgrade(self):
        """Retry fails, then model upgrade succeeds."""
        agent = _make_agent(
            model="gpt-4o-mini",
            escalation_policy=EscalationPolicy(steps=[
                EscalationStep(level=EscalationLevel.RETRY, max_attempts=1),
                EscalationStep(level=EscalationLevel.DIFFERENT_MODEL, max_attempts=1, model_override="gpt-4"),
            ], max_total_attempts=10),
        )

        success_response = _make_llm_response("Finally worked")
        client = AsyncMock()
        call_count = 0

        async def _side_effect(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count <= 2:
                raise RuntimeError(f"Fail attempt {call_count}")
            return success_response

        client.chat.completions.create = AsyncMock(side_effect=_side_effect)
        agent.set_llm_client(client)

        result = await agent.execute("hard task")
        assert result.success is True
        assert result.output == "Finally worked"

    @pytest.mark.asyncio
    async def test_escalation_resets_on_new_task(self):
        """Escalation state resets between execute() calls."""
        agent = _make_agent(
            escalation_policy=EscalationPolicy(steps=[
                EscalationStep(level=EscalationLevel.RETRY, max_attempts=1),
            ]),
        )

        success_response = _make_llm_response("ok")
        client = AsyncMock()
        client.chat.completions.create = AsyncMock(return_value=success_response)
        agent.set_llm_client(client)

        # First execution succeeds
        result1 = await agent.execute("task 1")
        assert result1.success is True

        # Escalation state should be reset for second execution
        assert agent._escalation_policy._attempt_count == 0
        assert agent._escalation_policy._current_step_idx == 0

    @pytest.mark.asyncio
    async def test_no_escalation_on_success(self):
        """Successful execution does not trigger escalation."""
        agent = _make_agent()
        success_response = _make_llm_response("all good")
        client = AsyncMock()
        client.chat.completions.create = AsyncMock(return_value=success_response)
        agent.set_llm_client(client)

        result = await agent.execute("easy task")
        assert result.success is True
        # Escalation was never triggered
        assert agent._escalation_policy._attempt_count == 0


class TestAgentEscalationGracefulFail:
    """Level 4: Graceful failure with full context."""

    @pytest.mark.asyncio
    async def test_different_agent_level_fails_gracefully(self):
        """DIFFERENT_AGENT level returns structured failure."""
        agent = _make_agent(
            escalation_policy=EscalationPolicy(steps=[
                EscalationStep(level=EscalationLevel.DIFFERENT_AGENT, max_attempts=1),
            ]),
        )

        client = AsyncMock()
        client.chat.completions.create = AsyncMock(
            side_effect=RuntimeError("Cannot handle this")
        )
        agent.set_llm_client(client)

        result = await agent.execute("specialized task")
        assert result.success is False
        assert result.data.get("escalation_exhausted") is True
        assert result.data.get("escalation_level") == "different_agent"


class TestEscalationPolicyConfiguration:
    """Test configurability of the escalation policy."""

    def test_max_attempts_per_level(self):
        policy = EscalationPolicy(steps=[
            EscalationStep(level=EscalationLevel.RETRY, max_attempts=5),
        ])
        assert policy.steps[0].max_attempts == 5

    def test_model_override_configuration(self):
        policy = EscalationPolicy(steps=[
            EscalationStep(level=EscalationLevel.DIFFERENT_MODEL, max_attempts=2, model_override="claude-3-opus"),
        ])
        assert policy.steps[0].model_override == "claude-3-opus"

    def test_empty_enabled_levels_gives_no_steps(self):
        policy = EscalationPolicy(enabled_levels=set())
        assert len(policy.steps) == 0
        assert policy.should_escalate(success=False) is False

    def test_agent_default_escalation_policy(self):
        agent = _make_agent()
        assert agent._escalation_policy is not None
        assert len(agent._escalation_policy.steps) > 0

    def test_agent_custom_escalation_policy(self):
        custom = EscalationPolicy(steps=[
            EscalationStep(level=EscalationLevel.RETRY, max_attempts=10),
        ])
        agent = _make_agent(escalation_policy=custom)
        assert agent._escalation_policy is custom
        assert agent._escalation_policy.steps[0].max_attempts == 10


# ---------------------------------------------------------------------------
# Edge-case tests — no human gate, premium model, policy reset, exhausted
# ---------------------------------------------------------------------------

class TestEscalationNoHumanGate:
    """Escalation skips human level when no gate is configured."""

    @pytest.mark.asyncio
    async def test_no_gate_skips_to_next_level(self):
        """Without a human gate, human escalation returns failure."""
        agent = _make_agent(
            escalation_policy=EscalationPolicy(steps=[
                EscalationStep(level=EscalationLevel.HUMAN, max_attempts=1),
            ]),
        )
        # No approval gate set

        client = AsyncMock()
        client.chat.completions.create = AsyncMock(
            side_effect=RuntimeError("fail")
        )
        agent.set_llm_client(client)

        result = await agent.execute("task")
        assert result.success is False


class TestEscalationModelUpgradeAlreadyPremium:
    """Model upgrade when agent is already on the premium model."""

    @pytest.mark.asyncio
    async def test_model_upgrade_same_model(self):
        """When model_override matches current model, escalation still proceeds."""
        agent = _make_agent(
            model="gpt-4",
            escalation_policy=EscalationPolicy(steps=[
                EscalationStep(level=EscalationLevel.DIFFERENT_MODEL, max_attempts=1, model_override="gpt-4"),
            ], max_total_attempts=5),
        )

        client = AsyncMock()
        client.chat.completions.create = AsyncMock(
            side_effect=RuntimeError("still fails")
        )
        agent.set_llm_client(client)

        result = await agent.execute("task")
        assert result.success is False
        # Model should remain unchanged after escalation
        assert agent.model == "gpt-4"


class TestEscalationPolicyResetAfterSuccess:
    """Policy fully resets after a successful execution."""

    @pytest.mark.asyncio
    async def test_reset_after_success_allows_full_escalation_again(self):
        """After success, the full escalation chain is available for the next task."""
        policy = EscalationPolicy(steps=[
            EscalationStep(level=EscalationLevel.RETRY, max_attempts=1),
            EscalationStep(level=EscalationLevel.DIFFERENT_MODEL, max_attempts=1, model_override="gpt-4"),
        ])

        # Simulate failure → escalation through both levels
        policy.should_escalate(success=False)
        policy.get_next_action()  # RETRY
        policy.get_next_action()  # DIFFERENT_MODEL

        # Now success resets
        policy.should_escalate(success=True)
        assert policy._attempt_count == 0
        assert policy._current_step_idx == 0
        assert policy._step_attempts == {}

        # Full chain should be available again
        step = policy.get_next_action()
        assert step is not None
        assert step.level == EscalationLevel.RETRY


class TestEscalationMaxLevelsExhausted:
    """All escalation levels exhausted returns None."""

    def test_all_steps_exhausted_returns_none(self):
        """After exhausting all steps, get_next_action returns None."""
        policy = EscalationPolicy(steps=[
            EscalationStep(level=EscalationLevel.RETRY, max_attempts=1),
        ])
        action = policy.get_next_action()
        assert action is not None
        assert action.level == EscalationLevel.RETRY
        # Now exhausted
        action = policy.get_next_action()
        assert action is None

    def test_should_escalate_false_when_all_exhausted(self):
        """should_escalate returns False when all steps are consumed."""
        policy = EscalationPolicy(
            steps=[
                EscalationStep(level=EscalationLevel.RETRY, max_attempts=1),
            ],
            max_total_attempts=10,
        )
        # Consume the single step's attempt
        policy.get_next_action()
        # The next call to get_next_action advances past the end
        assert policy.get_next_action() is None
        # Now _current_step_idx should be past the end
        assert policy._current_step_idx >= len(policy.steps)
        assert policy.should_escalate(success=False) is False
