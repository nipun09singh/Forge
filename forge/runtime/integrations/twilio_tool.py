"""Twilio SMS integration — send and receive text messages.

Supports real Twilio API or mock mode for development/testing.
Configure via environment variables:
    TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_FROM_NUMBER
If not set, runs in mock mode (returns simulated responses).
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


async def _send_sms(to: str, body: str, from_number: str = "") -> str:
    """Send an SMS via Twilio API or mock."""
    account_sid = os.environ.get("TWILIO_ACCOUNT_SID", "")
    auth_token = os.environ.get("TWILIO_AUTH_TOKEN", "")
    from_num = from_number or os.environ.get("TWILIO_FROM_NUMBER", "+15005550006")

    if not account_sid or not auth_token:
        # Mock mode
        logger.info(f"[MOCK] SMS to {to}: {body[:50]}...")
        return json.dumps({
            "success": True,
            "mock": True,
            "sid": f"SM_mock_{abs(hash(to + body)) % 10000:04d}",
            "to": to,
            "from": from_num,
            "body": body,
            "status": "sent",
            "message": "SMS sent (mock mode — set TWILIO_ACCOUNT_SID for real delivery)",
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
        description="Send an SMS text message via Twilio. Uses mock mode if TWILIO_ACCOUNT_SID is not set.",
        parameters=[
            ToolParameter(name="to", type="string", description="Recipient phone number (e.g., +14155551234)", required=True),
            ToolParameter(name="body", type="string", description="Message text to send", required=True),
            ToolParameter(name="from_number", type="string", description="Sender phone number (optional, uses TWILIO_FROM_NUMBER env var)", required=False),
        ],
        _fn=_send_sms,
    )
