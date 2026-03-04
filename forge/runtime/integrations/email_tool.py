"""Email Tool — sends real emails via SMTP."""

from __future__ import annotations

import json
import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Any
from forge.runtime.tools import Tool, ToolParameter


async def send_email(to: str, subject: str, body: str, html: str = "") -> str:
    """Send an email via SMTP. Configure via environment variables."""
    smtp_host = os.getenv("SMTP_HOST", "localhost")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_user = os.getenv("SMTP_USER", "")
    smtp_pass = os.getenv("SMTP_PASS", "")
    from_addr = os.getenv("SMTP_FROM", smtp_user or "forge@localhost")

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = from_addr
        msg["To"] = to

        msg.attach(MIMEText(body, "plain"))
        if html:
            msg.attach(MIMEText(html, "html"))

        with smtplib.SMTP(smtp_host, smtp_port, timeout=15) as server:
            if smtp_port == 587:
                server.starttls()
            if smtp_user and smtp_pass:
                server.login(smtp_user, smtp_pass)
            server.send_message(msg)

        return json.dumps({"success": True, "message": f"Email sent to {to}", "subject": subject})
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})


def create_email_tool(smtp_host: str | None = None) -> Tool:
    if smtp_host:
        os.environ.setdefault("SMTP_HOST", smtp_host)
    return Tool(
        name="send_email",
        description="Send an email. Configure SMTP via env vars: SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS, SMTP_FROM.",
        parameters=[
            ToolParameter(name="to", type="string", description="Recipient email address"),
            ToolParameter(name="subject", type="string", description="Email subject line"),
            ToolParameter(name="body", type="string", description="Plain text email body"),
            ToolParameter(name="html", type="string", description="Optional HTML body", required=False),
        ],
        _fn=send_email,
    )
