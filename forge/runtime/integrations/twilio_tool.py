"""Twilio SMS integration — send and receive text messages.

Supports real Twilio API or mock mode for development/testing.
Configure via environment variables:
    TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_FROM_NUMBER
If not set, mock mode requires explicit opt-in via MOCK_MODE=true or
MOCK_INTEGRATIONS=true.
"""

from __future__ import annotations

import json
import logging
import os
import urllib.request
import urllib.parse
import base64
from typing import Any

from forge.runtime.tools import Tool, ToolParameter

logger = logging.getLogger(__name__)


def _is_mock_mode_enabled() -> bool:
    """Check if mock mode is explicitly enabled via environment variables."""
    return (os.environ.get("MOCK_MODE", "").lower() == "true"
            or os.environ.get("MOCK_INTEGRATIONS", "").lower() == "true")


async def _send_sms(to: str, body: str, from_number: str = "") -> str:
    """Send an SMS via Twilio API or mock."""
    from forge.runtime.integrations.rate_limiter import get_sms_limiter, rate_limit_error
    limiter = get_sms_limiter()
    if not limiter.acquire("sms"):
        return rate_limit_error("send_sms", limiter, "sms")

    account_sid = os.environ.get("TWILIO_ACCOUNT_SID", "")
    auth_token = os.environ.get("TWILIO_AUTH_TOKEN", "")
    from_num = from_number or os.environ.get("TWILIO_FROM_NUMBER", "+15005550006")

    if not account_sid or not auth_token:
        if not _is_mock_mode_enabled():
            return json.dumps({
                "success": False,
                "error": "TWILIO_ACCOUNT_SID/TWILIO_AUTH_TOKEN not configured. Set MOCK_MODE=true for testing without real credentials.",
            })

        # Explicit mock mode
        logger.warning("⚠️ MOCK MODE: Twilio SMS integration running without real credentials")
        return json.dumps({
            "success": True,
            "mock": True,
            "sid": f"SM_mock_{abs(hash(to + body)) % 10000:04d}",
            "to": to,
            "from": from_num,
            "body": body,
            "status": "sent",
            "message": "⚠️ MOCK MODE — SMS sent (not real — set TWILIO_ACCOUNT_SID for real delivery)",
        })

    # Real Twilio API
    url = f"https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Messages.json"
    data = urllib.parse.urlencode({
        "To": to,
        "From": from_num,
        "Body": body,
    }).encode()
    credentials = base64.b64encode(f"{account_sid}:{auth_token}".encode()).decode()
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Authorization", f"Basic {credentials}")

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            result = json.loads(resp.read().decode())
            return json.dumps({
                "success": True,
                "mock": False,
                "sid": result.get("sid", ""),
                "to": to,
                "from": from_num,
                "status": result.get("status", "queued"),
            })
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})


def create_twilio_tool() -> Tool:
    """Create the Twilio SMS tool."""
    return Tool(
        name="send_sms",
        description="Send an SMS text message via Twilio. Requires TWILIO_ACCOUNT_SID or explicit MOCK_MODE=true.",
        parameters=[
            ToolParameter(name="to", type="string", description="Recipient phone number (e.g., +14155551234)", required=True),
            ToolParameter(name="body", type="string", description="Message text to send", required=True),
            ToolParameter(name="from_number", type="string", description="Sender phone number (optional, uses TWILIO_FROM_NUMBER env var)", required=False),
        ],
        _fn=_send_sms,
    )
