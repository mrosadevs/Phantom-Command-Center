"""
evening_debrief.py — Comprehensive 10PM evening debrief for Offline.

Sections (in order):
  1. Day Recap            — what we worked on / talked about today
  2. Theodore's Takes     — observations + suggestions from today's context
  3. Tonight's Research   — what Theodore plans to research overnight
  4. Research Prompt      — asks Offline to add any overnight research topics
  5. Repo Scan            — GitHub repos reviewed, feature ideas / new project ideas
  6. Overnight Build Plan — what Theodore might build tonight

Output queued via dm_queue → delivered by heartbeat loop.
"""

import asyncio
import json
import logging
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("phantom.evening_debrief")


async def _get_todays_context() -> str:
    """
    Reconstruct what happened today from memory files.
    Reads the research log and surprises log for today's entries.
    """
    from src.core import memory

    today = datetime.now().strftime("%Y-%m-%d")
    lines = []

    # Research log — entries from today
    research = memory.read_memory("research-log.md")
    today_research = [e for e in research.split("##") if today in e and e.strip()]
    if today_research:
        lines.append(f"**Researched today:** {len(today_research)} topic(s)")
        for e in today_research[:3]:
            title = e.strip().split("\n")[0][:80]
            lines.append(f"  • {title}")

    # Surprises / builds from today
    surprises = memory.read_memory("surprises-log.md")
    today_builds = [e for e in surprises.split("##") if today in e and e.strip()]
    if today_builds:
        lines.append(f"\n**Built today:** {len(today_builds)} project(s)")
        for e in today_builds[:3]:
            title = e.strip().split("\n")[0][:80]
            lines.append(f"  • {title}")

    # Backlog items added today
    backlog = memory.read_memory("backlog.md")
    today_backlog = [l for l in backlog.splitlines() if today in l and "Queued" in l]
    if today_backlog:
        lines.append(f"\n**Queued for later:** {len(today_backlog)} item(s)")
        for b in today_backlog[:3]:
            lines.append(f"  • {b.strip()[:100]}")

    if not lines:
        return "Quiet day in the logs — conversation history was active though."

    return "\n".join(lines)


async def _get_github_repos() -> List[Dict]:
    """Fetch Offline's GitHub repos via the GitHub API."""
    import httpx
    from src.core.config import get_secret

    token = get_secret("GITHUB_TOKEN", "")
    headers = {"Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                "https://api.github.com/users/mrosadevs/repos",
                headers=headers,
                params={"sort": "updated", "per_page": 10, "type": "owner"},
            )
            resp.raise_for_status()
            repos = resp.json()

        return [
            {
                "name": r["name"],
                "description": r.get("description") or "",
                "language": r.get("language") or "unknown",
                "updated": r.get("updated_at", "")[:10],
                "url": r["html_url"],
                "stars": r.get("stargazers_count", 0),
            }
            for r in repos
            if not r.get("fork")  # skip forks
        ]
    except Exception as e:
        logger.warning(f"GitHub API failed: {e}")
        return []


async def _suggest_repo_features(repos: List[Dict]) -> str:
    """Ask Groq to suggest features or new project ideas based on repo list."""
    from src.utils import groq_client
    from src.core import memory

    if not repos:
        return "Couldn't pull repo list — GitHub API may need a token set."

    ctx = memory.read_memory("about-manuel.md")[:400]
    repo_list = "\n".join(
        f"- {r['name']} ({r['language']}): {r['description']}"
        for r in repos[:8]
    )

    prompt = (
        f"Context about Offline (the developer):\n{ctx}\n\n"
        f"His GitHub repos:\n{repo_list}\n\n"
        f"Give me:\n"
        f"1. ONE specific feature idea for his most interesting repo (be concrete — not generic)\n"
        f"2. ONE completely new project idea that would complement his existing work\n"
        f"Format as two short paragraphs. No intro sentence. Direct and specific."
    )

    try:
        return await groq_client.chat(prompt, max_tokens=400)
    except Exception as e:
        logger.warning(f"Repo feature suggestion failed: {e}")
        return "\n".join(f"• {r['name']}: {r['description'][:80]}" for r in repos[:5])


