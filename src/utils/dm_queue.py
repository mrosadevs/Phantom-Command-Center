"""
dm_queue.py — File-based DM queue for cron scripts.

Cron scripts run as subprocesses (no Discord connection).
They enqueue messages here. The bot's heartbeat loop drains the queue
and sends them as DMs to Offline.
"""

import json
import logging
from datetime import datetime
from pathlib import Path

from src.core.config import ROOT_DIR

logger = logging.getLogger(__name__)

_QUEUE_FILE = ROOT_DIR / "memory" / "pending-dms.json"


def enqueue_dm(content: str, title: str = "", priority: int = 0):
    """
    Add a message to the pending DM queue.
    Called by cron scripts that don't have Discord access.

    Args:
        content:  The text to DM (Discord markdown supported, max 1900 chars per chunk)
        title:    Optional label shown in logs
        priority: Higher = sent first (not yet used, reserved)
    """
    queue = _read_queue()
    queue.append({
        "content": content,
        "title": title,
        "queued_at": datetime.now().isoformat(),
        "priority": priority,
    })
    _write_queue(queue)
    logger.info(f"DM queued: {title or content[:40]}")


def drain_queue() -> list:
    """
    Remove and return all pending DMs.
    Called by the heartbeat loop — each item should be sent to Offline.
    Returns list of dicts with 'content' and 'title'.
    """
    queue = _read_queue()
    if not queue:
        return []
    _write_queue([])
    logger.info(f"DM queue drained: {len(queue)} message(s)")
    return sorted(queue, key=lambda x: -x.get("priority", 0))


def _read_queue() -> list:
    try:
        if _QUEUE_FILE.exists():
            return json.loads(_QUEUE_FILE.read_text(encoding="utf-8"))
    except Exception as e:
        logger.warning(f"Could not read DM queue: {e}")
    return []


def _write_queue(queue: list):
    _QUEUE_FILE.parent.mkdir(parents=True, exist_ok=True)
    _QUEUE_FILE.write_text(json.dumps(queue, indent=2), encoding="utf-8")
