"""HTTP Tool — makes real HTTP requests."""

from __future__ import annotations

import ipaddress
import json
import socket
from typing import Any
from forge.runtime.tools import Tool, ToolParameter


def _is_url_safe(url: str) -> tuple[bool, str]:
    """Check if URL targets a safe (non-internal) destination."""
    try:
        from urllib.parse import urlparse
        parsed = urlparse(url)
        
        # Block non-HTTP schemes
        if parsed.scheme not in ("http", "https"):
            return False, f"Only http/https URLs are allowed, got: {parsed.scheme}"
        
        hostname = parsed.hostname or ""
        
        # Block cloud metadata endpoints
        if hostname in ("169.254.169.254", "metadata.google.internal", "100.100.100.200"):
            return False, "Access to cloud metadata endpoints is blocked"
        
        # Resolve hostname and check for private IPs
        try:
            for info in socket.getaddrinfo(hostname, None):
                addr = info[4][0]
                ip = ipaddress.ip_address(addr)
                if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
                    return False, f"Access to private/internal IP {addr} is blocked"
        except socket.gaierror:
            pass  # Let the request fail naturally if DNS fails
        
        return True, ""
    except Exception as e:
        return False, f"Invalid URL: {e}"


async def http_request(url: str, method: str = "GET", headers: str = "{}", body: str = "") -> str:
    """Make an HTTP request and return the response."""
    import urllib.request
    import urllib.error
    from forge.runtime.integrations.rate_limiter import get_http_limiter, rate_limit_error
    limiter = get_http_limiter()
    if not limiter.acquire("http"):
        return rate_limit_error("http_request", limiter, "http")

    # SSRF protection: block internal/private URLs
    safe, reason = _is_url_safe(url)
    if not safe:
        return json.dumps({"error": f"BLOCKED: {reason}"})

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
