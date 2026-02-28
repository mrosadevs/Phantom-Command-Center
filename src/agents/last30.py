"""
last30.py — Custom "last30" deep research agent for Phantom Command Center.

Researches ANY topic from the last 30 days using:
  1. Brave Search — 4 targeted query angles (latest, news, discussions, recommendations)
  2. Claude Sonnet — synthesis into a structured, actionable research brief

Triggered via Discord: "last30 AI agents" / "last30 TypeScript 2025" etc.

No OpenAI key needed. Uses Brave API + Claude Max subscription.
"""

import asyncio
import logging
import subprocess
from datetime import datetime
from typing import Optional

from src.utils import brave_client
from src.core.config import ROOT_DIR

logger = logging.getLogger(__name__)

# 4 search angles that surface different types of content
QUERY_ANGLES = [
    "{topic} {year} latest developments",
    "{topic} news {year}",
    "{topic} best tools recommendations {year}",
    "{topic} discussion community opinions",
]

SYNTHESIS_PROMPT = """You are a sharp research analyst. Theodore wants a brief on what's happened with "{topic}" in the last 30 days.

Here are web search results from {n_results} sources:

{search_results}

Write a tight research brief in this format — no fluff, no padding:

## What's New
2-3 bullet points on the biggest recent developments. Be specific.

## Key Findings
4-5 concrete takeaways grounded in the sources. Include numbers/data where available. No vague statements.

## Community Pulse
What's the mood? Any debates, consensus, or emerging opinions worth knowing?

## Worth Acting On
2-3 specific, actionable recommendations based purely on what you found.

## Sources
List 4-6 of the most relevant URLs from the results.

Keep it scannable. Be direct. Only report what's actually in the sources — no hallucinations."""


async def research_last30(topic: str) -> str:
    """
    Run a last-30-days research brief on any topic.
    Uses Brave Search for data gathering, Claude for synthesis.
    """
    logger.info(f"last30 research starting: {topic}")
    year = datetime.now().year

    # ── 1. Gather results from multiple search angles ──────────────────────────
    queries = [q.format(topic=topic, year=year) for q in QUERY_ANGLES]
    all_results = []
    seen_urls = set()

    gather_tasks = [brave_client.search(q, count=4) for q in queries]
    results_per_query = await asyncio.gather(*gather_tasks, return_exceptions=True)

    for results in results_per_query:
        if isinstance(results, Exception):
            continue
        for r in results:
            url = r.get("url", "")
            if url and url not in seen_urls:
                all_results.append(r)
                seen_urls.add(url)

    if not all_results:
        return (
            f"**last30: {topic}**\n\n"
            "Brave Search returned no results — API may be unavailable. Try again shortly."
        )

    # ── 2. Format results for synthesis ───────────────────────────────────────
    search_context = brave_client.format_results_for_prompt(all_results[:14])
    prompt = SYNTHESIS_PROMPT.format(
        topic=topic,
        n_results=len(all_results),
        search_results=search_context,
    )

    # ── 3. Synthesize with Claude (--print mode, Max subscription) ────────────
    synthesis = await _claude_synthesize(prompt)

    # ── 4. Format final response ───────────────────────────────────────────────
    ts = datetime.now().strftime("%b %d, %Y %I:%M %p")
    header = f"# last30: {topic}\n*{ts} • {len(all_results)} sources*\n\n"
    return header + synthesis


async def _claude_synthesize(prompt: str) -> str:
    """
    Call Claude via CLI --print mode for text synthesis.
    Uses Max subscription auth — no API key needed.
    Falls back to Groq if Claude CLI isn't available.
    """
    try:
        import os
        env = {k: v for k, v in __import__('os').environ.items() if k != "CLAUDECODE"}

        proc = await asyncio.create_subprocess_exec(
            "claude", "--print", prompt,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(ROOT_DIR),
            env=env,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=120)

        if proc.returncode == 0:
            output = stdout.decode("utf-8", errors="replace").strip()
            if output:
                logger.info("last30: synthesized with Claude")
                return output

        logger.warning(f"Claude --print failed (exit {proc.returncode}), falling back to Groq")

    except (FileNotFoundError, asyncio.TimeoutError) as e:
        logger.warning(f"Claude CLI unavailable: {e}, falling back to Groq")
    except Exception as e:
        logger.warning(f"Claude synthesis error: {e}, falling back to Groq")

    # ── Groq fallback ──────────────────────────────────────────────────────────
    try:
        from src.utils import groq_client
        return await groq_client.chat(prompt, max_tokens=1400)
    except Exception as e:
        logger.error(f"Groq fallback also failed: {e}")
        return "(Synthesis unavailable — check Claude CLI and Groq API key)"
