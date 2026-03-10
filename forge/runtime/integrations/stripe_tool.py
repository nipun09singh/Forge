"""Stripe payments integration — create charges, customers, and subscriptions.

Configure via environment variables:
    STRIPE_API_KEY (secret key starting with sk_)
If not set, mock mode requires explicit opt-in via MOCK_MODE=true or
MOCK_INTEGRATIONS=true.
"""

from __future__ import annotations

import json
import logging
import os
import urllib.request
import urllib.parse
import uuid
from typing import Any

from forge.runtime.tools import Tool, ToolParameter

logger = logging.getLogger(__name__)


def _is_mock_mode_enabled() -> bool:
    """Check if mock mode is explicitly enabled via environment variables."""
    return (os.environ.get("MOCK_MODE", "").lower() == "true"
            or os.environ.get("MOCK_INTEGRATIONS", "").lower() == "true")


async def _stripe_action(action: str, amount: int = 0, currency: str = "usd",
                         customer_email: str = "", description: str = "",
                         plan_id: str = "", customer_id: str = "",
                         payment_method_id: str = "") -> str:
    """Execute a Stripe action using Payment Intents API (charge, create_customer, subscribe, list_charges)."""
    from forge.runtime.integrations.rate_limiter import (
        get_stripe_limiter, get_stripe_amount_limiter,
        rate_limit_error, amount_limit_error,
    )
    # Rate-limit charges and subscriptions (monetary actions)
    if action in ("charge", "subscribe"):
        limiter = get_stripe_limiter()
        if not limiter.acquire("stripe"):
            return rate_limit_error("stripe_payment", limiter, "stripe")
        # Also enforce dollar-amount cap for charges
        if action == "charge" and amount > 0:
            amount_limiter = get_stripe_amount_limiter()
            if not amount_limiter.acquire(amount, "stripe"):
                return amount_limit_error("stripe_payment", amount_limiter, amount, "stripe")

    api_key = os.environ.get("STRIPE_API_KEY", "")

    if not api_key:
        if not _is_mock_mode_enabled():
            return json.dumps({
                "success": False,
                "error": "STRIPE_API_KEY not configured. Set MOCK_MODE=true for testing without real credentials.",
            })

        # Explicit mock mode
        import uuid
        logger.warning("⚠️ MOCK MODE: Stripe integration running without real credentials")
        mock_id = f"mock_{uuid.uuid4().hex[:8]}"

        if action == "charge":
            return json.dumps({
                "success": True, "mock": True,
                "id": f"ch_{mock_id}", "amount": amount, "currency": currency,
                "status": "succeeded", "description": description,
                "message": "⚠️ MOCK MODE — Charge created (not real — set STRIPE_API_KEY for real payments)",
            })
        elif action == "create_customer":
            return json.dumps({
                "success": True, "mock": True,
                "id": f"cus_{mock_id}", "email": customer_email,
                "message": "⚠️ MOCK MODE — Customer created (not real)",
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
                "message": "⚠️ MOCK MODE — Subscription created (not real)",
            })
        return json.dumps({"success": False, "error": f"Unknown action: {action}"})

    # Real Stripe API
    base_url = "https://api.stripe.com/v1"

    try:
        if action == "charge":
            # Use Payment Intents API (modern) instead of Charges API
            intent_data = {
                "amount": amount, "currency": currency, "description": description,
            }
            if payment_method_id:
                intent_data["payment_method"] = payment_method_id
                intent_data["confirm"] = "true"
            if customer_id:
                intent_data["customer"] = customer_id
            data = urllib.parse.urlencode(intent_data).encode()
            url = f"{base_url}/payment_intents"
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
        if action in ("charge", "subscribe"):
            idempotency_key = f"forge-{uuid.uuid4().hex}"
            req.add_header("Idempotency-Key", idempotency_key)

        with urllib.request.urlopen(req, timeout=15) as resp:
            result = json.loads(resp.read().decode())
            return json.dumps({"success": True, "mock": False, "data": result})
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})


def create_stripe_tool() -> Tool:
    """Create the Stripe payments tool."""
    return Tool(
        name="stripe_payment",
        description="Process payments via Stripe. Supports: charge, create_customer, list_charges, subscribe. Requires STRIPE_API_KEY or explicit MOCK_MODE=true.",
        parameters=[
            ToolParameter(name="action", type="string", description="Action: charge, create_customer, list_charges, subscribe", required=True),
            ToolParameter(name="amount", type="integer", description="Amount in cents (for charges)", required=False),
            ToolParameter(name="currency", type="string", description="Currency code (default: usd)", required=False),
            ToolParameter(name="customer_email", type="string", description="Customer email (for create_customer)", required=False),
            ToolParameter(name="description", type="string", description="Payment description", required=False),
            ToolParameter(name="plan_id", type="string", description="Plan/price ID (for subscribe)", required=False),
            ToolParameter(name="customer_id", type="string", description="Customer ID (for subscribe/charge)", required=False),
            ToolParameter(name="payment_method_id", type="string", description="Payment method ID (for charges via Payment Intents)", required=False),
        ],
        _fn=_stripe_action,
    )
