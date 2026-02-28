"""
morning_briefing.py — Cron script: runs at 6 AM daily.

Generates a morning briefing and posts it to Discord #morning-briefing.
"""

import asyncio
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("phantom.morning_briefing")


async def main():
    from src.agents.orchestrator import morning_briefing
    from src.interfaces.webhook_sender import build_briefing_embed

    logger.info("Generating morning briefing...")
    briefing_text = await morning_briefing()

    # Try to post to Discord
    import os
    webhook_url = os.getenv("PHANTOM_BRIEFING_WEBHOOK", "")

    if webhook_url:
        from src.interfaces.webhook_sender import send_webhook
        from datetime import datetime
        embed = build_briefing_embed(
            title=f"Good Morning — {datetime.now().strftime('%A, %B %d')}",
            sections={"Briefing": briefing_text[:1024]}
        )
        await send_webhook(webhook_url, embed)
        logger.info("Morning briefing sent to Discord")
    else:
        logger.info("Morning briefing (no webhook configured):")
        logger.info(briefing_text)


if __name__ == "__main__":
    asyncio.run(main())
