"""Forge Dashboard — Real-time web UI for monitoring AI agencies.

Serves a single-page dashboard that connects to a running agency's API
for live event streaming, task submission, and cost monitoring.

Usage:
    forge dashboard ./my-agency  # Starts dashboard + agency on port 8080
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

DASHBOARD_DIR = Path(__file__).parent


def get_dashboard_html() -> str:
    """Load the dashboard HTML."""
    html_path = DASHBOARD_DIR / "index.html"
    if html_path.exists():
        return html_path.read_text(encoding="utf-8")
    return "<html><body><h1>Dashboard not found</h1></body></html>"
