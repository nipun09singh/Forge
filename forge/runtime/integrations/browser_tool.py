"""Browser Tool — web browsing and content extraction for agent research."""

from __future__ import annotations

import json
import logging
import re
import urllib.request
import urllib.error
from html.parser import HTMLParser
from typing import Any

from forge.runtime.tools import Tool, ToolParameter
from forge.runtime.integrations.http_tool import _is_url_safe

logger = logging.getLogger(__name__)


class _TextExtractor(HTMLParser):
    """Simple HTML to text converter."""
    
    def __init__(self):
        super().__init__()
        self._text = []
        self._skip_tags = {"script", "style", "head", "meta", "link", "noscript"}
        self._in_skip = 0
        self._links = []
    
    def handle_starttag(self, tag, attrs):
        if tag in self._skip_tags:
            self._in_skip += 1
        if tag == "a":
            href = dict(attrs).get("href", "")
            if href and href.startswith("http"):
                self._links.append(href)
        if tag in ("p", "div", "h1", "h2", "h3", "h4", "li", "br", "tr"):
            self._text.append("\n")
    
    def handle_endtag(self, tag):
        if tag in self._skip_tags:
            self._in_skip = max(0, self._in_skip - 1)
    
    def handle_data(self, data):
        if self._in_skip == 0:
            text = data.strip()
            if text:
                self._text.append(text)
    
    def get_text(self) -> str:
        return " ".join(self._text).strip()
    
    def get_links(self) -> list[str]:
        return list(set(self._links))


async def browse_web(url: str, extract: str = "text") -> str:
    """
    Browse a web page and extract content.
    
    Args:
        url: The URL to browse
        extract: What to extract: "text" (page text), "links" (all links), "raw" (raw HTML)
    """
    # SSRF protection: reuse http_tool's URL validation
    safe, reason = _is_url_safe(url)
    if not safe:
        return json.dumps({"url": url, "error": f"BLOCKED: {reason}"})

    try:
        import http.cookiejar
        cj = http.cookiejar.CookieJar()
        opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }
        req = urllib.request.Request(url, headers=headers)
        
        with opener.open(req, timeout=15) as response:
            content_type = response.headers.get("Content-Type", "")
            charset = "utf-8"
            if "charset=" in content_type:
                charset = content_type.split("charset=")[-1].split(";")[0].strip()
            
            raw_html = response.read().decode(charset, errors="replace")
            status = response.status
        
        if extract == "raw":
            return json.dumps({
                "url": url,
                "status": status,
                "content_type": content_type,
                "html": raw_html[:20000],
                "truncated": len(raw_html) > 20000,
            })
        
        # Parse HTML
        parser = _TextExtractor()
        parser.feed(raw_html)
        
        if extract == "links":
            links = parser.get_links()
            return json.dumps({
                "url": url,
                "status": status,
                "links": links[:100],
                "count": len(links),
            })
        
        # Default: extract text
        text = parser.get_text()
        # Clean up whitespace
        text = re.sub(r'\n\s*\n', '\n\n', text)
        text = re.sub(r' +', ' ', text)
        
        return json.dumps({
            "url": url,
            "status": status,
            "text": text[:15000],
            "links": parser.get_links()[:20],
            "truncated": len(text) > 15000,
        })
        
    except urllib.error.HTTPError as e:
        return json.dumps({"url": url, "error": f"HTTP {e.code}: {e.reason}"})
    except Exception as e:
        return json.dumps({"url": url, "error": str(e)})


def create_browser_tool() -> Tool:
    """Create a web browsing tool."""
    return Tool(
        name="browse_web",
        description=(
            "Browse a web page and extract its content. "
            "Use for: reading documentation, researching solutions, checking APIs, "
            "fetching reference code, reading error explanations. "
            "Returns page text, links, or raw HTML."
        ),
        parameters=[
            ToolParameter(name="url", type="string", description="The URL to browse"),
            ToolParameter(name="extract", type="string", description="What to extract: text (default), links, or raw", required=False),
        ],
        _fn=browse_web,
    )
