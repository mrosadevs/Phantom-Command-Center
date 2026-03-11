"""
morning_debrief.py — Comprehensive 8AM morning briefing for Offline.

Sections (in order):
  1. Overnight Activity    — what Theodore built/researched while Offline slept
  2. Right-Wing Headlines  — top conservative news
  3. Cuba / US Tensions    — latest (Offline is Cuban)
  4. Mexico Cartel         — latest cartel news
  5. Gaming                — latest gaming news
  6. AI & Agents           — OpenAI / Claude / AI agents / automation
  7. Port Charlotte Local  — local FL news
  8. Weather               — Port Charlotte forecast for today
  9. Research Summary      — what Theodore found overnight
 10. Skill Suggestions     — new skills/MCPs to learn (awaits approval)

All news via Brave Search. Synthesis via Groq (fast, free, no tool issues).
Weather via wttr.in (free, no auth needed).
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
logger = logging.getLogger("phantom.morning_debrief")

# ── News search categories ────────────────────────────────────────────────────
NEWS_CATEGORIES = [
    {
        "key":   "rightwing",
        "label": "📰 Top Headlines",
        "query": "breaking news today site:foxnews.com OR site:breitbart.com OR site:dailywire.com OR site:nypost.com",
        "count": 4,
    },
    {
        "key":   "cuba",
        "label": "🇨🇺 Cuba / US Tensions",
        "query": "Cuba United States tensions sanctions relations news 2026",
        "count": 3,
    },
    {
        "key":   "cartel",
        "label": "🇲🇽 Mexico Cartel",
        "query": "Mexico cartel news violence latest 2026",
        "count": 3,
    },
    {
        "key":   "gaming",
        "label": "🎮 Gaming",
        "query": "gaming news releases updates 2026 latest",
        "count": 3,
    },
    {
        "key":   "ai",
        "label": "🤖 AI & Agents",
        "query": "OpenAI Claude AI agents automation LLM news release 2026",
        "count": 4,
    },
    {
        "key":   "portcharlotte",
        "label": "🌴 Port Charlotte Local",
        "query": "Port Charlotte Florida local news 2026",
        "count": 2,
    },
]

SKILL_SEARCH_QUERY = "Claude MCP server new skill tool agent 2026 github"


async def _fetch_weather() -> str:
    """Get Port Charlotte weather forecast from wttr.in (free, no auth)."""
    import httpx
    try:
        url = "https://wttr.in/Port+Charlotte,FL?format=j1"
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url, headers={"User-Agent": "PhantomBot/1.0"})
            resp.raise_for_status()
            data = resp.json()

        current = data["current_condition"][0]
        today = data["weather"][0]

        temp_f = current["temp_F"]
        feels_f = current["FeelsLikeF"]
        desc = current["weatherDesc"][0]["value"]
        humidity = current["humidity"]
        max_f = today["maxtempF"]
        min_f = today["mintempF"]

        hourly = today.get("hourly", [])
        rain_chance = max((int(h.get("chanceofrain", 0)) for h in hourly), default=0)

        return (
            f"**{desc}** | {temp_f}°F (feels {feels_f}°F)\n"
            f"High {max_f}°F / Low {min_f}°F | Humidity {humidity}% | Rain chance {rain_chance}%"
        )
    except Exception as e:
        logger.warning(f"Weather fetch failed: {e}")
        return "Weather unavailable — check wttr.in/Port+Charlotte,FL"


async def _search_news(category: dict) -> List[Dict]:
    """Run a Brave search for one news category."""
    from src.utils import brave_client
    results = await brave_client.search(category["query"], count=category["count"])
    return results


async def _get_overnight_summary() -> str:
    """Pull what was built/researched/branched overnight from memory files."""
    from src.core import memory

    lines = []

    # Check surprises log (overnight builds)
    surprises = memory.read_memory("surprises-log.md")
    if surprises.strip():
        entries = [e for e in surprises.split("##") if e.strip()]
        if entries:
            last = entries[-1].strip()[:400]
            lines.append(f"**Built overnight:**\n{last}")

    # Check research log
    research = memory.read_memory("research-log.md")
    if research.strip():
        entries = [e for e in research.split("##") if e.strip()]
        if entries:
            last = entries[-1].strip()[:400]
            lines.append(f"**Researched overnight:**\n{last}")

    # Check pending branches pushed overnight
    pending_prs_file = ROOT / "memory" / "pending-prs.md"
    if pending_prs_file.exists():
        content = pending_prs_file.read_text(encoding="utf-8").strip()
        entries = [e for e in content.split("##") if e.strip() and not e.strip().startswith("#")]
        if entries:
            # Only show branches from the last 24 hours
            from datetime import timedelta
            cutoff = datetime.now() - timedelta(hours=24)
            recent = []
            for entry in entries:
                # Extract timestamp from "## [YYYY-MM-DD HH:MM] Name"
                import re
                m = re.search(r'\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2})\]', entry)
                if m:
                    try:
                        ts = datetime.strptime(m.group(1), "%Y-%m-%d %H:%M")
                        if ts >= cutoff:
                            recent.append(entry.strip()[:350])
                    except ValueError:
                        pass
            if recent:
                branches_text = "\n\n".join(recent)
                lines.append(
                    f"**Branches pushed — ready for your review:**\n{branches_text}\n\n"
                    f"_Reply `git checkout [branch]` or open a PR when ready._"
                )

    if not lines:
        return "Nothing logged yet — I'll have more for you after the overnight runs kick in."

    return "\n\n".join(lines)


async def _find_skills() -> str:
    """Search for new Claude skills / MCPs Offline might want to learn."""
    from src.utils import brave_client
    results = await brave_client.search(SKILL_SEARCH_QUERY, count=5)
    if not results:
        return "No new skills found tonight."

    lines = []
    for i, r in enumerate(results, 1):
        lines.append(f"{i}. **{r['title']}**\n   {r['description'][:120]}\n   {r['url']}")

    return "\n\n".join(lines) + "\n\n_Reply `learn [url]` for any of these to install._"


async def _synthesize_section(label: str, results: List[Dict]) -> str:
    """Turn Brave results into a tight 3-bullet summary via Groq."""
    from src.utils import groq_client

    if not results:
        return f"{label}\n_No results found._"

    items = "\n".join(
        f"- {r['title']}: {r['description'][:150]} [{r['url']}]"
        for r in results
    )

    prompt = (
        f"Summarize these news items into exactly 3 tight bullet points. "
        f"Lead each bullet with a key fact, name, or number. No filler. No intro sentence.\n\n"
        f"{items}"
    )

    try:
        summary = await groq_client.chat(prompt, max_tokens=300)
        return f"{label}\n{summary.strip()}"
    except Exception as e:
        logger.warning(f"Groq synthesis failed for {label}: {e}")
        # Fallback: raw results
        lines = [f"• {r['title']}" for r in results[:3]]
        return f"{label}\n" + "\n".join(lines)


async def run_morning_debrief():
    """Generate and queue the full morning briefing."""
    from src.utils.dm_queue import enqueue_dm

    now = datetime.now()
    date_str = now.strftime("%A, %B %d %Y")
    logger.info(f"Morning debrief starting — {date_str}")

    # ── Fire all searches in parallel ────────────────────────────────────────
    news_tasks = [_search_news(cat) for cat in NEWS_CATEGORIES]
    weather_task = _fetch_weather()
    overnight_task = _get_overnight_summary()
    skills_task = _find_skills()

    results = await asyncio.gather(*news_tasks, weather_task, overnight_task, skills_task,
                                   return_exceptions=True)

    news_results = results[:len(NEWS_CATEGORIES)]
    weather      = results[len(NEWS_CATEGORIES)]     if not isinstance(results[len(NEWS_CATEGORIES)], Exception) else "Unavailable"
    overnight    = results[len(NEWS_CATEGORIES) + 1] if not isinstance(results[len(NEWS_CATEGORIES) + 1], Exception) else "Error reading logs"
    skills       = results[len(NEWS_CATEGORIES) + 2] if not isinstance(results[len(NEWS_CATEGORIES) + 2], Exception) else "Skill search failed"

    # ── Synthesize each news section in parallel ──────────────────────────────
    section_tasks = [
        _synthesize_section(NEWS_CATEGORIES[i]["label"], news_results[i] if not isinstance(news_results[i], Exception) else [])
        for i in range(len(NEWS_CATEGORIES))
    ]
    sections = await asyncio.gather(*section_tasks, return_exceptions=True)

    # ── Assemble the full briefing ────────────────────────────────────────────
    divider = "─" * 36

    briefing = f"""🌅 **GOOD MORNING, OFFLINE** — {date_str}
{divider}

🔧 **OVERNIGHT ACTIVITY**
{overnight}

{divider}
"""

    for i, cat in enumerate(NEWS_CATEGORIES):
        section = sections[i] if not isinstance(sections[i], Exception) else f"{cat['label']}\n_Section failed_"
        if cat["key"] == "portcharlotte":
            # Insert weather right after local news
            briefing += f"\n{section}\n\n🌤️ **Weather — Port Charlotte**\n{weather}\n\n{divider}\n"
        else:
            briefing += f"\n{section}\n\n{divider}\n"

    briefing += f"""
🧠 **NEW SKILLS I FOUND** _(approve to install)_
{skills}

{divider}
_Theodore • {now.strftime('%I:%M %p EST')} • Phantom Command Center_"""

    # ── Split into Discord-safe chunks (2000 char limit) and queue each ───────
    chunks = _split_message(briefing, max_len=1900)
    for i, chunk in enumerate(chunks):
        title = f"Morning Briefing {date_str}" if i == 0 else f"Morning Briefing {date_str} (cont.)"
        enqueue_dm(chunk, title=title, priority=10)

    logger.info(f"Morning debrief queued: {len(chunks)} chunk(s)")


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
    asyncio.run(run_morning_debrief())
