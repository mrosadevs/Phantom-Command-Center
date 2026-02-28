"""
gemini_client.py — Google Gemini integration via Gemini CLI.

Uses your Gemini Pro subscription (no API key needed).
Gemini CLI has Google Search grounding built-in — great for deep research.

Install CLI: npm install -g @google/generative-ai-cli
Auth:        gemini auth login
"""

import asyncio
import logging
import os
import sys
from pathlib import Path

from src.core.config import ROOT_DIR

# On Windows, npm .cmd wrappers must be called with the .cmd suffix from Python subprocess
GEMINI_CMD = "gemini.cmd" if sys.platform == "win32" else "gemini"

logger = logging.getLogger(__name__)

# Where Gemini-assisted projects get scaffolded
CODEX_WORK_DIR = Path("C:/Users/viole/OneDrive/Documents/CodexCoWork")

RESEARCH_PROMPT = """Search Google for "{topic}" and write a research brief right now. Do not ask for clarification — just search and write.

Format your response exactly like this:

## What's New
2-3 bullet points on the biggest recent developments. Be specific — names, dates, numbers.

## Key Findings
4-5 concrete takeaways from what you found. Include data/numbers where available.

## Community Pulse
What's the current mood, debate, or consensus around this topic?

## Worth Acting On
2-3 specific, actionable recommendations based on what you found.

## Sources
List 4-6 relevant URLs from your search results.

Topic: {topic}

Search now and write the brief directly. No preamble. No asking for clarification."""


async def research(topic: str, timeout: int = 240) -> str:
    """
    Run a deep research query via Gemini CLI with Google Search grounding.
    Falls back to a plain message if CLI isn't available or auth fails.
    """
    prompt = RESEARCH_PROMPT.format(topic=topic)

    try:
        clean_env = {k: v for k, v in os.environ.items() if k not in ("CLAUDECODE",)}

        proc = await asyncio.create_subprocess_exec(
            GEMINI_CMD, "--prompt", prompt, "--output-format", "text",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=clean_env,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)

        if proc.returncode == 0:
            output = stdout.decode("utf-8", errors="replace").strip()
            if output:
                logger.info(f"Gemini research complete: {topic}")
                return output

        err = stderr.decode("utf-8", errors="replace").strip()
        logger.warning(f"Gemini CLI failed (exit {proc.returncode}): {err[:200]}")
        return f"[Gemini CLI error — check `gemini auth login`: {err[:200]}]"

    except FileNotFoundError:
        return "[Gemini CLI not found — run: npm install -g @google/generative-ai-cli]"
    except asyncio.TimeoutError:
        return f"[Gemini timed out after {timeout}s]"
    except Exception as e:
        logger.error(f"Gemini research error: {e}")
        return f"[Gemini error: {e}]"


async def chat(prompt: str, system: str = "", timeout: int = 60) -> str:
    """
    Send a one-shot chat message via Gemini CLI.
    """
    full_prompt = f"{system}\n\n{prompt}".strip() if system else prompt

    try:
        clean_env = {k: v for k, v in os.environ.items() if k not in ("CLAUDECODE",)}

        proc = await asyncio.create_subprocess_exec(
            GEMINI_CMD, "--prompt", full_prompt, "--output-format", "text",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=clean_env,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)

        if proc.returncode == 0:
            return stdout.decode("utf-8", errors="replace").strip()

        return f"[Gemini error: {stderr.decode('utf-8', errors='replace')[:200]}]"

    except FileNotFoundError:
        return "[Gemini CLI not found]"
    except asyncio.TimeoutError:
        return "[Gemini timed out]"
    except Exception as e:
        return f"[Gemini error: {e}]"


async def scaffold_project(description: str, project_name: str = None) -> str:
    """
    Create a project scaffold in CodexCoWork for use with VS Code + Codex.
    Gemini generates the file structure + starter files, you build it out with Codex.
    """
    import re

    def slugify(text: str) -> str:
        text = text.lower()
        text = re.sub(r'[^a-z0-9]+', '-', text)
        return text.strip('-')[:40]

    safe_name = slugify(project_name or description[:30])
    project_dir = CODEX_WORK_DIR / safe_name
    project_dir.mkdir(parents=True, exist_ok=True)

    prompt = (
        f"Generate a project scaffold for: {description}\n\n"
        f"Output the files immediately using this exact format for each file:\n"
        f"=== FILE: path/to/file.ext ===\n[file contents here]\n\n"
        f"Include these files: README.md, main entry file, config/package files, .gitignore.\n"
        f"Keep code minimal but working — this is a starter scaffold.\n"
        f"Do not ask questions. Output the files now."
    )

    output = await chat(prompt, timeout=90)

    # Parse and write files
    file_pattern = __import__('re').compile(r'=== FILE: (.+?) ===\n(.*?)(?==== FILE:|$)', __import__('re').DOTALL)
    files_written = []

    for match in file_pattern.finditer(output):
        fname = match.group(1).strip()
        content = match.group(2).strip()
        fpath = project_dir / fname
        fpath.parent.mkdir(parents=True, exist_ok=True)
        fpath.write_text(content, encoding="utf-8")
        files_written.append(fname)

    if not files_written:
        # Save raw output as README scaffold
        (project_dir / "SCAFFOLD.md").write_text(output, encoding="utf-8")
        files_written = ["SCAFFOLD.md"]

    return (
        f"**Scaffold ready in CodexCoWork!**\n"
        f"Path: `{project_dir}`\n"
        f"Files: {', '.join(files_written)}\n\n"
        f"Open it in VS Code and let Codex fill it in."
    )
