"""Built-in tool integrations — real working tools for Forge agencies."""

from forge.runtime.integrations.http_tool import create_http_tool
from forge.runtime.integrations.email_tool import create_email_tool
from forge.runtime.integrations.sql_tool import create_sql_tool
from forge.runtime.integrations.file_tool import create_file_tool
from forge.runtime.integrations.webhook_tool import create_webhook_tool
from forge.runtime.integrations.command_tool import create_command_tool
from forge.runtime.integrations.git_tool import create_git_tool
from forge.runtime.integrations.browser_tool import create_browser_tool
from forge.runtime.integrations.search_tool import create_search_tool
from forge.runtime.integrations.twilio_tool import create_twilio_tool
from forge.runtime.integrations.stripe_tool import create_stripe_tool
from forge.runtime.integrations.calendar_tool import create_calendar_tool
from forge.runtime.tools import Tool


class BuiltinToolkit:
    """
    Registry of all built-in tool integrations.

    These are REAL, working tools — not stubs. They make actual HTTP requests,
    send real emails, query real databases, and read/write real files.
    """

    @staticmethod
    def all_tools(
        sandbox_dir: str = "./data",
        db_path: str = "./data/agency.db",
        smtp_host: str | None = None,
    ) -> list[Tool]:
        """Get all built-in tools."""
        tools = [
            create_http_tool(),
            create_file_tool(sandbox_dir=sandbox_dir),
            create_sql_tool(db_path=db_path),
        ]
        if smtp_host:
            tools.append(create_email_tool(smtp_host=smtp_host))
        tools.append(create_webhook_tool())
        tools.append(create_command_tool())
        tools.append(create_git_tool())
        tools.append(create_browser_tool())
        tools.append(create_search_tool())
        tools.append(create_twilio_tool())
        tools.append(create_stripe_tool())
        tools.append(create_calendar_tool())
        return tools

    @staticmethod
    def primitives(
        sandbox_dir: str = "./workspace",
        db_path: str = "./data/agency.db",
        role: str | None = None,
    ) -> list:
        """Get primitive tools, optionally filtered by agent role.

        When *role* is ``None`` (default), all 5 primitives are returned for
        backward compatibility.  When a role is given, ``run_command`` is only
        included for ``"developer"`` and ``"admin"`` roles.

        Primitives:
        - read_write_file: Create, read, edit any file
        - run_command: Execute any shell command (developer/admin only)
        - http_request: Call any API
        - web_search: Search the internet
        - browse_web: Read any web page
        """
        from forge.runtime.integrations.file_tool import create_file_tool
        from forge.runtime.integrations.command_tool import create_command_tool
        from forge.runtime.integrations.http_tool import create_http_tool
        from forge.runtime.integrations.search_tool import create_search_tool
        from forge.runtime.integrations.browser_tool import create_browser_tool

        tools = [
            create_file_tool(sandbox_dir=sandbox_dir),
            create_http_tool(),
            create_search_tool(),
            create_browser_tool(),
        ]

        # Only include command_tool for privileged roles (or when no role specified)
        _command_roles = {"developer", "admin"}
        if role is None or role.strip().lower() in _command_roles:
            tools.insert(1, create_command_tool())

        return tools

    @staticmethod
    def safe_tools(sandbox_dir: str = "./workspace") -> list:
        """Return primitive tools WITHOUT command execution.

        Intended for non-technical roles (support, analyst, etc.) where shell
        access is unnecessary and potentially dangerous.
        """
        from forge.runtime.integrations.file_tool import create_file_tool
        from forge.runtime.integrations.http_tool import create_http_tool
        from forge.runtime.integrations.search_tool import create_search_tool
        from forge.runtime.integrations.browser_tool import create_browser_tool

        return [
            create_file_tool(sandbox_dir=sandbox_dir),
            create_http_tool(),
            create_search_tool(),
            create_browser_tool(),
        ]

    @staticmethod
    def library() -> dict:
        """Get the integration tool library — available tools the AI can choose to use.
        
        Returns a registry of tool factories (not instantiated tools) with metadata,
        so the orchestrator can discover and load integrations on demand.
        
        Usage:
            lib = BuiltinToolkit.library()
            if "send_sms" in lib:
                sms_tool = lib["send_sms"]["create"]()
        """
        from forge.runtime.integrations.email_tool import create_email_tool
        from forge.runtime.integrations.webhook_tool import create_webhook_tool
        from forge.runtime.integrations.git_tool import create_git_tool
        from forge.runtime.integrations.sql_tool import create_sql_tool
        from forge.runtime.integrations.twilio_tool import create_twilio_tool
        from forge.runtime.integrations.stripe_tool import create_stripe_tool
        from forge.runtime.integrations.calendar_tool import create_calendar_tool
        
        return {
            "send_email": {
                "create": create_email_tool,
                "description": "Send emails via SMTP",
                "category": "communication",
                "env_vars": ["SMTP_HOST", "SMTP_USER", "SMTP_PASSWORD"],
            },
            "send_webhook": {
                "create": create_webhook_tool,
                "description": "Send HTTP webhooks to external services",
                "category": "integration",
                "env_vars": [],
            },
            "git_operation": {
                "create": create_git_tool,
                "description": "Git version control operations",
                "category": "devops",
                "env_vars": [],
            },
            "query_database": {
                "create": lambda **kw: create_sql_tool(**kw),
                "description": "Query SQLite databases",
                "category": "data",
                "env_vars": [],
            },
            "send_sms": {
                "create": create_twilio_tool,
                "description": "Send SMS via Twilio API (mock mode if unconfigured)",
                "category": "communication",
                "env_vars": ["TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN"],
            },
            "stripe_payment": {
                "create": create_stripe_tool,
                "description": "Process payments via Stripe (mock mode if unconfigured)",
                "category": "payments",
                "env_vars": ["STRIPE_API_KEY"],
            },
            "calendar": {
                "create": create_calendar_tool,
                "description": "Manage calendar events via Google Calendar (mock mode if unconfigured)",
                "category": "scheduling",
                "env_vars": ["GOOGLE_CALENDAR_API_KEY"],
            },
        }

    @staticmethod
    def get_tool(name: str, **kwargs) -> "Tool | None":
        """Lazy-load a specific integration tool by name.
        
        Returns None if the tool doesn't exist in the library.
        The AI can use this to pull integrations when its research tells it to.
        """
        lib = BuiltinToolkit.library()
        entry = lib.get(name)
        if entry:
            return entry["create"](**kwargs)
        return None

    @staticmethod
    def get_tool_names(include_email: bool = True) -> list[str]:
        """Get names of all available built-in tools."""
        names = ["http_request", "query_database", "read_write_file", "send_webhook", "run_command", "git_operation", "browse_web", "web_search", "send_sms", "stripe_payment", "calendar"]
        if include_email:
            names.append("send_email")
        return names
