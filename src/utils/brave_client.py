"""
brave_client.py — Brave Search API client for Phantom Command Center.

Used by the research agent to fetch real, current web results.
Free tier: 2,000 queries/month.
"""

import logging
from typing import List, Dict

import httpx

from src.core.config import get_secret

logger = logging.getLogger(__name__)

BRAVE_API_URL = "https://api.search.brave.com/res/v1/web/search"


async def search(query: str, count: int = 5) -> List[Dict]:
    """
    Search the web via Brave Search API.

    Returns a list of results, each with:
      - title
      - url
      - description
    """
    api_key = get_secret("BRAVE_API_KEY")

    headers = {
        "Accept": "application/json",
        "Accept-Encoding": "gzip",
        "X-Subscription-Token": api_key
    }
    params = {
        "q": query,
        "count": count,
        "search_lang": "en",
        "safesearch": "moderate"
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(BRAVE_API_URL, headers=headers, params=params)
            resp.raise_for_status()
            data = resp.json()

        results = []
        for item in data.get("web", {}).get("results", []):
            results.append({
                "title": item.get("title", ""),
                "url": item.get("url", ""),
                "description": item.get("description", "")
            })

        logger.info(f"Brave Search: '{query}' → {len(results)} results")
        return results

    except Exception as e:
        logger.error(f"Brave Search failed for '{query}': {e}")
        return []


def format_results_for_prompt(results: List[Dict]) -> str:
    """Format search results into a readable string for LLM prompts."""
    if not results:
        return "No search results found."

    lines = []
    for i, r in enumerate(results, 1):
        lines.append(f"{i}. **{r['title']}**")
        lines.append(f"   {r['description']}")
        lines.append(f"   Source: {r['url']}")
    return "\n".join(lines)
