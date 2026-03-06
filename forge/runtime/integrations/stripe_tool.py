"""Stripe payments integration — create charges, customers, and subscriptions.

Configure via environment variables:
    STRIPE_API_KEY (secret key starting with sk_)
If not set, runs in mock mode.
"""

from __future__ import annotations

import json
import logging
import os
import urllib.request
import urllib.parse
from typing import Any

from forge.runtime.tools import Tool, ToolParameter

logger = logging.getLogger(__name__)


async def _stripe_action(action: str, amount: int = 0, currency: str = "usd",
                         customer_email: str = "", description: str = "",
                         plan_id: str = "", customer_id: str = "") -> str:
    """Execute a Stripe action (charge, create_customer, subscribe, list_charges)."""
    api_key = os.environ.get("STRIPE_API_KEY", "")

    if not api_key:
        # Mock mode
        import uuid
        mock_id = f"mock_{uuid.uuid4().hex[:8]}"

        if action == "charge":
            return json.dumps({
                "success": True, "mock": True,
                "id": f"ch_{mock_id}", "amount": amount, "currency": currency,
                "status": "succeeded", "description": description,
                "message": "Charge created (mock — set STRIPE_API_KEY for real payments)",
            })
        elif action == "create_customer":
            return json.dumps({
                "success": True, "mock": True,
                "id": f"cus_{mock_id}", "email": customer_email,
                "message": "Customer created (mock mode)",
            })
        elif action == "list_charges":
            return json.dumps({
                "success": True, "mock": True,
                "charges": [
                    {"id": f"ch_mock_{i}", "amount": (i + 1) * 1000, "currency": "usd", "status": "succeeded"}
                    for i in range(3)
                ],
            })
        elif action == "subscribe":
            return json.dumps({
                "success": True, "mock": True,
                "id": f"sub_{mock_id}", "plan": plan_id, "customer": customer_id,
                "status": "active",
                "message": "Subscription created (mock mode)",
            })
        return json.dumps({"success": False, "error": f"Unknown action: {action}"})

    # Real Stripe API
    base_url = "https://api.stripe.com/v1"

    try:
        if action == "charge":
            data = urllib.parse.urlencode({
                "amount": amount, "currency": currency, "description": description,
                "source": "tok_visa",
            }).encode()
            url = f"{base_url}/charges"
        elif action == "create_customer":
            data = urllib.parse.urlencode({"email": customer_email}).encode()
            url = f"{base_url}/customers"
        elif action == "list_charges":
            url = f"{base_url}/charges?limit=10"
            data = None
        elif action == "subscribe":
            data = urllib.parse.urlencode({
                "customer": customer_id, "items[0][price]": plan_id,
            }).encode()
            url = f"{base_url}/subscriptions"
        else:
            return json.dumps({"success": False, "error": f"Unknown action: {action}"})

        req = urllib.request.Request(url, data=data, method="POST" if data else "GET")
        req.add_header("Authorization", f"Bearer {api_key}")

        with urllib.request.urlopen(req, timeout=15) as resp:
            result = json.loads(resp.read().decode())
            return json.dumps({"success": True, "mock": False, "data": result})
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})


def create_stripe_tool() -> Tool:
    """Create the Stripe payments tool."""
    return Tool(
        name="stripe_payment",
        description="Process payments via Stripe. Supports: charge, create_customer, list_charges, subscribe. Uses mock mode if STRIPE_API_KEY is not set.",
        parameters=[
            ToolParameter(name="action", type="string", description="Action: charge, create_customer, list_charges, subscribe", required=True),
            ToolParameter(name="amount", type="integer", description="Amount in cents (for charges)", required=False),
            ToolParameter(name="currency", type="string", description="Currency code (default: usd)", required=False),
            ToolParameter(name="customer_email", type="string", description="Customer email (for create_customer)", required=False),
            ToolParameter(name="description", type="string", description="Payment description", required=False),
            ToolParameter(name="plan_id", type="string", description="Plan/price ID (for subscribe)", required=False),
            ToolParameter(name="customer_id", type="string", description="Customer ID (for subscribe)", required=False),
        ],
        _fn=_stripe_action,
    )
