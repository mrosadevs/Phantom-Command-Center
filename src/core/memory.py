"""
memory.py — Memory manager for Phantom Command Center.

Reads and writes the memory files in phantom/memory/.
Memory files are plain Markdown so Claude Code can read/edit them directly.

Key files:
  - about-manuel.md   : Who Theodore is, interests, preferences
  - projects.md       : Active projects and repos
  - skills-learned.md : Installed skills registry
  - mcps-installed.md : Installed MCP servers registry
  - research-log.md   : Past research topics and summaries
  - surprises-log.md  : Log of proactively built tools/apps
"""

import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

from src.core.config import MEMORY_DIR

logger = logging.getLogger(__name__)


def read_memory(filename: str) -> str:
    """Read a memory file and return its contents as a string."""
    path = MEMORY_DIR / filename
    if not path.exists():
        logger.warning(f"Memory file not found: {filename}")
        return ""
    return path.read_text(encoding="utf-8")


def write_memory(filename: str, content: str):
    """Overwrite a memory file with new content."""
    path = MEMORY_DIR / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    logger.info(f"Memory written: {filename}")


def append_memory(filename: str, content: str):
    """Append content to a memory file (adds newline separator)."""
    path = MEMORY_DIR / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write("\n" + content)
    logger.info(f"Memory appended: {filename}")


def add_fact(fact: str):
    """Add a quick fact to about-manuel.md."""
    timestamp = datetime.now().strftime("%Y-%m-%d")
    append_memory("about-manuel.md", f"\n- [{timestamp}] {fact}")
    logger.info(f"Fact added to about-manuel: {fact[:60]}")


def remove_fact(keyword: str) -> bool:
    """
    Remove any line from about-manuel.md containing the keyword.
    Returns True if at least one line was removed.
    """
    content = read_memory("about-manuel.md")
    lines = content.splitlines()
    new_lines = [l for l in lines if keyword.lower() not in l.lower()]
    if len(new_lines) < len(lines):
        write_memory("about-manuel.md", "\n".join(new_lines))
        logger.info(f"Removed fact containing: {keyword}")
        return True
    return False


def log_research(topic: str, summary: str, full_report_path: Optional[str] = None):
    """Add an entry to research-log.md."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    entry = f"\n## [{timestamp}] {topic}\n{summary}"
    if full_report_path:
        entry += f"\n*Full report: {full_report_path}*"
    append_memory("research-log.md", entry)


def log_surprise(name: str, description: str, path: str):
    """Add an entry to surprises-log.md."""
    timestamp = datetime.now().strftime("%Y-%m-%d")
    entry = f"\n## [{timestamp}] {name}\n**What**: {description}\n**Path**: {path}"
    append_memory("surprises-log.md", entry)


def register_skill(name: str, url: str, capabilities: str):
    """Register a newly installed skill in skills-learned.md."""
    timestamp = datetime.now().strftime("%Y-%m-%d")
    entry = f"\n## {name}\n- Installed: {timestamp}\n- Source: {url}\n- Capabilities: {capabilities}"
    append_memory("skills-learned.md", entry)


def register_mcp(name: str, package: str, description: str):
    """Register a newly installed MCP server in mcps-installed.md."""
    timestamp = datetime.now().strftime("%Y-%m-%d")
    entry = f"\n## {name}\n- Package: {package}\n- Installed: {timestamp}\n- Description: {description}"
    append_memory("mcps-installed.md", entry)


def get_full_context() -> str:
    """
    Return a combined context string from all memory files.
    Used to give agents full awareness of who Theodore is.
    """
    files = [
        "about-manuel.md",
        "projects.md",
        "skills-learned.md",
        "mcps-installed.md",
        "research-log.md",
    ]
    sections = []
    for f in files:
        content = read_memory(f)
        if content.strip():
            sections.append(f"### {f}\n{content}")
    return "\n\n".join(sections)
