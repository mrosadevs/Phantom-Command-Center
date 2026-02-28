"""
discord_commands.py — Natural language command handlers for the Discord bot.

Each handler function processes a specific type of message and returns
a response string (or embed dict) to send back to the user.
"""

import logging
from datetime import datetime
from typing import Tuple, Optional

from src.core import memory, router
from src.core.config import ROOT_DIR
from src.utils import lm_studio_client, claude_code_sdk, groq_client

logger = logging.getLogger(__name__)


async def handle_status() -> Tuple[str, dict]:
    """Return system health status."""
    from src.interfaces.webhook_sender import build_status_embed
    from src.utils import lm_studio_client as lms

    lm_online = await lms.is_available()
    lm_models = await lms.list_models() if lm_online else []

    services = {
        "LM Studio": {
            "online": lm_online,
            "detail": f"Models loaded: {', '.join(lm_models)}" if lm_models else "No models loaded"
        },
        "Claude Code": {
            "online": True,
            "detail": "Available via Max subscription"
        },
        "Groq": {
            "online": True,
            "detail": "Free tier connected"
        },
        "Dashboard": {
            "online": True,
            "detail": "Running at http://localhost:3000"
        }
    }

    embed = build_status_embed(services)
    return "", embed


async def handle_learn(url_or_name: str) -> str:
    """Handle 'learn [url/name]' — delegate to skill manager."""
    from src.agents.skill_manager import install_skill
    result = await install_skill(url_or_name)
    return result


async def handle_install_mcp(mcp_name: str) -> str:
    """Handle 'install [mcp name]' — delegate to skill manager."""
    from src.agents.skill_manager import install_mcp
    result = await install_mcp(mcp_name)
    return result


async def handle_remember(fact: str) -> str:
    """Handle 'remember [fact]' — save to memory."""
    memory.add_fact(fact)
    return f"Got it! I've remembered: *{fact}*"


async def handle_forget(keyword: str) -> str:
    """Handle 'forget [thing]' — remove from memory."""
    removed = memory.remove_fact(keyword)
    if removed:
        return f"Removed memories containing: *{keyword}*"
    return f"I couldn't find anything about *{keyword}* in my memory."


async def handle_research_tonight(topic: str) -> str:
    """Queue a research topic for tonight's research run."""
    queue_file = ROOT_DIR / "memory" / "research-queue.md"
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    with open(queue_file, "a") as f:
        f.write(f"\n- [{timestamp}] {topic}")
    return f"Queued for tonight's research: **{topic}** — I'll have findings in the morning!"


async def handle_build(description: str) -> str:
    """Handle 'build me [description]' — delegate to builder agent."""
    from src.agents.builder import build_on_demand
    result = await build_on_demand(description)
    return result


async def handle_what_did_you_build() -> str:
    """Return a summary of the last overnight build."""
    content = memory.read_memory("surprises-log.md")
    if not content.strip() or content.strip() == "# Overnight Surprises Log":
        return "I haven't built anything proactively yet — check back after 2 AM!"

    # Return last entry
    sections = content.split("##")
    if len(sections) > 1:
        last = sections[-1].strip()
        return f"**Most recent overnight build:**\n```\n{last[:800]}\n```"
    return content[-600:]


async def handle_what_did_you_research() -> str:
    """Return a summary of recent research."""
    content = memory.read_memory("research-log.md")
    if not content.strip() or content.strip() == "# Research Log":
        return "No research recorded yet. I'll start tonight at 11 PM!"

    sections = content.split("##")
    if len(sections) > 1:
        last = sections[-1].strip()
        return f"**Most recent research:**\n```\n{last[:800]}\n```"
    return content[-600:]


async def handle_last30(topic: str) -> str:
    """Handle 'last30 [topic]' — deep research brief on any topic from the last 30 days."""
    from src.agents.last30 import research_last30
    if not topic:
        return "Usage: `last30 [topic]` — e.g. `last30 AI coding tools`"
    return await research_last30(topic)


async def handle_gemini_research(topic: str) -> str:
    """Handle 'gemini research [topic]' — deep research via Gemini with Google Search."""
    from src.utils import gemini_client
    if not topic:
        return "Usage: `gemini research [topic]` — uses Gemini + Google Search for deep research"
    result = await gemini_client.research(topic)
    from datetime import datetime
    ts = datetime.now().strftime("%b %d, %Y %I:%M %p")
    return f"# Gemini Research: {topic}\n*{ts} • Google Search grounded*\n\n{result}"


async def handle_codex_scaffold(description: str) -> str:
    """Handle 'codex scaffold [description]' — scaffold a project in CodexCoWork for VS Code."""
    from src.utils import gemini_client
    if not description:
        return "Usage: `codex scaffold [description]` — e.g. `codex scaffold React dashboard`"
    return await gemini_client.scaffold_project(description)


async def handle_schedule(task: str, time_str: str) -> str:
    """Handle 'schedule [task] at [time]' — add to scheduler."""
    # For now, queue it in a schedule requests file for review
    queue_file = ROOT_DIR / "memory" / "schedule-requests.md"
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    with open(queue_file, "a") as f:
        f.write(f"\n- [{timestamp}] Task: {task} | At: {time_str}")
    return f"Scheduled: **{task}** at **{time_str}** — I'll take care of it!"


