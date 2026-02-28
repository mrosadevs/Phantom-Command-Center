"""
last30.py — Deep research agent for any topic from the last 30 days.

Multi-source research engine:
  1. Brave Search — 6 targeted query angles (news, reddit, dev, hn, video, analysis)
  2. Hacker News  — Algolia free API (no auth, recent stories + points)
  3. Smart model routing — uses current override, falls back to LM Studio, then Groq

Triggered via Discord: "last30 AI agents" / "last30 TypeScript" etc.
"""

import asyncio
import logging
import sys
from datetime import datetime, timedelta
from typing import List, Dict

import httpx

from src.utils import brave_client
from src.core.config import ROOT_DIR

logger = logging.getLogger(__name__)

# On Windows, npm .cmd wrappers must be called with .cmd suffix from Python subprocess
CLAUDE_CMD = "claude.cmd" if sys.platform == "win32" else "claude"

# ── Search angles: 6 different perspectives ───────────────────────────────────
QUERY_ANGLES = [
    '"{topic}" {year} latest news',
    '"{topic}" developments update {year}',
    '"{topic}" site:reddit.com OR site:news.ycombinator.com',
    '"{topic}" developer tools release {year}',
    '"{topic}" analysis trends {year}',
    '"{topic}" review community opinion {year}',
]

# ── Hacker News via Algolia free API ─────────────────────────────────────────
HN_API = "https://hn.algolia.com/api/v1/search"

# ── Synthesis prompt: strict format, cross-platform signals, Stats Block ──────
SYNTHESIS_PROMPT = """⚠️ TOOL USE: NONE. Do NOT call WebSearch, BraveSearch, or any tool. ALL data is already provided below — your only job is to read it and write the brief.

Research brief request: "{topic}" — last 30 days only.

You have {n_results} deduplicated results from web search + Hacker News below.

{search_results}

Write a tight, factual research brief. Follow this EXACT format with no extra sections:

## What's New
3 bullet points on the biggest recent developments. Lead with specific names, dates, numbers.
Every bullet must be grounded in the sources above.

## Key Findings
5 concrete takeaways. Include data/numbers where available. No vague statements.
Flag cross-platform signals (stories appearing on HN + Reddit + web = strong signal).

## Community Pulse
What's the actual mood — debates, consensus, emerging criticism? Quote @handles or r/subreddits where relevant.
Be specific about sentiment, not generic.

## Worth Acting On
3 specific, actionable recommendations based purely on what you found.
No generic advice. Directly tied to the findings above.

## Stats Block
- Sources analysed: {n_results}
- HN stories: {hn_count}
- Web results: {web_count}
- Date range: last 30 days

## Sources
List 6-8 of the most relevant URLs. Prefer HN threads and community posts over press releases.

---
Rules: Only report what's in the sources. Cite r/subreddits and HN threads by name, not just URLs.
No hallucinations. If a claim isn't in the sources, don't include it."""


async def _search_hn(topic: str, count: int = 8) -> List[Dict]:
    """
    Search Hacker News via Algolia free API.
    Returns stories from the last 30 days sorted by points.
    No auth required.
    """
    cutoff = int((datetime.now() - timedelta(days=30)).timestamp())
    params = {
        "query": topic,
        "tags": "story",
        "hitsPerPage": count,
        "numericFilters": f"created_at_i>{cutoff}",
    }
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(HN_API, params=params)
            resp.raise_for_status()
            data = resp.json()

        hits = data.get("hits", [])
        results = []
        for h in hits:
            obj_id = h.get("objectID", "")
            hn_url = h.get("url") or f"https://news.ycombinator.com/item?id={obj_id}"
            points = h.get("points", 0)
            comments = h.get("num_comments", 0)
            results.append({
                "title": h.get("title", "(no title)"),
                "url": hn_url,
                "description": f"[HN] {points} pts · {comments} comments · {h.get('author', '')}",
                "source": "hackernews",
                "points": points,
            })

        # Sort by engagement
        results.sort(key=lambda x: x["points"], reverse=True)
        logger.info(f"HN search '{topic}': {len(results)} stories")
        return results

    except Exception as e:
        logger.warning(f"HN search failed: {e}")
        return []


async def _synthesize(prompt: str) -> str:
    """
    Synthesize research brief.

    Priority:
      1. Model override (if Theodore has locked a specific model)
      2. Claude CLI --print mode (original — best quality, fast)
      3. Groq fallback (if Claude CLI unavailable)
    """
    import os
    from src.core.router import get_override
    from src.utils import groq_client

    override = get_override()

    # ── 1. Respect manual model override ──────────────────────────────────────
    if override:
        provider = override["provider"]
        model    = override["model"]
        label    = override["label"]

        if provider == "claude-code":
            result = await _claude_cli_synthesize(prompt, model=model)
            if result:
                logger.info(f"last30: synthesized with {label} (override)")
                return result

        elif provider == "lm-studio":
            try:
                from src.utils import lm_studio_client
                result = await lm_studio_client.chat(prompt, max_tokens=1500)
                logger.info(f"last30: synthesized with {label} (override)")
                return result
            except Exception as e:
                logger.warning(f"LM Studio synthesis failed: {e}")

        elif provider == "groq":
            try:
                result = await groq_client.chat(prompt, max_tokens=1500)
                logger.info(f"last30: synthesized with {label} (override)")
                return result
            except Exception as e:
                logger.warning(f"Groq synthesis failed: {e}")

        elif provider == "gemini":
            try:
                from src.utils import gemini_client
                result = await gemini_client.chat(prompt)
                logger.info(f"last30: synthesized with {label} (override)")
                return result
            except Exception as e:
                logger.warning(f"Gemini synthesis failed: {e}")

    # ── 2. Default: Claude CLI --print (original behaviour, best quality) ─────
    result = await _claude_cli_synthesize(prompt)
    if result:
        logger.info("last30: synthesized with Claude CLI")
        return result

    # ── 3. Groq fallback ──────────────────────────────────────────────────────
    try:
        result = await groq_client.chat(prompt, max_tokens=1500)
        logger.info("last30: synthesized with Groq (fallback)")
        return result
    except Exception as e:
        logger.error(f"All synthesis providers failed: {e}")
        return "(Synthesis unavailable — Claude CLI not found and Groq API key may be missing.)"


