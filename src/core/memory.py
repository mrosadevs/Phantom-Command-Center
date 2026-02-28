"""
memory.py — Memory manager for Phantom Command Center.

Reads and writes the memory files in phantom/memory/.
Memory files are plain Markdown so Claude Code can read/edit them directly.

Key files:
  - about-manuel.md       : Who Theodore is, interests, preferences
  - projects.md           : Active projects and repos
  - skills-learned.md     : Installed skills registry
  - mcps-installed.md     : Installed MCP servers registry
  - research-log.md       : Past research topics and summaries
  - surprises-log.md      : Log of proactively built tools/apps
  - working-context.json  : Current repo/project being worked on (persistent)

Conversation history is stored in-memory (per Discord channel, clears on restart).
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict

from src.core.config import MEMORY_DIR

logger = logging.getLogger(__name__)

# ── In-memory conversation history (per Discord channel_id) ──────────────────
# Cleared on bot restart — intentional (fresh sessions, no stale context)
_conversation_history: Dict[int, List[Dict]] = {}
MAX_HISTORY_TURNS = 20   # keep last 20 messages (10 exchanges)


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


def get_soul() -> str:
    """Return Phantom's soul/personality file content."""
    return read_memory("soul.md")


def get_full_context() -> str:
    """
    Return a combined context string from all memory files.
    Used to give agents full awareness of who Theodore is.
    Soul is intentionally excluded here — it's loaded separately
    so it can be placed first in every system prompt.
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


def append_evolved_trait(trait: str):
    """Add a new evolved trait to the soul file's Evolved Traits section."""
    ts = datetime.now().strftime("%Y-%m-%d")
    entry = f"\n- [{ts}] {trait}"
    soul_path = MEMORY_DIR / "soul.md"
    if soul_path.exists():
        content = soul_path.read_text(encoding="utf-8")
        if "## Evolved Traits" in content:
            soul_path.write_text(content + entry, encoding="utf-8")
            logger.info(f"Evolved trait added: {trait}")


def append_backlog(title: str, why: str, effort: str = "M"):
    """Add an item to Phantom's proactive backlog."""
    ts = datetime.now().strftime("%Y-%m-%d")
    entry = f"\n## [BACKLOG-{ts}] {title} | **Why**: {why} | **Effort**: {effort} | **Status**: Queued"
    append_memory("backlog.md", entry)
    logger.info(f"Backlog item added: {title}")


# ── Conversation History ───────────────────────────────────────────────────────

def add_conversation_turn(channel_id: int, role: str, content: str):
    """
    Add a message turn to in-memory conversation history for a channel.
    role: "user" or "assistant"
    """
    if channel_id not in _conversation_history:
        _conversation_history[channel_id] = []
    _conversation_history[channel_id].append({
        "role": role,
        "content": content[:1500],   # cap per-turn to avoid bloat
        "ts": datetime.now().isoformat(),
    })
    # Trim to window
    if len(_conversation_history[channel_id]) > MAX_HISTORY_TURNS:
        _conversation_history[channel_id] = _conversation_history[channel_id][-MAX_HISTORY_TURNS:]


def get_conversation_history(channel_id: int, last_n: int = 12) -> List[Dict]:
    """Return the last N turns for a channel."""
    return _conversation_history.get(channel_id, [])[-last_n:]


def format_conversation_history(channel_id: int, last_n: int = 10) -> str:
    """
    Format recent conversation as a readable block for model system prompts.
    Returns empty string if no history yet.
    """
    turns = get_conversation_history(channel_id, last_n)
    if not turns:
        return ""
    lines = []
    for t in turns:
        label = "Offline" if t["role"] == "user" else "Theodore"
        # Truncate very long turns so it stays compact in the prompt
        text = t["content"][:600].replace("\n", " ")
        lines.append(f"{label}: {text}")
    return "\n".join(lines)


# ── Working Context (persistent JSON) ─────────────────────────────────────────

_WC_FILE = MEMORY_DIR / "working-context.json"


def set_working_context(path: str, name: str, kind: str = "project", github_url: str = ""):
    """
    Save the current working context (the repo/project Theodore wants to focus on).
    Persists across bot restarts.
    """
    ctx = {
        "path": path,
        "name": name,
        "kind": kind,
        "github_url": github_url,
        "set_at": datetime.now().isoformat(),
    }
    _WC_FILE.parent.mkdir(parents=True, exist_ok=True)
    _WC_FILE.write_text(json.dumps(ctx, indent=2), encoding="utf-8")
    logger.info(f"Working context set: {name} at {path}")


def get_working_context() -> dict:
    """Return current working context dict, or empty dict if none set."""
    try:
        if _WC_FILE.exists():
            return json.loads(_WC_FILE.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}


def clear_working_context():
    """Clear the current working context."""
    if _WC_FILE.exists():
        _WC_FILE.unlink()
    logger.info("Working context cleared")


def format_working_context() -> str:
    """Return a one-line summary of the current working context for prompts."""
    ctx = get_working_context()
    if not ctx:
        return "No specific repo/project focused. Work in ClaudeCoWork by default."
    parts = [f"Focused repo/project: {ctx['name']}"]
    if ctx.get("path"):
        parts.append(f"Local path: {ctx['path']}")
    if ctx.get("github_url"):
        parts.append(f"GitHub: {ctx['github_url']}")
    return " | ".join(parts)
