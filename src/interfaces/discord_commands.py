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

    # Show working context in status
    ctx = memory.get_working_context()
    ctx_detail = f"Focused on: {ctx['name']}" if ctx else "No focus set"

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
        },
        "Working Context": {
            "online": bool(ctx),
            "detail": ctx_detail
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
    ts = datetime.now().strftime("%b %d, %Y %I:%M %p")
    return f"# Gemini Research: {topic}\n*{ts} • Google Search grounded*\n\n{result}"


async def handle_use_model(alias: str) -> str:
    """Handle 'use [model]' — override the auto-router to lock a specific model."""
    from src.core.router import set_override
    return set_override(alias)


async def handle_which_model() -> str:
    """Handle 'which model' / 'what model' — show current override or routing mode."""
    from src.core.router import get_override
    override = get_override()
    if override:
        return (
            f"🔒 Locked to **{override['label']}** (`{override['model']}`)\n"
            f"Say `use auto` to go back to smart routing."
        )
    return (
        "Using **auto-routing** — I pick the best model per task.\n\n"
        "**Switch with:** `use sonnet` · `use opus` · `use haiku` · `use lm` · `use groq` · `use gemini`\n"
        "**Shorthand:** `/sonnet` · `/opus` · `/haiku`\n"
        "**Natural:** `code with opus` · `switch to gemini`\n"
        "**Reset:** `use auto`"
    )


async def handle_codex_scaffold(description: str) -> str:
    """Handle 'codex scaffold [description]' — scaffold a project in CodexCoWork for VS Code."""
    from src.utils import gemini_client
    if not description:
        return "Usage: `codex scaffold [description]` — e.g. `codex scaffold React dashboard`"
    return await gemini_client.scaffold_project(description)


def _parse_schedule_to_cron(time_str: str) -> str:
    """
    Convert natural language time to cron expression.
    Examples: "every day at 9pm" → "0 21 * * *"
              "every morning at 8am" → "0 8 * * *"
              "every friday at 6pm" → "0 18 * * 4"
              "every weekday at noon" → "0 12 * * 1-5"
    Returns cron string or raises ValueError if unparseable.
    """
    t = time_str.lower().strip()

    # Extract hour from "at Xam/pm" or "at X:YY"
    import re
    hour = None
    minute = 0

    match = re.search(r'at\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)?', t)
    if match:
        hour = int(match.group(1))
        if match.group(2):
            minute = int(match.group(2))
        ampm = match.group(3)
        if ampm == "pm" and hour != 12:
            hour += 12
        elif ampm == "am" and hour == 12:
            hour = 0
    elif "noon" in t or "midday" in t:
        hour = 12
    elif "midnight" in t:
        hour = 0
    elif "morning" in t and hour is None:
        hour = 8
    elif "evening" in t and hour is None:
        hour = 18
    elif "night" in t and hour is None:
        hour = 21

    if hour is None:
        raise ValueError(f"Couldn't parse time from: '{time_str}'")

    # Day-of-week
    dow = "*"
    day_map = {
        "sunday": 0, "monday": 1, "tuesday": 2, "wednesday": 3,
        "thursday": 4, "friday": 5, "saturday": 6,
        "sun": 0, "mon": 1, "tue": 2, "wed": 3, "thu": 4, "fri": 5, "sat": 6,
    }
    for day_name, day_num in day_map.items():
        if day_name in t:
            dow = str(day_num)
            break

    if "weekday" in t or "weekdays" in t:
        dow = "1-5"
    elif "weekend" in t or "weekends" in t:
        dow = "0,6"

    return f"{minute} {hour} * * {dow}"


async def handle_schedule(task: str, time_str: str) -> str:
    """Handle 'schedule [task] at [time]' — actually wire it into APScheduler."""
    from src.core.scheduler import add_recurring_job

    try:
        cron = _parse_schedule_to_cron(time_str)
    except ValueError as e:
        return (
            f"Couldn't parse that time: `{time_str}`\n"
            "Try: `every day at 9pm`, `every friday at 6pm`, `every morning at 8am`"
        )

    # Build the DM message for this job
    job_name = task.lower().replace(" ", "_")[:30]
    dm_message = f"⏰ **Scheduled reminder:** {task}"

    result = add_recurring_job(
        name=job_name,
        cron=cron,
        job_type="dm",
        payload=dm_message,
    )
    return f"{result}\n`{cron}` — I'll DM you: *{task}*"


async def handle_work_on(target: str) -> str:
    """
    Handle 'work on [repo/path]' — set the working context so Claude knows
    which repo/project to edit, push to, etc. in subsequent messages.
    """
    from pathlib import Path

    target = target.strip().strip('"\'')

    # Extract just the repo name/URL — first token only.
    # If someone types "work on my-repo rename it and add a readme", we only
    # want "my-repo". Full paths (C:\..., /...) and URLs are kept as-is.
    if " " in target and not target.startswith(("C:", "D:", "/", "~", "http")):
        target = target.split()[0]

    if not target:
        ctx = memory.get_working_context()
        if ctx:
            return (
                f"🎯 Currently focused on: **{ctx['name']}**\n"
                f"Path: `{ctx.get('path', 'N/A')}`\n"
                f"GitHub: {ctx.get('github_url', 'N/A')}\n\n"
                f"Say `clear context` to reset."
            )
        return "No working context set. Say `work on [repo name]` to focus on a repo."

    # Detect if it's a full local path (Windows or Unix)
    if target.startswith(("C:", "D:", "/", "~")):
        path = Path(target.replace("~", str(Path.home())))
        name = path.name
        memory.set_working_context(str(path), name, "local_path")
        return f"🎯 Working context set: **{name}**\nPath: `{path}`"

    # Otherwise treat as a GitHub repo name under mrosadevs
    github_url = f"https://github.com/mrosadevs/{target}"

    # Look for it locally in ClaudeCoWork first, then common spots
    possible_paths = [
        Path("C:/Users/viole/OneDrive/Documents/ClaudeCoWork") / target,
        Path("C:/Users/viole/OneDrive/Documents") / target,
        Path("C:/Users/viole/Documents") / target,
        Path("C:/Users/viole") / target,
    ]
    local_path = next((str(p) for p in possible_paths if p.exists()), "")

    memory.set_working_context(
        local_path or target,
        target,
        "github_repo",
        github_url,
    )

    if local_path:
        return (
            f"🎯 Working context set: **{target}**\n"
            f"Local: `{local_path}`\n"
            f"GitHub: {github_url}\n\n"
            f"Any edits, commits, or pushes will target this repo."
        )
    else:
        return (
            f"🎯 Working context set: **{target}**\n"
            f"GitHub: {github_url}\n"
            f"*(Not found locally — Claude will clone it if needed)*\n\n"
            f"Any edits or pushes will target this repo."
        )


async def handle_show_context() -> str:
    """Show or clear the current working context."""
    ctx = memory.get_working_context()
    if not ctx:
        return (
            "No working context set.\n\n"
            "Use `work on [repo name]` to focus on a specific repo.\n"
            "e.g. `work on color-palette-generator`"
        )
    lines = [f"🎯 **Current Focus: {ctx['name']}**"]
    if ctx.get("path"):
        lines.append(f"Path: `{ctx['path']}`")
    if ctx.get("github_url"):
        lines.append(f"GitHub: {ctx['github_url']}")
    if ctx.get("set_at"):
        lines.append(f"Set at: {ctx['set_at'][:16].replace('T', ' ')}")
    lines.append("\nSay `clear context` to reset.")
    return "\n".join(lines)


async def handle_clear_context() -> str:
    """Clear the current working context."""
    ctx = memory.get_working_context()
    if not ctx:
        return "No working context to clear."
    name = ctx.get("name", "unknown")
    memory.clear_working_context()
    return f"✅ Cleared working context (was: **{name}**). Back to default (ClaudeCoWork)."


async def handle_show_schedule() -> str:
    """Show all active scheduled jobs (static + dynamic)."""
    from src.core.scheduler import get_jobs_status, _load_dynamic_jobs
    jobs = get_jobs_status()
    if not jobs:
        return "No scheduled jobs found."
    lines = ["📅 **Active Schedule:**\n"]
    for j in jobs:
        next_run = j.get("next_run", "unknown")
        if next_run and next_run != "unknown":
            next_run = next_run[:16].replace("T", " ")
        lines.append(f"• **{j['name']}** — next: `{next_run}`")
    dynamic = _load_dynamic_jobs()
    if dynamic:
        lines.append(f"\n🔁 **Your custom jobs ({len(dynamic)}):**")
        for j in dynamic:
            lines.append(f"• `{j['name']}` — `{j['cron']}` — _{j.get('payload', j.get('script', ''))[:60]}_")
        lines.append("\nSay `cancel schedule [name]` to remove one.")
    return "\n".join(lines)


async def handle_cancel_schedule(job_name: str) -> str:
    """Cancel a dynamic scheduled job by name."""
    from src.core.scheduler import remove_recurring_job
    return remove_recurring_job(job_name)


async def handle_general_chat(message: str, channel_id: int = 0) -> str:
    """
    Handle any general message — route to appropriate model.
    Includes conversation history + working context in every request
    so the model always knows what was just discussed and which repo to target.
    Also auto-detects memory-worthy facts and saves them.
    Returns response text with routing info appended.
    """
    from pathlib import Path

    # Get routing decision
    route = await router.route_task(message)
    provider = route["provider"]
    model = route["model"]
    reason = route["reason"]
    footer_model = route.get("label", model) or model

    # ── Build context layers ───────────────────────────────────────────────────
    long_term_ctx = memory.get_full_context()
    # LM Studio/Groq: max 4 turns — local models hallucinate badly with more history
    history_turns = 4 if provider in ("lm-studio", "groq") else 8
    conv_history  = memory.format_conversation_history(channel_id, last_n=history_turns) if channel_id else ""
    wc            = memory.get_working_context()

    # ── Build working context block for Claude — explicit and actionable ───────
    if wc:
        repo_name   = wc.get("name", "unknown")
        github_url  = wc.get("github_url", "")
        stored_path = wc.get("path", "")

        # Re-check if the stored path is a real local directory
        local_path = stored_path if stored_path and Path(stored_path).is_dir() else ""

        # If not local yet, try to find it in common spots
        if not local_path:
            for candidate in [
                Path("C:/Users/viole/OneDrive/Documents/ClaudeCoWork") / repo_name,
                Path("C:/Users/viole/OneDrive/Documents") / repo_name,
                Path("C:/Users/viole") / repo_name,
            ]:
                if candidate.is_dir():
                    local_path = str(candidate)
                    # Update stored path so future calls find it immediately
                    memory.set_working_context(local_path, repo_name, wc.get("kind", "github_repo"), github_url)
                    break

        if local_path:
            cwd_for_claude = local_path
            wc_block = (
                f"╔══ WORKING REPO (read this first) ══╗\n"
                f"  Repo:   {repo_name}\n"
                f"  Path:   {local_path}   ← your cwd, run ALL commands here\n"
                f"  GitHub: {github_url}\n"
                f"╚════════════════════════════════════╝\n"
                f"Do NOT work in the Phantom-Command-Center directory.\n"
                f"cd to the path above and make changes there."
            )
        else:
            # Repo not cloned locally — tell Claude to clone it first
            clone_dest = str(Path("C:/Users/viole/OneDrive/Documents/ClaudeCoWork") / repo_name)
            cwd_for_claude = None
            wc_block = (
                f"╔══ WORKING REPO (read this first) ══╗\n"
                f"  Repo:   {repo_name}\n"
                f"  GitHub: {github_url}\n"
                f"  Not cloned yet — clone to: {clone_dest}\n"
                f"╚════════════════════════════════════╝\n"
                f"Step 1: git clone {github_url} \"{clone_dest}\"\n"
                f"Step 2: cd into it, make the changes requested\n"
                f"Step 3: git add, commit, push\n"
                f"Do NOT work in the Phantom-Command-Center directory."
            )
    else:
        cwd_for_claude = None
        wc_block = "No working context. Default build dir: C:/Users/viole/OneDrive/Documents/ClaudeCoWork/"

    # ── Soul / personality ─────────────────────────────────────────────────────
    soul = memory.get_soul()
    soul_block = soul[:2000] if soul else "You are Theodore, Offline's personal AI. Be direct, sharp, and genuinely helpful. Your name is Theodore."

    # ── System prompt (for LM Studio / Groq / Gemini) ─────────────────────────
    system_prompt = (
        f"{soul_block}\n\n"
        "---\n"
        "HARD RULES — breaking any of these is a failure:\n"
        "- NEVER introduce yourself or explain what you are\n"
        "- NEVER say 'What can I do for you?' or any variation\n"
        "- NEVER use 'Certainly!' 'Of course!' 'Great question!' or any corporate filler\n"
        "- NEVER start with 'I' as the first word\n"
        "- Just respond directly. Match the energy of the message. Be Phantom.\n\n"
        "---\n"
        "ANTI-HALLUCINATION RULES — violating these is a critical failure:\n"
        "- NEVER claim to have built, pushed, deployed, or completed something unless you are literally doing it right now in this response\n"
        "- NEVER fabricate task completions, repo changes, file edits, or GitHub actions\n"
        "- The Recent Conversation below is READ-ONLY history — do NOT continue or repeat it\n"
        "- If you don't know something, say so. Do not invent an answer.\n\n"
        "---\n"
        "MEMORY RULES:\n"
        "1. If Offline tells you a personal fact (birthday, preference, project, goal, habit, "
        "relationship, opinion), append at the END of your response:\n"
        "   SAVE_TO_MEMORY: [the fact in one sentence]\n"
        "2. If you notice a consistent pattern about Offline's preferences or working style "
        "that isn't already in your soul/personality, append:\n"
        "   EVOLVED_TRAIT: [observed trait in one sentence]\n"
        "Only use these tags for genuinely new information. Not for questions or tasks.\n\n"
        f"--- Offline's Memory ---\n{long_term_ctx[:800]}\n\n"
        f"--- Working Context ---\n{wc_block}\n\n"
        + (f"--- Recent Conversation (READ-ONLY — do NOT repeat or continue this) ---\n{conv_history}" if conv_history else "")
    )

    # ── Claude prompt — soul + working context at the very top ────────────────
    conv_block = f"\n\n=== RECENT CONVERSATION ===\n{conv_history}" if conv_history else ""
    claude_prompt = (
        f"=== WHO YOU ARE ===\n{soul_block}\n\n"
        f"=== WORKING CONTEXT ===\n{wc_block}"
        f"{conv_block}\n\n"
        f"=== TASK FROM THEODORE ===\n{message}\n\n"
        f"=== BACKGROUND (Offline's memory) ===\n{long_term_ctx[:600]}"
    )

    # ── Route to provider ──────────────────────────────────────────────────────
    if provider == "lm-studio":
        response = await lm_studio_client.chat(message, system=system_prompt, max_tokens=900)
    elif provider == "groq":
        response = await groq_client.chat(message, system=system_prompt, max_tokens=900)
    elif provider == "gemini":
        from src.utils import gemini_client
        response = await gemini_client.chat(f"{system_prompt}\n\n{message}")
    else:
        # Claude — set cwd to local repo path if we have one
        response = await claude_code_sdk.run_task(
            claude_prompt,
            model=model,
            working_dir=cwd_for_claude,
        )

    # Auto-extract and save any memory facts the model flagged
    response, saved_fact = _extract_and_save_memory(response)

    routing_footer = f"\n\n*{footer_model} • {reason}*"
    if saved_fact:
        routing_footer += f"\n*💾 Saved to memory: {saved_fact}*"
    return response + routing_footer


def _extract_and_save_memory(response: str):
    """
    Look for SAVE_TO_MEMORY: and EVOLVED_TRAIT: tags in model response.
    Saves facts to about-manuel.md and traits to soul.md Evolved Traits.
    Returns (cleaned_response, saved_fact_or_None).
    """
    import re

    saved = None

    # ── SAVE_TO_MEMORY → about-manuel.md (personal facts) ────────────────────
    match = re.search(r'SAVE_TO_MEMORY:\s*(.+?)(?:\n|$)', response, re.IGNORECASE)
    if match:
        fact = match.group(1).strip()
        if fact:
            memory.add_fact(fact)
            logger.info(f"Auto-saved to memory: {fact}")
            saved = fact
        response = re.sub(r'\nSAVE_TO_MEMORY:.*?(?:\n|$)', '', response, flags=re.IGNORECASE).strip()

    # ── EVOLVED_TRAIT → soul.md Evolved Traits section ───────────────────────
    trait_match = re.search(r'EVOLVED_TRAIT:\s*(.+?)(?:\n|$)', response, re.IGNORECASE)
    if trait_match:
        trait = trait_match.group(1).strip()
        if trait:
            memory.append_evolved_trait(trait)
            logger.info(f"Phantom evolved: {trait}")
        response = re.sub(r'\nEVOLVED_TRAIT:.*?(?:\n|$)', '', response, flags=re.IGNORECASE).strip()

    return response, saved


async def handle_news() -> str:
    """
    Fetch latest right-wing headlines on demand.
    Only fires on exact trigger phrases — never on 'gaming news', 'AI news', etc.
    """
    from src.utils import brave_client, groq_client
    from datetime import datetime

    query = (
        "breaking news today site:foxnews.com OR site:breitbart.com OR "
        "site:dailywire.com OR site:nypost.com OR site:thefederalist.com"
    )
    try:
        results = await brave_client.search(query, count=8)
        if not results:
            return "Couldn't pull headlines right now — Brave API may be down. Try again shortly."

        items = "\n".join(
            f"- {r['title']}: {r['description'][:120]} [{r['url']}]"
            for r in results
        )
        prompt = (
            "Summarize these news headlines into 5 tight bullet points. "
            "Lead each bullet with the key fact, name, or number. No intro sentence. No filler.\n\n"
            + items
        )
        synthesis = await groq_client.chat(prompt, max_tokens=700)

        # Always hardcode the links — never rely on the model to include them
        links = "\n".join(
            f"• [{r['title'][:70]}]({r['url']})"
            for r in results[:6] if r.get("url")
        )
        ts = datetime.now().strftime("%I:%M %p")
        return (
            f"📰 **Latest Headlines** — {ts}\n\n"
            f"{synthesis.strip()}\n\n"
            f"**Sources:**\n{links}"
        )
    except Exception as e:
        logger.error(f"News command failed: {e}")
        return f"News fetch failed: {e}"


async def handle_clear_chat(channel_id: int = None) -> str:
    """Wipe conversation history so the model stops hallucinating from stale context."""
    from src.core.memory import clear_conversation_history
    clear_conversation_history(channel_id)
    return "🧹 Conversation history cleared — fresh slate, no stale context."


async def handle_morning_debrief() -> str:
    """Trigger the full morning briefing on-demand (doesn't affect the 8AM cron)."""
    from src.agents.morning_debrief import run_morning_debrief
    try:
        await run_morning_debrief()
        return "Morning briefing queued — incoming in ~2 minutes. ☀️"
    except Exception as e:
        logger.error(f"Morning debrief on-demand failed: {e}")
        return f"Morning debrief failed to run: {e}"


async def handle_evening_debrief() -> str:
    """Trigger the full evening debrief on-demand (doesn't affect the 10PM cron)."""
    from src.agents.evening_debrief import run_evening_debrief
    try:
        await run_evening_debrief()
        return "Evening debrief queued — incoming in ~2 minutes. 🌙"
    except Exception as e:
        logger.error(f"Evening debrief on-demand failed: {e}")
        return f"Evening debrief failed to run: {e}"


def parse_command(message: str) -> Tuple[str, str]:
    """
    Parse a natural language message into (command_type, argument).

    Returns:
        ("learn", "https://...")         for learn commands
        ("install_mcp", "brave search")  for install commands
        ("status", "")                   for status checks
        ("research", "topic")            for research requests
        ("build", "description")         for build requests
        ("remember", "fact")             for remember commands
        ("forget", "keyword")            for forget commands
        ("what_built", "")               for build history queries
        ("what_researched", "")          for research history queries
        ("work_on", "repo/path")         for setting working context
        ("show_context", "")             for showing working context
        ("clear_context", "")            for clearing working context
        ("general", original_message)   for everything else
    """
    msg = message.strip().lower()

    if msg == "status" or msg == "ping" or "system status" in msg:
        return ("status", "")

    # News command — exact phrases only. "latest news on X" or "news about X" goes to general/last30.
    _NEWS_TRIGGERS = {
        "news", "latest news", "top news", "headlines",
        "latest headlines", "top headlines", "breaking news",
    }
    if msg in _NEWS_TRIGGERS:
        return ("news", "")

    if msg.startswith("learn "):
        return ("learn", message[6:].strip())

    if msg.startswith("install "):
        return ("install_mcp", message[8:].strip())

    if msg.startswith("remember "):
        return ("remember", message[9:].strip())

    if msg.startswith("forget "):
        return ("forget", message[7:].strip())

    # On-demand debriefs — fire immediately, cron still runs at scheduled time
    if any(p in msg for p in ("morning debrief", "morning briefing", "morning brief",
                               "give me my morning", "send morning")):
        return ("morning_debrief", "")

    if any(p in msg for p in ("evening debrief", "evening briefing", "evening brief",
                               "give me my evening", "send evening",
                               "night debrief", "nightly debrief")):
        return ("evening_debrief", "")

    if "research" in msg and ("tonight" in msg or "overnight" in msg):
        topic = message.lower().replace("research", "").replace("tonight", "").replace("overnight", "").strip()
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

    # /opus /sonnet /haiku /lm /groq /gemini shorthand
    if msg.startswith("/") and msg[1:].split()[0] in ("opus", "sonnet", "haiku", "lm", "groq", "gemini", "auto"):
        alias = msg[1:].split()[0]
        return ("use_model", alias)

    # "use X" — explicit switch
    if msg.startswith("use "):
        return ("use_model", message[4:].strip())

    # "code with opus / sonnet / haiku" — natural language switch
    for alias in ("opus", "sonnet", "haiku", "lm", "groq", "gemini"):
        if f"with {alias}" in msg or f"switch to {alias}" in msg or f"switch {alias}" in msg:
            return ("use_model", alias)

    if msg in ("which model", "what model", "what model are you using", "which model are you using", "model?"):
        return ("which_model", "")

    if msg.startswith("gemini research ") or msg.startswith("g research "):
        topic = message.split(" ", 2)[2].strip()
        return ("gemini_research", topic)

    if msg.startswith("codex scaffold ") or msg.startswith("scaffold "):
        desc = message.split(" ", 2)[2].strip() if msg.startswith("codex scaffold ") else message.split(" ", 1)[1].strip()
        return ("codex_scaffold", desc)

    # Working context commands
    if msg.startswith("work on ") or msg.startswith("focus on ") or msg.startswith("set repo "):
        # strip the prefix
        for prefix in ("work on ", "focus on ", "set repo "):
            if msg.startswith(prefix):
                return ("work_on", message[len(prefix):].strip())

    if msg in ("context", "what context", "what are we working on", "current context", "what repo"):
        return ("show_context", "")

    if msg in ("clear context", "reset context", "no context", "unfocus"):
        return ("clear_context", "")

    if msg in ("clear chat", "clear history", "reset chat", "forget conversation",
               "clear conversation", "start fresh", "new conversation"):
        return ("clear_chat", "")

    # Schedule management
    if msg in ("my schedule", "schedules", "scheduled jobs", "what's scheduled", "show schedule"):
        return ("show_schedule", "")

    if msg.startswith("cancel schedule ") or msg.startswith("remove schedule "):
        job_name = message.split(" ", 2)[2].strip()
        return ("cancel_schedule", job_name)

    return ("general", message)