async def _claude_cli_synthesize(prompt: str, model: str = None, timeout: int = 120) -> str:
    """
    Call Claude via CLI --print mode (Max subscription auth, no SDK overhead).
    Returns the response string, or empty string on failure.
    """
    import os

    cmd = [CLAUDE_CMD, "--print", prompt]
    if model:
        cmd += ["--model", model]

    try:
        env = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(ROOT_DIR),
            env=env,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)

        if proc.returncode == 0:
            output = stdout.decode("utf-8", errors="replace").strip()
            # Detect if Claude tried to use a tool it doesn't have permission for
            # (e.g. WebSearch) and returned a meta-message instead of the actual brief.
            _tool_denied_signals = [
                "isn't permitted in this session",
                "WebSearch tool isn't permitted",
                "don't have permission",
                "not permitted to use",
                "Two options to get",  # Claude's "here's what you can do instead" format
            ]
            if output and not any(s in output for s in _tool_denied_signals):
                return output
            logger.warning("Claude CLI returned a tool-permission message — falling back to Groq")

        err = stderr.decode("utf-8", errors="replace").strip()
        logger.warning(f"Claude CLI --print failed (exit {proc.returncode}): {err[:120]}")
        return ""

    except FileNotFoundError:
        logger.warning("Claude CLI not found (claude.cmd missing on PATH)")
        return ""
    except asyncio.TimeoutError:
        logger.warning(f"Claude CLI timed out after {timeout}s")
        return ""
    except Exception as e:
        logger.warning(f"Claude CLI error: {e}")
        return ""


async def research_last30(topic: str) -> str:
    """
    Run a last-30-days deep research brief on any topic.
    Multi-source: Brave Search (6 angles) + Hacker News (Algolia API).
    Synthesizes with current active model, falls back to LM Studio then Groq.
    """
    logger.info(f"last30 research starting: {topic}")
    year = datetime.now().year

    # ── 1. Fire all searches in parallel ──────────────────────────────────────
    queries = [q.format(topic=topic, year=year) for q in QUERY_ANGLES]
    brave_tasks = [brave_client.search(q, count=4) for q in queries]
    hn_task = _search_hn(topic, count=8)

    all_tasks = brave_tasks + [hn_task]
    all_results_raw = await asyncio.gather(*all_tasks, return_exceptions=True)

    # ── 2. Deduplicate by URL ─────────────────────────────────────────────────
    brave_results = []
    hn_results = []
    seen_urls: set = set()

    # Process brave results (first N items)
    for results in all_results_raw[:-1]:
        if isinstance(results, Exception):
            continue
        for r in results:
            url = r.get("url", "")
            if url and url not in seen_urls:
                brave_results.append(r)
                seen_urls.add(url)

    # Process HN results (last item)
    hn_raw = all_results_raw[-1]
    if not isinstance(hn_raw, Exception):
        for r in hn_raw:
            url = r.get("url", "")
            if url and url not in seen_urls:
                hn_results.append(r)
                seen_urls.add(url)

    if not brave_results and not hn_results:
        return (
            f"**last30: {topic}**\n\n"
            "No results found — Brave Search API may be unavailable. Try again shortly."
        )

    # ── 3. Format results for synthesis ───────────────────────────────────────
    # Cap to avoid token overload: 14 web + 6 HN
    web_capped = brave_results[:14]
    hn_capped = hn_results[:6]
    all_combined = web_capped + hn_capped

    web_block = brave_client.format_results_for_prompt(web_capped) if web_capped else "No web results."
    hn_block = _format_hn_results(hn_capped) if hn_capped else "No HN stories found in last 30 days."

    search_results_str = f"### Web Results ({len(web_capped)})\n{web_block}\n\n### Hacker News ({len(hn_capped)})\n{hn_block}"

    prompt = SYNTHESIS_PROMPT.format(
        topic=topic,
        n_results=len(all_combined),
        hn_count=len(hn_capped),
        web_count=len(web_capped),
        search_results=search_results_str,
    )

    # ── 4. Synthesize ──────────────────────────────────────────────────────────
    synthesis = await _synthesize(prompt)

    # ── 5. Format final response ───────────────────────────────────────────────
    ts = datetime.now().strftime("%b %d, %Y %I:%M %p")
    header = (
        f"# last30: {topic}\n"
        f"*{ts} • {len(web_capped)} web + {len(hn_capped)} HN sources*\n\n"
    )
    return header + synthesis


def _format_hn_results(results: List[Dict]) -> str:
    """Format HN results for the synthesis prompt."""
    if not results:
        return "No HN stories."
    lines = []
    for i, r in enumerate(results, 1):
        lines.append(f"{i}. **{r['title']}**")
        lines.append(f"   {r['description']}")
        lines.append(f"   Source: {r['url']}")
    return "\n".join(lines)
