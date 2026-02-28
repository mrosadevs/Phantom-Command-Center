"""
nightly_research.py — Cron script: runs at 11 PM daily.

Triggers the researcher agent to investigate topics relevant to Manuel.
"""

import asyncio
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("phantom.nightly_research")


async def main():
    from src.agents.researcher import run_nightly_research
    logger.info("Starting nightly research...")
    await run_nightly_research()
    logger.info("Nightly research complete.")


if __name__ == "__main__":
    asyncio.run(main())
