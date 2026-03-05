"""Web Search Tool — search the internet via DuckDuckGo."""

from __future__ import annotations

import json
import logging
import urllib.request
import urllib.parse
import urllib.error
import re
from typing import Any

from forge.runtime.tools import Tool, ToolParameter

logger = logging.getLogger(__name__)


async def web_search(query: str, max_results: int = 5) -> str:
    """Search the web using DuckDuckGo and return results."""
    try:
        encoded = urllib.parse.quote_plus(query)
        url = f"https://html.duckduckgo.com/html/?q={encoded}"
        
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
        }
        req = urllib.request.Request(url, headers=headers)
        
        with urllib.request.urlopen(req, timeout=15) as response:
            html = response.read().decode("utf-8", errors="replace")
        
        # Extract results from DuckDuckGo HTML
        results = []
        # DuckDuckGo HTML results are in <a class="result__a" href="...">title</a>
        # and <a class="result__snippet">description</a>
        links = re.findall(r'class="result__a"[^>]*href="([^"]*)"[^>]*>([^<]*)</a>', html)
        snippets = re.findall(r'class="result__snippet"[^>]*>(.*?)</a>', html, re.DOTALL)
        
        for i, (link, title) in enumerate(links[:max_results]):
            # Clean the redirect URL
            if "uddg=" in link:
                actual_url = urllib.parse.unquote(link.split("uddg=")[1].split("&")[0])
            else:
                actual_url = link
            
            snippet = ""
            if i < len(snippets):
                snippet = re.sub(r'<[^>]+>', '', snippets[i]).strip()[:200]
            
            results.append({
                "title": title.strip(),
                "url": actual_url,
                "snippet": snippet,
            })
        
        if not results:
            # Fallback: extract any links and text
            all_links = re.findall(r'href="(https?://[^"]+)"[^>]*>([^<]+)</a>', html)
            for link, title in all_links[:max_results]:
                if "duckduckgo" not in link:
                    results.append({"title": title.strip(), "url": link, "snippet": ""})
        
        return json.dumps({
            "query": query,
            "results": results,
            "count": len(results),
        }, indent=2)
        
    except Exception as e:
        return json.dumps({"query": query, "error": str(e), "results": []})


def create_search_tool() -> Tool:
    """Create a web search tool."""
    return Tool(
        name="web_search",
        description=(
            "Search the internet for information. Returns titles, URLs, and snippets. "
            "Use for: market research, finding documentation, researching competitors, "
            "understanding customer needs, finding best practices."
        ),
        parameters=[
            ToolParameter(name="query", type="string", description="The search query"),
            ToolParameter(name="max_results", type="integer", description="Max results to return (default 5)", required=False),
        ],
        _fn=web_search,
    )
