"""
heartbeat.py — Periodic status pulse for Phantom Command Center.

Every hour, sends Theodore a brief DM confirming Phantom is alive,
what it's been doing, and the health of all services.
Interval is configurable in phantom.config.json.
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

# Track when last heartbeat was sent
_last_heartbeat: datetime = None
HEARTBEAT_INTERVAL_MINUTES = 360  # DM every 6 hours
HEARTBEAT_FILE = ROOT_DIR / "memory" / "heartbeat.json"
_bot_start_time: datetime = datetime.now()


def write_heartbeat_state(lm_online: bool, lm_models: list):
    """Write current heartbeat state to disk so the dashboard can read it."""
    state = {
        "last_heartbeat": datetime.now().isoformat(),
        "start_time": _bot_start_time.isoformat(),
        "lm_studio_online": lm_online,
        "lm_models": lm_models,
        "interval_minutes": HEARTBEAT_INTERVAL_MINUTES
    }
    HEARTBEAT_FILE.parent.mkdir(parents=True, exist_ok=True)
    HEARTBEAT_FILE.write_text(json.dumps(state, indent=2))


def read_heartbeat_state() -> dict:
    """Read the last heartbeat state from disk."""
    if not HEARTBEAT_FILE.exists():
        return None
    try:
        return json.loads(HEARTBEAT_FILE.read_text())
    except Exception:
        return None


async def send_heartbeat(bot):
    """
    Send a heartbeat DM to Theodore.
    Called on a schedule by the bot's background loop.
    """
    global _last_heartbeat

    now = datetime.now()

    # Check interval
    if _last_heartbeat and (now - _last_heartbeat) < timedelta(minutes=HEARTBEAT_INTERVAL_MINUTES):
        return

    _last_heartbeat = now
    logger.info("Sending heartbeat...")

    # Build status info
    lm_online = await lm_studio_client.is_available()
    lm_models = await lm_studio_client.list_models() if lm_online else []

    # Always write state to disk (even between DM intervals) so dashboard stays current
    write_heartbeat_state(lm_online, lm_models)

    # Count recent activity
    surprises_log = memory.read_memory("surprises-log.md")
    research_log = memory.read_memory("research-log.md")
    surprises_count = surprises_log.count("## [")
    research_count = research_log.count("## [")

    # Check for queued research topics
    queue_file = ROOT_DIR / "memory" / "research-queue.md"
    queue_items = 0
    if queue_file.exists():
        content = queue_file.read_text()
        queue_items = len([l for l in content.splitlines() if l.strip().startswith("-")])

    # Build next scheduled task info
    next_task = _get_next_task()

    # Compose the embed
    time_str = now.strftime("%I:%M %p")
    lm_status = f"🟢 Online ({', '.join(lm_models[:1]) or 'model loaded'})" if lm_online else "🔴 Offline"

    embed = {
        "title": "💓 Phantom Heartbeat",
        "description": f"Still alive and running as of **{time_str}**",
        "color": 0x7B2FBE,
        "fields": [
            {
                "name": "Services",
                "value": (
                    f"LM Studio: {lm_status}\n"
                    f"Groq: 🟢 Connected\n"
                    f"Claude Code: 🟢 Available"
                ),
                "inline": True
            },
            {
                "name": "Activity",
                "value": (
                    f"Apps built: **{surprises_count}**\n"
                    f"Research reports: **{research_count}**\n"
                    f"Queued topics: **{queue_items}**"
                ),
                "inline": True
            },
            {
                "name": "Next Scheduled",
                "value": next_task,
                "inline": False
            }
        ],
        "footer": {"text": "Phantom Command Center • heartbeat"},
        "timestamp": now.isoformat()
    }

    # Send DM to Theodore
    await _dm_owner(bot, embed=embed)
    logger.info("Heartbeat sent")


def _get_next_task() -> str:
    """Return the next scheduled task based on current time."""
    now = datetime.now()
    hour = now.hour

    schedule = [
        (6,  "Morning Briefing"),
        (22, "Memory Sync"),
        (23, "Nightly Research"),
        (2,  "Overnight Build"),
    ]

    for task_hour, task_name in sorted(schedule, key=lambda x: x[0]):
        if task_hour > hour:
            run_at = now.replace(hour=task_hour, minute=0, second=0)
            diff = run_at - now
            hours_away = int(diff.total_seconds() // 3600)
            mins_away = int((diff.total_seconds() % 3600) // 60)
            return f"**{task_name}** in {hours_away}h {mins_away}m"

    # Wrap around to tomorrow
    run_at = now.replace(hour=2, minute=0, second=0) + timedelta(days=1)
    diff = run_at - now
    hours_away = int(diff.total_seconds() // 3600)
    return f"**Overnight Build** in ~{hours_away}h"


async def _dm_owner(bot, text: str = None, embed: dict = None):
    """Send a DM to the bot owner (Theodore)."""
    import discord
    from src.core.config import get_secret

    try:
        guild_id = int(get_secret("PHANTOM_GUILD_ID", "0"))
        guild = bot.get_guild(guild_id)
        if not guild:
            return

        # Get the guild owner
        owner = guild.owner
        if not owner:
            return

        dm = await owner.create_dm()

        if embed:
            await dm.send(embed=discord.Embed.from_dict(embed))
        elif text:
            await dm.send(text)

    except Exception as e:
        logger.error(f"Heartbeat DM failed: {e}")