async def _plan_overnight_research() -> str:
    """Generate a plan for tonight's research based on context."""
    from src.utils import groq_client
    from src.core import memory

    ctx = memory.get_full_context()[:1200]

    prompt = (
        f"Context:\n{ctx}\n\n"
        f"Based on Offline's projects and interests, suggest 2-3 specific research topics "
        f"worth investigating tonight. Each should be:\n"
        f"- Actionable (something that leads to a useful output)\n"
        f"- Relevant to his current work or interests\n"
        f"- Something with fresh content to find (not basics)\n\n"
        f"Format: numbered list, one line each. No fluff."
    )

    try:
        return await groq_client.chat(prompt, max_tokens=300)
    except Exception as e:
        logger.warning(f"Research planning failed: {e}")
        return "1. AI agent frameworks released this week\n2. LM Studio performance with RTX 5080\n3. Cuba/US policy updates"


async def _plan_overnight_build() -> str:
    """Generate what Theodore might build tonight."""
    from src.utils import groq_client
    from src.core import memory

    backlog = memory.read_memory("backlog.md")[:800]
    ctx = memory.read_memory("about-manuel.md")[:400]

    prompt = (
        f"Offline's backlog:\n{backlog}\n\n"
        f"Context:\n{ctx}\n\n"
        f"Pick ONE thing worth building overnight that would genuinely surprise and delight Offline "
        f"when he wakes up. Should be completable in one session and immediately useful.\n"
        f"Format: **Project name** — one sentence on what it is and why it'll be useful."
    )

    try:
        return await groq_client.chat(prompt, max_tokens=200)
    except Exception as e:
        logger.warning(f"Build planning failed: {e}")
        return "Checking backlog for the best overnight build target..."


async def run_evening_debrief():
    """Generate and queue the full evening debrief."""
    from src.utils.dm_queue import enqueue_dm

    now = datetime.now()
    date_str = now.strftime("%A, %B %d %Y")
    logger.info(f"Evening debrief starting — {date_str}")

    # ── Fire everything in parallel ───────────────────────────────────────────
    today_ctx, repos, research_plan, build_plan = await asyncio.gather(
        _get_todays_context(),
        _get_github_repos(),
        _plan_overnight_research(),
        _plan_overnight_build(),
        return_exceptions=True,
    )

    # Handle any exceptions
    if isinstance(today_ctx, Exception):    today_ctx    = "Could not read today's activity log."
    if isinstance(repos, Exception):        repos        = []
    if isinstance(research_plan, Exception): research_plan = "Research planning failed."
    if isinstance(build_plan, Exception):   build_plan   = "Build planning failed."

    # Repo suggestions (needs repos result)
    repo_suggestions = await _suggest_repo_features(repos if isinstance(repos, list) else [])

    divider = "─" * 36

    debrief = f"""🌙 **GOOD EVENING, OFFLINE** — {date_str}
{divider}

📋 **TODAY'S RECAP**
{today_ctx}

{divider}

🔬 **TONIGHT'S RESEARCH PLAN**
{research_plan}

💬 _Reply `research overnight [topic]` to add something specific you want me to dig into._

{divider}

🗂️ **REPO REVIEW & IDEAS**
{repo_suggestions}
"""

    # Add repo list at the bottom
    if isinstance(repos, list) and repos:
        repo_lines = [f"• [{r['name']}]({r['url']}) — {r['description'][:60] or 'no description'}" for r in repos[:6]]
        debrief += "\n**Your repos:**\n" + "\n".join(repo_lines) + "\n"

    debrief += f"""
{divider}

🔨 **OVERNIGHT BUILD PLAN**
{build_plan}

{divider}
_Theodore • {now.strftime('%I:%M %p EST')} • Phantom Command Center_
_I'll be at it while you sleep. See you at 8AM. 🌅_"""

    # Queue in Discord-safe chunks
    chunks = _split_message(debrief, max_len=1900)
    for i, chunk in enumerate(chunks):
        title = f"Evening Debrief {date_str}" if i == 0 else f"Evening Debrief {date_str} (cont.)"
        enqueue_dm(chunk, title=title, priority=10)

    logger.info(f"Evening debrief queued: {len(chunks)} chunk(s)")


def _split_message(text: str, max_len: int = 1900) -> List[str]:
    """Split a long message at newlines to stay within Discord limits."""
    if len(text) <= max_len:
        return [text]

    chunks = []
    current = ""
    for line in text.split("\n"):
        if len(current) + len(line) + 1 > max_len:
            if current:
                chunks.append(current.rstrip())
            current = line + "\n"
        else:
            current += line + "\n"
    if current.strip():
        chunks.append(current.rstrip())
    return chunks


if __name__ == "__main__":
    asyncio.run(run_evening_debrief())
