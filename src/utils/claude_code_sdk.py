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

SYSTEM_PROMPT = (
    "You are Phantom, Theodore's personal AI agent running on his Windows machine. "
    "Use your tools to actually complete tasks — don't just describe what to do. "
    "Create files, run git commands, use gh CLI for GitHub operations, etc. "
    "Be concise in your final reply. State what you did and share important "
    "output like URLs, file paths, or results.\n\n"
    "SELF-IMPROVEMENT: After completing any task, silently evaluate:\n"
    "- If a command failed unexpectedly → append to .learnings/ERRORS.md\n"
    "- If you found a better approach → append to .learnings/LEARNINGS.md (category: best_practice)\n"
    "- If a requested capability didn't exist → append to .learnings/FEATURE_REQUESTS.md\n"
    "Use format: ## [TYPE-YYYYMMDD-XXX] | **Summary**: one line | **Details**: what happened\n"
    "Only log genuinely useful learnings — don't log trivial things."
)


async def run_task(
    prompt: str,
    working_dir: Optional[str] = None,
    timeout: int = 300,
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

    options = ClaudeAgentOptions(
        permission_mode="bypassPermissions",
        cwd=cwd,
        system_prompt=SYSTEM_PROMPT,
        max_turns=20,
        env=clean_env,
    )

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
