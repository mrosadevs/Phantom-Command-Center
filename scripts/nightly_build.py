"""
nightly_build.py — Cron script: runs at 2 AM daily.

Triggers the builder agent to proactively create a tool or improvement for Manuel.
"""

import asyncio
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("phantom.nightly_build")


async def main():
    from src.agents.builder import run_nightly_build
    logger.info("Starting nightly build agent...")
    await run_nightly_build()
    logger.info("Nightly build complete.")


if __name__ == "__main__":
    asyncio.run(main())
