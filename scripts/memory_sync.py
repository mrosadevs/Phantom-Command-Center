"""
memory_sync.py — Cron script: runs at 10 PM daily.

Consolidates memory files and ensures everything is clean and consistent.
Trims old entries if files grow too large.
"""

import asyncio
import logging
import sys
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("phantom.memory_sync")

MEMORY_DIR = ROOT / "memory"
MAX_LOG_ENTRIES = 50  # Keep last 50 entries in log files


async def trim_log(filename: str):
    """Trim a log file to the last MAX_LOG_ENTRIES entries."""
    path = MEMORY_DIR / filename
    if not path.exists():
        return

    content = path.read_text(encoding="utf-8")
    sections = content.split("\n## ")
    header = sections[0]
    entries = sections[1:]

    if len(entries) > MAX_LOG_ENTRIES:
        logger.info(f"Trimming {filename}: {len(entries)} -> {MAX_LOG_ENTRIES} entries")
        trimmed = entries[-MAX_LOG_ENTRIES:]
        path.write_text(header + "\n## " + "\n## ".join(trimmed), encoding="utf-8")


async def main():
    logger.info("Starting memory sync...")

    # Trim large log files
    for logfile in ["research-log.md", "surprises-log.md"]:
        await trim_log(logfile)

    # Ensure all memory files exist with headers
    defaults = {
        "about-manuel.md": "# About Manuel\n\n",
        "projects.md": "# Active Projects\n\n",
        "skills-learned.md": "# Skills Learned\n\n",
        "mcps-installed.md": "# MCPs Installed\n\n",
        "research-log.md": "# Research Log\n\n",
        "surprises-log.md": "# Overnight Surprises Log\n\n",
    }

    for filename, default_content in defaults.items():
        path = MEMORY_DIR / filename
        if not path.exists():
            path.write_text(default_content, encoding="utf-8")
            logger.info(f"Created missing memory file: {filename}")

    logger.info(f"Memory sync complete at {datetime.now().strftime('%Y-%m-%d %H:%M')}")


if __name__ == "__main__":
    asyncio.run(main())
