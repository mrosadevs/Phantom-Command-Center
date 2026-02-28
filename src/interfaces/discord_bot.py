"""
discord_bot.py — Main Discord bot for Phantom Command Center.

Theodore's primary interface. Listens in #phantom-commands and responds
to natural language. Routes tasks through the smart router.

Run with: python src/interfaces/discord_bot.py
"""

import asyncio
import logging
import os
import sys
from pathlib import Path

import discord
from discord.ext import commands

# Add project root to path
ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from src.core.config import CONFIG, get_secret
from src.core import memory as mem_module
from src.core.scheduler import start as start_scheduler, stop as stop_scheduler
from src.agents.heartbeat import send_heartbeat, set_bot as heartbeat_set_bot
from src.interfaces.discord_commands import parse_command, handle_general_chat
from src.interfaces.discord_commands import (
    handle_status, handle_learn, handle_install_mcp,
    handle_remember, handle_forget, handle_research_tonight,
    handle_build, handle_what_did_you_build, handle_what_did_you_research,
    handle_schedule, handle_last30, handle_gemini_research, handle_codex_scaffold,
    handle_use_model, handle_which_model,
    handle_work_on, handle_show_context, handle_clear_context,
    handle_show_schedule, handle_cancel_schedule,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("phantom.bot")

# Discord intents — need message content to read messages
intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True

bot = commands.Bot(command_prefix="!", intents=intents)

# Channel names from config
CHANNEL_COMMANDS = CONFIG["discord"]["channels"]["commands"]
CHANNEL_BRIEFING = CONFIG["discord"]["channels"]["briefing"]
CHANNEL_SURPRISES = CONFIG["discord"]["channels"]["surprises"]
CHANNEL_RESEARCH = CONFIG["discord"]["channels"]["research"]
CHANNEL_ALERTS = CONFIG["discord"]["channels"]["alerts"]


@bot.event
async def on_ready():
    """Called when the bot connects to Discord."""
    logger.info(f"Phantom connected as {bot.user} (ID: {bot.user.id})")

    # Give heartbeat module access to the bot (needed for scheduled DMs)
    heartbeat_set_bot(bot)

    # Start the task scheduler
    try:
        start_scheduler()
        logger.info("Task scheduler started")
    except Exception as e:
        logger.error(f"Failed to start scheduler: {e}")

    # Start heartbeat background loop
    bot.loop.create_task(_heartbeat_loop())

    # Send startup notification to commands channel if it exists
    guild_id = int(get_secret("PHANTOM_GUILD_ID", "0"))
    if guild_id:
        guild = bot.get_guild(guild_id)
        if guild:
            channel = discord.utils.get(guild.text_channels, name=CHANNEL_COMMANDS)
            if channel:
                embed = discord.Embed(
                    title="🔮 Phantom is Online",
                    description="I'm awake and ready. What do you need?",
                    color=0x7B2FBE
                )
                embed.add_field(name="Try", value=(
                    "`status` — system health\n"
                    "`work on [repo]` — focus on a specific repo\n"
                    "`build me [description]` — build something\n"
                    "`last30 [topic]` — 30-day research brief\n"
                    "`gemini research [topic]` — Google-grounded research\n"
                    "`use opus` / `use lm` / `use auto` — switch models\n"
                    "Or just chat naturally!"
                ), inline=False)
                await channel.send(embed=embed)


@bot.event
async def on_message(message: discord.Message):
    """Handle incoming messages — DMs or #phantom-commands."""
    # Ignore bot's own messages
    if message.author.bot:
        return

    is_dm = isinstance(message.channel, discord.DMChannel)
    is_commands_channel = hasattr(message.channel, 'name') and message.channel.name == CHANNEL_COMMANDS

    # Respond in DMs or in the commands channel
    if not is_dm and not is_commands_channel:
        return

    content = message.content.strip()
    if not content:
        return

    channel_id = message.channel.id
    logger.info(f"Message from {message.author} [ch:{channel_id}]: {content[:80]}")

    # ── Record user turn in conversation history ──────────────────────────────
    mem_module.add_conversation_turn(channel_id, "user", content)

    # Show typing indicator while processing
    async with message.channel.typing():
        try:
            response_text, embed = await dispatch_command(content, channel_id=channel_id)
        except Exception as e:
            logger.error(f"Command dispatch error: {e}", exc_info=True)
            response_text = f"Something went wrong: `{e}`"
            embed = None

    # ── Record bot response in conversation history ───────────────────────────
    if response_text:
        # Strip the routing footer before saving to history (cleaner)
        history_text = response_text.split("\n\n*")[0][:800]
        mem_module.add_conversation_turn(channel_id, "assistant", history_text)

    # Send response
    if embed:
        await message.channel.send(content=response_text or None, embed=discord.Embed.from_dict(embed))
    elif response_text:
        # Split long messages
        for chunk in _chunk_message(response_text):
            await message.channel.send(chunk)


async def dispatch_command(message: str, channel_id: int = 0) -> tuple:
    """
    Parse and dispatch a message to the right handler.
    Returns (response_text, embed_dict_or_None).
    channel_id is passed to general chat so it can include conversation history.
    """
    command, arg = parse_command(message)

    if command == "status":
        text, embed = await handle_status()
        return text, embed

    elif command == "learn":
        text = await handle_learn(arg)
        return text, None

    elif command == "install_mcp":
        text = await handle_install_mcp(arg)
        return text, None

    elif command == "remember":
        text = await handle_remember(arg)
        return text, None

    elif command == "forget":
        text = await handle_forget(arg)
        return text, None

    elif command == "research":
        text = await handle_research_tonight(arg)
        return text, None

    elif command == "build":
        text = await handle_build(arg)
        return text, None

    elif command == "what_built":
        text = await handle_what_did_you_build()
        return text, None

    elif command == "what_researched":
        text = await handle_what_did_you_research()
        return text, None

    elif command == "last30":
        text = await handle_last30(arg)
        return text, None

    elif command == "gemini_research":
        text = await handle_gemini_research(arg)
        return text, None

    elif command == "use_model":
        text = await handle_use_model(arg)
        return text, None

    elif command == "which_model":
        text = await handle_which_model()
        return text, None

    elif command == "codex_scaffold":
        text = await handle_codex_scaffold(arg)
        return text, None

    elif command == "schedule":
        parts = arg.split("|||")
        task = parts[0] if len(parts) > 0 else arg
        time_str = parts[1] if len(parts) > 1 else "unspecified time"
        text = await handle_schedule(task, time_str)
        return text, None

    elif command == "work_on":
        text = await handle_work_on(arg)
        return text, None

    elif command == "show_context":
        text = await handle_show_context()
        return text, None

    elif command == "clear_context":
        text = await handle_clear_context()
        return text, None

    elif command == "show_schedule":
        text = await handle_show_schedule()
        return text, None

    elif command == "cancel_schedule":
        text = await handle_cancel_schedule(arg)
        return text, None

    else:
        # General chat — pass channel_id so it has conversation history
        text = await handle_general_chat(message, channel_id=channel_id)
        return text, None


def _chunk_message(text: str, max_len: int = 1990) -> list:
    """Split a long message into Discord-safe chunks."""
    if len(text) <= max_len:
        return [text]
    chunks = []
    while len(text) > max_len:
        # Try to split at a newline
        split_at = text.rfind("\n", 0, max_len)
        if split_at == -1:
            split_at = max_len
        chunks.append(text[:split_at])
        text = text[split_at:].lstrip()
    if text:
        chunks.append(text)
    return chunks


async def send_to_channel(channel_name: str, text: str = None, embed: dict = None):
    """
    Utility to send a message to a specific channel by name.
    Used by overnight agents to post results.
    """
    guild_id = int(get_secret("PHANTOM_GUILD_ID", "0"))
    if not guild_id:
        logger.warning("PHANTOM_GUILD_ID not set — cannot send to channel")
        return

    guild = bot.get_guild(guild_id)
    if not guild:
        logger.warning(f"Guild {guild_id} not found")
        return

    channel = discord.utils.get(guild.text_channels, name=channel_name)
    if not channel:
        logger.warning(f"Channel #{channel_name} not found in guild")
        return

    if embed:
        await channel.send(content=text, embed=discord.Embed.from_dict(embed))
    elif text:
        for chunk in _chunk_message(text):
            await channel.send(chunk)


async def _heartbeat_loop():
    """
    Two-speed background loop:
      - Writes alive state to disk every 2 minutes (keeps dashboard green)
      - Sends DM to Theodore every 6 hours (per HEARTBEAT_INTERVAL_MINUTES)
    """
    from src.agents.heartbeat import write_heartbeat_state
    from src.utils import lm_studio_client as lms

    await bot.wait_until_ready()

    # Write immediately on startup so dashboard goes green right away
    lm_online = await lms.is_available()
    lm_models = await lms.list_models() if lm_online else []
    write_heartbeat_state(lm_online, lm_models)

    while not bot.is_closed():
        # Always write state every 2 minutes so dashboard stays current
        lm_online = await lms.is_available()
        lm_models = await lms.list_models() if lm_online else []
        write_heartbeat_state(lm_online, lm_models)

        # Only DM Offline on the 6-hour interval
        await send_heartbeat(bot)

        # ── Drain DM queue (cron scripts deposit messages here) ───────────────
        try:
            from src.utils.dm_queue import drain_queue
            from src.agents.heartbeat import _dm_owner
            pending = drain_queue()
            for item in pending:
                content = item.get("content", "")
                if content:
                    # Split into Discord-safe chunks
                    for chunk in _chunk_message(content):
                        await _dm_owner(bot, text=chunk)
                    await asyncio.sleep(0.5)  # small delay between chunks
        except Exception as e:
            logger.warning(f"DM queue drain failed: {e}")

        await asyncio.sleep(60 * 2)  # Tick every 2 minutes


def run():
    """Start the bot."""
    token = get_secret("PHANTOM_DISCORD_TOKEN")
    logger.info("Starting Phantom Discord bot...")
    bot.run(token)


if __name__ == "__main__":
    run()
