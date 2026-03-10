"""Webhook Tool — sends webhook notifications to external services."""

from __future__ import annotations

import json
import urllib.request
import urllib.error
from typing import Any
from forge.runtime.tools import Tool, ToolParameter


async def send_webhook(url: str, payload: str, method: str = "POST") -> str:
    """Send a webhook (HTTP POST/PUT with JSON payload) to an external URL."""
    from forge.runtime.integrations.rate_limiter import get_webhook_limiter, rate_limit_error
    limiter = get_webhook_limiter()
    if not limiter.acquire("webhook"):
        return rate_limit_error("send_webhook", limiter, "webhook")

    # SSRF protection: reuse http_tool's URL validation
    try:
        from forge.runtime.integrations.http_tool import _is_url_safe
        safe, reason = _is_url_safe(url)
        if not safe:
            return json.dumps({"success": False, "error": f"BLOCKED: {reason}"})
    except ImportError:
        pass  # If http_tool not available, proceed without check

    # Validate payload is valid JSON
    try:
        json.loads(payload)
    except (json.JSONDecodeError, TypeError):
        return json.dumps({"success": False, "error": "Payload must be valid JSON"})

    try:
        data = payload.encode("utf-8")
        headers = {"Content-Type": "application/json", "User-Agent": "Forge-Agency/1.0"}
        req = urllib.request.Request(url, data=data, headers=headers, method=method.upper())

        with urllib.request.urlopen(req, timeout=15) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            return json.dumps({
                "success": True,
                "status": resp.status,
                "response": body[:2000],
            })
    except urllib.error.HTTPError as e:
        return json.dumps({
            "success": False,
            "status": e.code,
            "error": str(e.reason),
        })
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})


def create_webhook_tool() -> Tool:
    return Tool(
        name="send_webhook",
        description="Send a webhook (HTTP POST with JSON payload) to notify external services.",
        parameters=[
            ToolParameter(name="url", type="string", description="Webhook URL to send to"),
            ToolParameter(name="payload", type="string", description="JSON payload to send"),
            ToolParameter(name="method", type="string", description="HTTP method (POST or PUT)", required=False),
        ],
        _fn=send_webhook,
    )
