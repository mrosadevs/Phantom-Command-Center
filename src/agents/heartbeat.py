"""
heartbeat.py — Phantom's proactive thinking loop.

Inspired by OpenClaw's heartbeat architecture:
- Every 30 minutes, reads HEARTBEAT.md checklist + current context
- Asks LM Studio: "anything worth telling Theodore right now?"
- If model says HEARTBEAT_OK → silent, do nothing
- If model surfaces something real → DM Theodore

Separate from the 2-minute disk write (for dashboard) and 6-hour status ping.
"""

import asyncio
import json
import logging
from datetime import datetime, timedelta
from pathlib import Path

from src.core import memory
from src.core.config import ROOT_DIR
from src.utils import lm_studio_client

logger = logging.getLogger(__name__)

HEARTBEAT_FILE = ROOT_DIR / "memory" / "heartbeat.json"
HEARTBEAT_MD   = ROOT_DIR / "memory" / "HEARTBEAT.md"

_bot_start_time: datetime = datetime.now()
_last_heartbeat_dm: datetime = None       # last 6-hour status DM
_last_proactive_check: datetime = None    # last 30-min think cycle
_bot = None

PROACTIVE_INTERVAL_MINUTES = 30   # think cycle
DM_INTERVAL_MINUTES        = 360  # status DM (6 hours)

HEARTBEAT_OK = "HEARTBEAT_OK"


def set_bot(bot_instance):
    global _bot
    _bot = bot_instance


# ── Disk state (keeps dashboard green) ────────────────────────────────────────

def write_heartbeat_state(lm_online: bool, lm_models: list):
    state = {
        "last_heartbeat": datetime.now().isoformat(),
        "start_time": _bot_start_time.isoformat(),
        "lm_studio_online": lm_online,
        "lm_models": lm_models,
        "proactive_interval_minutes": PROACTIVE_INTERVAL_MINUTES,
    }
    HEARTBEAT_FILE.parent.mkdir(parents=True, exist_ok=True)
    HEARTBEAT_FILE.write_text(json.dumps(state, indent=2))


def read_heartbeat_state() -> dict:
    if not HEARTBEAT_FILE.exists():
        return None
    try:
        return json.loads(HEARTBEAT_FILE.read_text())
    except Exception:
        return None


# ── Proactive think cycle (OpenClaw-style) ────────────────────────────────────

async def run_proactive_check(bot):
    """
    Core of the true heartbeat. Reads HEARTBEAT.md + current context,
    asks LM Studio what (if anything) to tell Theodore.
    Silently drops HEARTBEAT_OK. DMs anything real.
    """
    global _last_proactive_check

    now = datetime.now()
    if _last_proactive_check and (now - _last_proactive_check) < timedelta(minutes=PROACTIVE_INTERVAL_MINUTES):
        return

    _last_proactive_check = now

    # Read HEARTBEAT.md checklist
    if not HEARTBEAT_MD.exists():
        return
    checklist = HEARTBEAT_MD.read_text(encoding="utf-8")

    # Gather context to reason over
    context_parts = []

    research_queue = ROOT_DIR / "memory" / "research-queue.md"
    if research_queue.exists():
        q = research_queue.read_text(encoding="utf-8").strip()
        if q and "# Research Queue" not in q or len(q) > 20:
            context_parts.append(f"**Research queue:**\n{q[:400]}")

    backlog = ROOT_DIR / "memory" / "backlog.md"
    if backlog.exists():
        b = backlog.read_text(encoding="utf-8").strip()
        if b:
            context_parts.append(f"**Backlog:**\n{b[:400]}")

    surprises_log = memory.read_memory("surprises-log.md")
    if surprises_log:
        context_parts.append(f"**Recent builds:**\n{surprises_log[-400:]}")

    errors_file = ROOT_DIR / ".learnings" / "ERRORS.md"
    if errors_file.exists():
        errs = errors_file.read_text(encoding="utf-8").strip()
        if errs:
            context_parts.append(f"**Known errors:**\n{errs[:300]}")

    context_str = "\n\n".join(context_parts) if context_parts else "No pending items."

    hour = now.hour
    time_context = f"Current time: {now.strftime('%I:%M %p')} EST"
    in_active_hours = 9 <= hour <= 23

    prompt = (
        f"You are Phantom, Theodore's personal AI agent.\n\n"
        f"{time_context}\n\n"
        f"HEARTBEAT CHECKLIST:\n{checklist}\n\n"
        f"CURRENT CONTEXT:\n{context_str}\n\n"
        f"Check the items above. Active hours (system checks): {'YES' if in_active_hours else 'NO (skip system checks)'}.\n\n"
        f"If nothing genuinely needs Theodore's attention right now → respond ONLY with: HEARTBEAT_OK\n"
        f"If there IS something worth telling him → write a short, direct message (max 3 bullet points).\n"
        f"Do not explain that you ran a heartbeat. Just say what matters."
    )

    try:
        response = await lm_studio_client.chat(
            prompt,
            system="You are a concise, proactive AI agent. Only reach out when there's real signal.",
            max_tokens=300
        )
    except Exception as e:
        logger.warning(f"Proactive check LM Studio call failed: {e}")
        return

    response = response.strip()

    # OpenClaw pattern: HEARTBEAT_OK = silent drop
    if HEARTBEAT_OK in response or response == "" or len(response) < 5:
        logger.info("Proactive check: HEARTBEAT_OK — nothing to report")
        return

    # Something real — DM Theodore
    logger.info(f"Proactive check surfaced something: {response[:80]}")
    await _dm_owner(bot, text=response)


