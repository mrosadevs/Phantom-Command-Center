"""
evening_debrief.py — Cron wrapper: runs at 10 PM EST daily.
Also runs at 2:20 AM as a test (first few days).

Calls the evening_debrief agent which queues the DM via dm_queue.
The heartbeat loop drains the queue and DMs Offline within ~2 minutes.
"""

import asyncio
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("phantom.script.evening_debrief")


async def main():
    from src.agents.evening_debrief import run_evening_debrief
    logger.info("Evening debrief script starting...")
    await run_evening_debrief()
    logger.info("Evening debrief queued for delivery.")


if __name__ == "__main__":
    asyncio.run(main())
