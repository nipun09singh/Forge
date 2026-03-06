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
    def get_tool_names(include_email: bool = True) -> list[str]:
        """Get names of all available built-in tools."""
        names = ["http_request", "query_database", "read_write_file", "send_webhook", "run_command", "git_operation", "browse_web", "web_search", "send_sms", "stripe_payment", "calendar"]
        if include_email:
            names.append("send_email")
        return names
