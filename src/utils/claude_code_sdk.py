"""
claude_code_sdk.py — Agentic Claude via the claude-agent-sdk.

Uses your existing Claude Code CLI authentication (Max subscription).
No API key required. Claude can execute bash commands, create files,
run git, use gh CLI — anything on your machine.

Requires: pip install claude-agent-sdk
"""

import asyncio
import logging
import os
from pathlib import Path
from typing import Optional

from src.core.config import ROOT_DIR

logger = logging.getLogger(__name__)

def _build_system_prompt() -> str:
    """Load soul.md for personality, merge with execution rules."""
    try:
        soul_path = ROOT_DIR / "memory" / "soul.md"
        soul = soul_path.read_text(encoding="utf-8").strip()[:1800] if soul_path.exists() else ""
    except Exception:
        soul = ""

    soul_block = soul or "You are Theodore, Offline's personal AI. Be direct, sharp, and genuinely helpful. Call yourself Theodore."

    return (
        f"{soul_block}\n\n"
        "---\n"
        "EXECUTION RULES (these override everything — you are in agentic mode):\n"
        "- Use your tools to ACTUALLY complete tasks. Don't describe — execute.\n"
        "- Create files, run bash, use git, use gh CLI for GitHub. Do the work.\n"
        "- If working in a repo: cd into it, make changes, git add, commit, push.\n"
        "- Final reply: what you did, any URLs/paths/results. Be concise.\n\n"
        "SELF-IMPROVEMENT (silent log after each task):\n"
        "- Unexpected failure → .learnings/ERRORS.md\n"
        "- Better approach found → .learnings/LEARNINGS.md\n"
        "- Missing capability → .learnings/FEATURE_REQUESTS.md\n"
        "Format: ## [TYPE-YYYYMMDD] | **Summary**: one line | **Details**: what happened\n"
        "Only log genuinely useful learnings."
    )


SYSTEM_PROMPT = _build_system_prompt()


async def run_task(
    prompt: str,
    working_dir: Optional[str] = None,
    timeout: int = 300,
    model: Optional[str] = None,
) -> str:
    """
    Run an agentic task via Claude Code (uses Max subscription auth).
    Claude can call Bash, create/edit files, run git, etc.
    Returns Claude's final text response.
    """
    try:
        from claude_agent_sdk import query, ClaudeAgentOptions
        from claude_agent_sdk.types import ResultMessage, AssistantMessage, TextBlock
    except ImportError:
        return "[claude-agent-sdk not installed. Run: pip install claude-agent-sdk]"

    cwd = working_dir or str(ROOT_DIR)

    # Strip CLAUDECODE env var so the SDK can launch even if called from
    # inside a Claude Code session (e.g. during dev/testing)
    clean_env = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}

    options_kwargs = dict(
        permission_mode="bypassPermissions",
        cwd=cwd,
        system_prompt=SYSTEM_PROMPT,
        max_turns=20,
        env=clean_env,
    )
    if model:
        options_kwargs["model"] = model

    options = ClaudeAgentOptions(**options_kwargs)

    try:
        async with asyncio.timeout(timeout):
            async for message in query(prompt=prompt, options=options):
                # ResultMessage is the final summary — grab it and return
                if isinstance(message, ResultMessage):
                    if message.is_error:
                        return f"[Claude error: {message.result}]"
                    return (message.result or "").strip() or "(task completed)"

    except asyncio.TimeoutError:
        return f"[Claude timed out after {timeout}s]"
    except Exception as e:
        logger.error(f"Claude agent error: {e}")
        return f"[Claude error: {e}]"

    return "(task completed)"


async def build_project(
    description: str,
    output_dir: str,
    timeout: int = 1800,
) -> str:
    """Ask Claude to build a project in output_dir using real bash/file operations."""
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    prompt = (
        f"Build the following project inside the directory: {output_dir}\n\n"
        f"{description}\n\n"
        "Create all directories and files with complete, working implementations. No stubs."
    )
    return await run_task(prompt, working_dir=output_dir, timeout=timeout)


async def improve_repo(
    repo_path: str,
    improvement: str,
    timeout: int = 600,
) -> str:
    """Ask Claude to implement an improvement in an existing local repo."""
    prompt = (
        f"Implement this improvement in the repo at {repo_path}:\n\n"
        f"{improvement}\n\n"
        "Read existing files, make targeted changes, and verify the result."
    )
    return await run_task(prompt, working_dir=repo_path, timeout=timeout)