# ── 6-hour status DM ───────────────────────────────────────────────────────────

async def send_heartbeat(bot):
    """6-hour status DM with full health summary."""
    global _last_heartbeat_dm

    now = datetime.now()
    if _last_heartbeat_dm and (now - _last_heartbeat_dm) < timedelta(minutes=DM_INTERVAL_MINUTES):
        return

    _last_heartbeat_dm = now
    logger.info("Sending 6-hour heartbeat DM...")

    lm_online = await lm_studio_client.is_available()
    lm_models = await lm_studio_client.list_models() if lm_online else []
    write_heartbeat_state(lm_online, lm_models)

    surprises_count = memory.read_memory("surprises-log.md").count("## [")
    research_count  = memory.read_memory("research-log.md").count("## [")

    queue_file = ROOT_DIR / "memory" / "research-queue.md"
    queue_items = 0
    if queue_file.exists():
        content = queue_file.read_text()
        queue_items = len([l for l in content.splitlines() if l.strip().startswith("-")])

    next_task = _get_next_task()
    time_str  = now.strftime("%I:%M %p")
    lm_status = f"Online ({', '.join(lm_models[:1]) or 'model loaded'})" if lm_online else "Offline"

    embed = {
        "title": "Phantom Heartbeat",
        "description": f"Still alive as of **{time_str}**",
        "color": 0x7B2FBE,
        "fields": [
            {
                "name": "Services",
                "value": (
                    f"LM Studio: {lm_status}\n"
                    f"Claude Code: Available"
                ),
                "inline": True
            },
            {
                "name": "Activity",
                "value": (
                    f"Builds: **{surprises_count}**\n"
                    f"Research: **{research_count}**\n"
                    f"Queued: **{queue_items}**"
                ),
                "inline": True
            },
            {
                "name": "Next Scheduled",
                "value": next_task,
                "inline": False
            }
        ],
        "footer": {"text": "Phantom Command Center"},
        "timestamp": now.isoformat()
    }

    await _dm_owner(bot, embed=embed)
    logger.info("6-hour heartbeat DM sent")


async def schedule_dm(message: str):
    """Called by APScheduler for dynamic DM jobs."""
    if _bot is None:
        logger.warning("schedule_dm: bot not initialized yet")
        return
    await _dm_owner(_bot, text=message)


# ── Internal helpers ──────────────────────────────────────────────────────────

def _get_next_task() -> str:
    now  = datetime.now()
    hour = now.hour

    schedule = [
        (6,  "Morning Briefing"),
        (22, "Memory Sync"),
        (23, "Nightly Research"),
        (3,  "Overnight Build"),
    ]

    for task_hour, task_name in sorted(schedule, key=lambda x: x[0]):
        if task_hour > hour:
            run_at    = now.replace(hour=task_hour, minute=0, second=0)
            diff      = run_at - now
            hours_away = int(diff.total_seconds() // 3600)
            mins_away  = int((diff.total_seconds() % 3600) // 60)
            return f"**{task_name}** in {hours_away}h {mins_away}m"

    run_at     = now.replace(hour=3, minute=0, second=0) + timedelta(days=1)
    diff       = run_at - now
    hours_away = int(diff.total_seconds() // 3600)
    return f"**Overnight Build** in ~{hours_away}h"


async def _dm_owner(bot, text: str = None, embed: dict = None):
    import discord
    from src.core.config import get_secret

    try:
        guild_id = int(get_secret("PHANTOM_GUILD_ID", "0"))
        if not guild_id:
            return
        guild = bot.get_guild(guild_id)
        if not guild:
            return
        owner = guild.owner
        if not owner:
            return
        dm = await owner.create_dm()
        if embed:
            await dm.send(embed=discord.Embed.from_dict(embed))
        elif text:
            await dm.send(text)
    except Exception as e:
        logger.error(f"DM failed: {e}")
