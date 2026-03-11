"""
researcher.py — Overnight research agent for Phantom Command Center.

Every night at 11 PM:
  1. Reads Theodore's memory and recent conversations
  2. Identifies 2-3 topics worth researching tonight
  3. Searches for information (via Brave MCP if available, or Groq)
  4. Summarizes findings and saves reports
  5. Posts to Discord #research-feed
  6. Pings #alerts for urgent findings
"""

import logging
from datetime import datetime
from pathlib import Path

from src.core import memory
from src.core.config import ROOT_DIR
from src.utils import lm_studio_client, groq_client

logger = logging.getLogger(__name__)

RESEARCH_DIR = ROOT_DIR / "memory" / "research"


async def run_nightly_research():
    """Main entry point for the overnight research agent."""
    logger.info("Starting nightly research agent...")
    timestamp = datetime.now().strftime("%Y-%m-%d")

    # Step 1: Gather context about Theodore
    context = memory.get_full_context()

    # Check any queued topics
    queue_file = ROOT_DIR / "memory" / "research-queue.md"
    queued_topics = []
    if queue_file.exists():
        queue_content = queue_file.read_text(encoding="utf-8")
        lines = [l.strip() for l in queue_content.splitlines() if l.strip().startswith("-")]
        queued_topics = [l.lstrip("- ").split("]")[-1].strip() for l in lines]
        # Clear the queue after reading
        queue_file.write_text("# Research Queue\n", encoding="utf-8")

    # Step 2: Ask LM Studio what to research tonight
    topic_prompt = (
        f"Based on what you know about Theodore, identify 2-3 topics worth researching tonight.\n\n"
        f"Context:\n{context[:1500]}\n\n"
        f"Also include these queued topics if any: {', '.join(queued_topics) if queued_topics else 'none'}\n\n"
        f"Output a JSON array like:\n"
        f'[{{"topic": "topic name", "reason": "why it matters to Theodore", "search_query": "search terms"}}]\n\n'
        f"Focus on topics relevant to his current projects, technologies he uses, or things that might surprise and help him."
    )

    topics_json = await lm_studio_client.chat(
        topic_prompt,
        system="You are Phantom, Theodore's AI agent. Identify high-value research topics.",
        max_tokens=500
    )

    topics = _parse_topics(topics_json)
    if not topics:
        logger.warning("No research topics identified tonight")
        return

    logger.info(f"Research topics tonight: {[t['topic'] for t in topics]}")

    # Step 3: Research each topic
    results = []
    for topic_data in topics[:3]:
        topic = topic_data.get("topic", "Unknown")
        reason = topic_data.get("reason", "")
        search_query = topic_data.get("search_query", topic)

        logger.info(f"Researching: {topic}")
        report, sources, urgent = await _research_topic(topic, search_query, reason, context)

        # Save full report
        report_file = RESEARCH_DIR / f"{timestamp}-{_slugify(topic)}.md"
        RESEARCH_DIR.mkdir(parents=True, exist_ok=True)
        report_file.write_text(
            f"# Research: {topic}\n\n**Date**: {timestamp}\n**Reason**: {reason}\n\n{report}",
            encoding="utf-8"
        )

        # Log to research-log.md
        summary = report[:400] + "..." if len(report) > 400 else report
        memory.log_research(topic, summary, str(report_file.relative_to(ROOT_DIR)))

        results.append({
            "topic": topic,
            "reason": reason,
            "summary": summary,
            "sources": sources,
            "urgent": urgent,
            "report_path": str(report_file)
        })

    # Step 4: Post to Discord
    await _post_results_to_discord(results)

    logger.info(f"Nightly research complete. {len(results)} topics covered.")


async def _research_topic(topic: str, search_query: str, reason: str, context: str) -> tuple:
    """
    Research a single topic using Brave Search + Groq synthesis.
    Returns (report_text, sources_list, is_urgent).
    """
    urgent = False

    # Step 1: Fetch real web results via Brave Search
    from src.utils.brave_client import search, format_results_for_prompt
    search_results = await search(search_query, count=6)
    sources = [r["url"] for r in search_results if r.get("url")]
    search_context = format_results_for_prompt(search_results)

    # Step 2: Synthesize findings with Groq
    research_prompt = (
        f"Research this topic: **{topic}**\n\n"
        f"Here are current web search results to use as your sources:\n"
        f"{search_context}\n\n"
        f"Context about Theodore (who this research is for):\n{context[:600]}\n\n"
        f"Based on the search results above, provide:\n"
        f"1. A comprehensive summary (3-5 paragraphs) of what's current\n"
        f"2. Key findings and recent developments from the sources\n"
        f"3. How this relates to Theodore's work and interests\n"
        f"4. Concrete action items or things to watch\n"
        f"5. Flag URGENT: YES at the very start if there's a security issue or breaking change\n\n"
        f"Be specific and cite the sources where relevant."
    )

    report = await groq_client.chat(
        research_prompt,
        system="You are a research analyst. Synthesize web search results into actionable reports.",
        model="llama-3.3-70b-versatile",
        max_tokens=1500
    )

    # Fallback to LM Studio if Groq failed
    if report.startswith("[Groq error:"):
        logger.warning(f"Groq failed for '{topic}', falling back to LM Studio")
        from src.utils import lm_studio_client
        report = await lm_studio_client.chat(
            research_prompt,
            system="You are a research analyst. Synthesize web search results into actionable reports.",
            max_tokens=1500
        )

    # Check for urgency flag
    if "URGENT: YES" in report or "URGENT:" in report[:50]:
        urgent = True
        report = report.replace("URGENT: YES", "").strip()

    return report, sources, urgent


async def _post_results_to_discord(results: list):
    """Deposit research results into DM queue — bot drains it every 2 min."""
    try:
        from src.utils.dm_queue import enqueue_dm

        for result in results:
            urgent  = result.get("urgent", False)
            topic   = result["topic"]
            summary = result["summary"]
            sources = result.get("sources", [])
            path    = result.get("report_path", "")

            # Build message
            tag  = "URGENT — " if urgent else ""
            msg  = f"**{tag}Research: {topic}**\n\n{summary}"
            if sources:
                src_lines = "\n".join(f"• {s}" for s in sources[:3])
                msg += f"\n\n**Sources:**\n{src_lines}"
            if path:
                rel = Path(path).name
                msg += f"\n\n*Full report: `memory/research/{rel}`*"

            enqueue_dm(msg, title=topic, priority=2 if urgent else 0)
            logger.info(f"Research queued for DM: {topic}")

    except Exception as e:
        logger.error(f"Failed to queue research results: {e}")


def _parse_topics(json_str: str) -> list:
    """Parse topics from LM Studio JSON response."""
    import json
    import re

    # Extract JSON array from response
    match = re.search(r'\[.*?\]', json_str, re.DOTALL)
    if not match:
        return []
    try:
        return json.loads(match.group())
    except json.JSONDecodeError:
        logger.warning(f"Failed to parse topics JSON: {json_str[:200]}")
        return []


def _slugify(text: str) -> str:
    """Convert text to a filename-safe slug."""
    import re
    text = text.lower()
    text = re.sub(r'[^a-z0-9]+', '-', text)
    return text.strip('-')[:40]
