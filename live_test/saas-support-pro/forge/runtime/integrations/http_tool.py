"""HTTP Tool — makes real HTTP requests."""

from __future__ import annotations

import json
from typing import Any
from forge.runtime.tools import Tool, ToolParameter


async def http_request(url: str, method: str = "GET", headers: str = "{}", body: str = "") -> str:
    """Make an HTTP request and return the response."""
    import urllib.request
    import urllib.error

    try:
        hdrs = json.loads(headers) if headers else {}
    except json.JSONDecodeError:
        hdrs = {}

    data = body.encode("utf-8") if body else None
    req = urllib.request.Request(url, data=data, headers=hdrs, method=method.upper())

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            response_body = resp.read().decode("utf-8", errors="replace")
            return json.dumps({
                "status": resp.status,
                "headers": dict(resp.headers),
                "body": response_body[:5000],
            }, indent=2)
    except urllib.error.HTTPError as e:
        return json.dumps({
            "status": e.code,
            "error": str(e.reason),
            "body": e.read().decode("utf-8", errors="replace")[:2000],
        })
    except Exception as e:
        return json.dumps({"error": str(e)})


def create_http_tool() -> Tool:
    return Tool(
        name="http_request",
        description="Make an HTTP request (GET, POST, PUT, DELETE) to any URL. Returns status, headers, and body.",
        parameters=[
            ToolParameter(name="url", type="string", description="The URL to request"),
            ToolParameter(name="method", type="string", description="HTTP method: GET, POST, PUT, DELETE", required=False),
            ToolParameter(name="headers", type="string", description="JSON string of request headers", required=False),
            ToolParameter(name="body", type="string", description="Request body (for POST/PUT)", required=False),
        ],
        _fn=http_request,
    )
