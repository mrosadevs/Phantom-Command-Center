"""
webhook_sender.py — Sends rich Discord embeds to channels via webhooks or the bot client.

Used by overnight agents to post briefings, research, and surprises
without needing the full bot to be running interactively.
"""

import logging
from datetime import datetime
from typing import Optional

import httpx

logger = logging.getLogger(__name__)


async def send_webhook(webhook_url: str, embed: dict, content: str = None):
    """
    Send a Discord embed to a webhook URL.

    Args:
        webhook_url: Discord webhook URL
        embed: Discord embed object (dict)
        content: Optional plain text message above the embed
    """
    payload = {"embeds": [embed]}
    if content:
        payload["content"] = content

    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(webhook_url, json=payload)
        if resp.status_code not in (200, 204):
            logger.error(f"Webhook failed ({resp.status_code}): {resp.text}")
        else:
            logger.info("Webhook sent successfully")


def build_briefing_embed(
    title: str,
    sections: dict,
    color: int = 0x7B2FBE
) -> dict:
    """
    Build a morning briefing embed.

    Args:
        title: Embed title
        sections: dict of {section_name: content_string}
        color: Embed color (hex int, default: phantom purple)
    """
    fields = [
        {"name": name, "value": value[:1024], "inline": False}
        for name, value in sections.items()
    ]
    return {
        "title": f"🔮 {title}",
        "color": color,
        "fields": fields,
        "footer": {"text": "Phantom Command Center"},
        "timestamp": datetime.utcnow().isoformat()
    }


def build_surprise_embed(
    name: str,
    description: str,
    why: str,
    path: str,
    color: int = 0x00D4AA
) -> dict:
    """Build an overnight surprise announcement embed."""
    return {
        "title": f"✨ Tonight I Built: {name}",
        "description": description,
        "color": color,
        "fields": [
            {"name": "Why I Built This", "value": why, "inline": False},
            {"name": "Location", "value": f"`{path}`", "inline": False},
        ],
        "footer": {"text": "Phantom — Overnight Build Engine"},
        "timestamp": datetime.utcnow().isoformat()
    }


def build_research_embed(
    topic: str,
    summary: str,
    sources: list = None,
    urgent: bool = False,
    color: int = 0x4A90E2
) -> dict:
    """Build a research findings embed."""
    fields = [{"name": "Summary", "value": summary[:1024], "inline": False}]
    if sources:
        source_text = "\n".join(f"• {s}" for s in sources[:5])
        fields.append({"name": "Sources", "value": source_text[:1024], "inline": False})

    alert_prefix = "🚨 URGENT: " if urgent else "🔬 "
    embed_color = 0xFF4444 if urgent else color

    return {
        "title": f"{alert_prefix}Research: {topic}",
        "color": embed_color,
        "fields": fields,
        "footer": {"text": "Phantom — Research Agent"},
        "timestamp": datetime.utcnow().isoformat()
    }


def build_status_embed(services: dict) -> dict:
    """Build a system status embed."""
    fields = []
    for service, status in services.items():
        icon = "🟢" if status.get("online") else "🔴"
        detail = status.get("detail", "")
        fields.append({
            "name": f"{icon} {service}",
            "value": detail or ("Online" if status.get("online") else "Offline"),
            "inline": True
        })

    return {
        "title": "🔮 Phantom System Status",
        "color": 0x7B2FBE,
        "fields": fields,
        "footer": {"text": "Phantom Command Center"},
        "timestamp": datetime.utcnow().isoformat()
    }