async def handle_general_chat(message: str) -> str:
    """
    Handle any general message — route to appropriate model.
    Also auto-detects memory-worthy facts and saves them.
    Returns response text with routing info appended.
    """
    # Get routing decision
    route = await router.route_task(message)
    provider = route["provider"]
    model = route["model"]
    reason = route["reason"]

    # Get memory context for richer responses
    context = memory.get_full_context()

    system_prompt = (
        "You are Phantom, Theodore's personal AI agent. You know everything about him "
        "from the context below. Be helpful, direct, and occasionally proactive.\n\n"
        "IMPORTANT MEMORY RULE: If Theodore tells you a personal fact about himself "
        "(birthday, preference, project, goal, interest, habit, relationship, location, etc.), "
        "you MUST include this exact line at the END of your response (no exceptions):\n"
        "SAVE_TO_MEMORY: [the fact in one clear sentence]\n\n"
        "Only include SAVE_TO_MEMORY if there's actually a new fact to save. "
        "Don't save it for questions, tasks, or things you already know.\n\n"
        f"--- Theodore's Memory Context ---\n{context[:2000]}"
    )

    # Route to the right provider
    if provider == "lm-studio":
        response = await lm_studio_client.chat(message, system=system_prompt, max_tokens=900)
    elif provider == "groq":
        response = await groq_client.chat(message, system=system_prompt, max_tokens=900)
    else:
        full_prompt = f"[Context about Theodore]\n{context[:1000]}\n\n[Message]\n{message}"
        response = await claude_code_sdk.run_task(full_prompt)

    # Auto-extract and save any memory facts the model flagged
    response, saved_fact = _extract_and_save_memory(response)

    # Append routing info
    routing_footer = f"\n\n*{model} • {reason}*"
    if saved_fact:
        routing_footer += f"\n*💾 Saved to memory: {saved_fact}*"
    return response + routing_footer


def _extract_and_save_memory(response: str):
    """
    Look for SAVE_TO_MEMORY: tag in model response, save it, strip the tag.
    Returns (cleaned_response, saved_fact_or_None).
    """
    import re
    match = re.search(r'SAVE_TO_MEMORY:\s*(.+?)(?:\n|$)', response, re.IGNORECASE)
    if match:
        fact = match.group(1).strip()
        if fact:
            memory.add_fact(fact)
            logger.info(f"Auto-saved to memory: {fact}")
        # Remove the tag from the response
        cleaned = re.sub(r'\nSAVE_TO_MEMORY:.*?(?:\n|$)', '', response, flags=re.IGNORECASE).strip()
        return cleaned, fact
    return response, None


def parse_command(message: str) -> Tuple[str, str]:
    """
    Parse a natural language message into (command_type, argument).

    Returns:
        ("learn", "https://...") for learn commands
        ("install_mcp", "brave search") for install commands
        ("status", "") for status checks
        ("research", "topic") for research requests
        ("build", "description") for build requests
        ("remember", "fact") for remember commands
        ("forget", "keyword") for forget commands
        ("what_built", "") for build history queries
        ("what_researched", "") for research history queries
        ("general", original_message) for everything else
    """
    msg = message.strip().lower()

    if msg == "status" or msg == "ping" or "system status" in msg:
        return ("status", "")

    if msg.startswith("learn "):
        return ("learn", message[6:].strip())

    if msg.startswith("install "):
        return ("install_mcp", message[8:].strip())

    if msg.startswith("remember "):
        return ("remember", message[9:].strip())

    if msg.startswith("forget "):
        return ("forget", message[7:].strip())

    if "research" in msg and "tonight" in msg:
        topic = message.lower().replace("research", "").replace("tonight", "").strip()
        return ("research", topic)

    if msg.startswith("build me ") or msg.startswith("build "):
        desc = message[9:].strip() if msg.startswith("build me ") else message[6:].strip()
        return ("build", desc)

    if "what did you build" in msg or "what have you built" in msg or "overnight build" in msg:
        return ("what_built", "")

    if "what did you research" in msg or "research log" in msg or "what have you researched" in msg:
        return ("what_researched", "")

    if msg.startswith("schedule ") and " at " in msg:
        parts = message[9:].split(" at ", 1)
        return ("schedule", f"{parts[0].strip()}|||{parts[1].strip()}")

    if msg.startswith("last30 ") or msg.startswith("last 30 "):
        topic = message.split(" ", 1)[1].strip() if msg.startswith("last30 ") else message.split(" ", 2)[2].strip()
        return ("last30", topic)

    if msg.startswith("gemini research ") or msg.startswith("g research "):
        topic = message.split(" ", 2)[2].strip()
        return ("gemini_research", topic)

    if msg.startswith("codex scaffold ") or msg.startswith("scaffold "):
        desc = message.split(" ", 2)[2].strip() if msg.startswith("codex scaffold ") else message.split(" ", 1)[1].strip()
        return ("codex_scaffold", desc)

    return ("general", message)
