"""
builder.py — Proactive App Builder for Phantom Command Center (The Surprise Engine).

Every night at 2 AM:
  1. Reads Theodore's memory and project context
  2. Asks LM Studio to propose ONE buildable tool/app/automation
  3. Evaluates the proposal for usefulness and feasibility
  4. Delegates to Claude Code to actually build it
  5. Posts the result to Discord #overnight-surprises
  6. Logs it in memory/surprises-log.md

Also handles on-demand builds: "build me [description]"
"""

import logging
import re
import subprocess
from datetime import datetime
from pathlib import Path

from src.core import memory
from src.core.config import ROOT_DIR
from src.utils import lm_studio_client, claude_code_sdk
from src.utils.github_client import scan_watched_repos

logger = logging.getLogger(__name__)

# All Claude-built projects go here — on-demand and overnight surprises
CLAUDE_WORK_DIR = Path("C:/Users/viole/OneDrive/Documents/ClaudeCoWork")
SURPRISES_DIR   = CLAUDE_WORK_DIR / "surprises"
PENDING_PRS_FILE = ROOT_DIR / "memory" / "pending-prs.md"


async def run_nightly_build():
    """Main entry point for the overnight build agent (runs at 2 AM)."""
    logger.info("Starting nightly build agent...")

    context = memory.get_full_context()

    # Step 1: Get repo scan for improvement ideas
    repo_data = []
    try:
        repo_data = await scan_watched_repos()
    except Exception as e:
        logger.warning(f"Could not scan repos: {e}")

    repo_summary = ""
    for repo in repo_data:
        repo_summary += (
            f"- {repo['repo']}: {repo['description']} "
            f"({repo['language']}, {repo['recent_commits']} recent commits, "
            f"{repo['open_issues']} open issues)\n"
        )

    # Step 2: Ask LM Studio to propose something to build
    proposal_prompt = (
        f"You are Phantom, Theodore's AI agent. Based on everything you know about him, "
        f"propose ONE specific, buildable tool, app, or improvement that would make his life easier.\n\n"
        f"--- Theodore's Context ---\n{context[:1500]}\n\n"
        f"--- His Repos ---\n{repo_summary}\n\n"
        f"Rules:\n"
        f"- It must be completable in one coding session (not a massive project)\n"
        f"- It must be genuinely useful based on his actual situation\n"
        f"- It should NOT duplicate something that clearly already exists\n"
        f"- If improving an existing repo, set target_repo to 'owner/repo-name' exactly as shown above\n"
        f"- If building something brand new (no target repo), set target_repo to null\n\n"
        f"Output JSON:\n"
        f'{{"name": "Tool Name", "description": "What it does", "why": "Why Theodore needs this", '
        f'"build_instructions": "Detailed instructions", "type": "webapp|script|cli|api|improvement", '
        f'"target_repo": "owner/repo-name or null"}}'
    )

    proposal_json = await lm_studio_client.chat(
        proposal_prompt,
        system="You are Phantom, a proactive AI agent. Propose practical tools.",
        max_tokens=800
    )

    proposal = _parse_proposal(proposal_json)
    if not proposal:
        logger.warning("No valid proposal generated tonight")
        return

    logger.info(f"Tonight's proposal: {proposal.get('name')}")

    # Step 3: Evaluate the proposal
    approved = await _evaluate_proposal(proposal)
    if not approved:
        logger.info("Proposal rejected — skipping build tonight")
        return

    # Step 4: Build it
    result = await _build_surprise(proposal)

    # Step 5: Notify Discord
    await _announce_surprise(proposal, result)

    logger.info(f"Nightly build complete: {proposal.get('name')}")


async def build_on_demand(description: str) -> str:
    """
    Build something on Theodore's direct request.
    Used when he says "build me [description]" in Discord.
    Output goes to ClaudeCoWork/{project-name}/.
    """
    logger.info(f"On-demand build: {description}")

    safe_name = _slugify(description[:30])
    output_dir = CLAUDE_WORK_DIR / safe_name
    output_dir.mkdir(parents=True, exist_ok=True)

    await _send_discord_message(f"Building **{description}**... I'll let you know when it's done!")

    try:
        result = await claude_code_sdk.build_project(description, str(output_dir))
        memory.log_surprise(description, description, str(output_dir))

        return (
            f"**Build complete!** `{description}`\n"
            f"Output: `{output_dir}`\n\n"
            f"Claude's notes:\n```\n{result[:600]}\n```"
        )
    except Exception as e:
        logger.error(f"On-demand build failed: {e}")
        return f"Build failed: `{e}`"


async def _build_surprise(proposal: dict) -> str:
    """Build the proposed tool or repo improvement using Claude Code."""
    target_repo = proposal.get("target_repo")

    # Route: repo improvement → branch flow, new tool → surprises dir
    if target_repo and target_repo != "null" and "/" in target_repo:
        return await _build_repo_improvement(proposal, target_repo)

    # New standalone tool
    name         = proposal.get("name", "unnamed-tool")
    instructions = proposal.get("build_instructions", proposal.get("description", ""))
    timestamp    = datetime.now().strftime("%Y-%m-%d")
    safe_name    = _slugify(name)
    output_dir   = SURPRISES_DIR / f"{timestamp}-{safe_name}"
    output_dir.mkdir(parents=True, exist_ok=True)

    full_instructions = (
        f"Build: {name}\n\n"
        f"Description: {proposal.get('description', '')}\n\n"
        f"Build Instructions: {instructions}\n\n"
        f"Create a complete, working implementation. Include a README.md explaining what was built."
    )

    logger.info(f"Building surprise: {name} in {output_dir}")
    result = await claude_code_sdk.build_project(full_instructions, str(output_dir))

    memory.log_surprise(
        name=name,
        description=proposal.get("description", ""),
        path=str(output_dir.relative_to(ROOT_DIR))
    )
    return result


async def _build_repo_improvement(proposal: dict, target_repo: str) -> str:
    """
    Build an improvement to an existing repo on a new branch.
    Pushes phantom/YYYY-MM-DD-slug to origin and logs to pending-prs.md.
    """
    repo_name  = target_repo.split("/")[-1]
    repo_path  = CLAUDE_WORK_DIR / repo_name
    name       = proposal.get("name", "improvement")
    description = proposal.get("description", "")
    instructions = proposal.get("build_instructions", description)

    if not repo_path.exists():
        logger.warning(f"Repo not found locally: {repo_path}")
        return f"[Repo {repo_name} not found at {repo_path}]"

    timestamp  = datetime.now().strftime("%Y-%m-%d")
    branch     = f"phantom/{timestamp}-{_slugify(name)}"

    # Create the branch
    try:
        subprocess.run(
            ["git", "-C", str(repo_path), "checkout", "-b", branch],
            check=True, capture_output=True, text=True
        )
        logger.info(f"Created branch: {branch} in {repo_name}")
    except subprocess.CalledProcessError as e:
        logger.error(f"Branch creation failed: {e.stderr}")
        return f"[Git branch failed: {e.stderr}]"

    # Ask Claude to make the changes (no commit/push — we handle that)
    build_prompt = (
        f"Implement this improvement to the repo at {repo_path}:\n\n"
        f"Improvement: {name}\n"
        f"Description: {description}\n\n"
        f"Instructions: {instructions}\n\n"
        f"IMPORTANT: Make only the file changes needed. "
        f"Do NOT run git commit or git push — the build system handles that."
    )

    logger.info(f"Building repo improvement: {name} in {repo_path}")
    result = await claude_code_sdk.run_task(build_prompt, working_dir=str(repo_path), timeout=600)

    # Commit and push the branch
    try:
        subprocess.run(["git", "-C", str(repo_path), "add", "-A"], check=True, capture_output=True)
        subprocess.run(
            ["git", "-C", str(repo_path), "commit", "-m", f"phantom: {name}\n\n{description[:200]}"],
            check=True, capture_output=True, text=True
        )
        subprocess.run(
            ["git", "-C", str(repo_path), "push", "origin", branch],
            check=True, capture_output=True, text=True
        )
        logger.info(f"Pushed branch {branch} to {target_repo}")
    except subprocess.CalledProcessError as e:
        logger.error(f"Git push failed: {e.stderr}")
        # Return to main/master so next run isn't stuck on the branch
        subprocess.run(["git", "-C", str(repo_path), "checkout", "master"],
                       capture_output=True)
        subprocess.run(["git", "-C", str(repo_path), "checkout", "main"],
                       capture_output=True)
        return f"[Built but push failed: {e.stderr[:200]}]"

    # Return to default branch
    for default in ["main", "master"]:
        res = subprocess.run(["git", "-C", str(repo_path), "checkout", default],
                             capture_output=True)
        if res.returncode == 0:
            break

    # Log to pending-prs.md so morning debrief picks it up
    _log_pending_pr(
        repo=target_repo,
        branch=branch,
        name=name,
        description=description,
        why=proposal.get("why", "")
    )

    memory.log_surprise(
        name=name,
        description=f"[Repo improvement] {target_repo} → branch `{branch}`",
        path=f"{repo_name}/{branch}"
    )

    return result


def _log_pending_pr(repo: str, branch: str, name: str, description: str, why: str):
    """Append a pending branch to memory/pending-prs.md for the morning debrief."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    entry = (
        f"\n## [{timestamp}] {name}\n"
        f"- **Repo:** `{repo}`\n"
        f"- **Branch:** `{branch}`\n"
        f"- **What:** {description}\n"
        f"- **Why:** {why}\n"
        f"- **Status:** Pending review\n"
    )
    PENDING_PRS_FILE.parent.mkdir(parents=True, exist_ok=True)
    if not PENDING_PRS_FILE.exists():
        PENDING_PRS_FILE.write_text("# Pending Phantom Branches\n", encoding="utf-8")
    with open(PENDING_PRS_FILE, "a", encoding="utf-8") as f:
        f.write(entry)
    logger.info(f"Logged pending PR: {branch}")


async def _evaluate_proposal(proposal: dict) -> bool:
    """
    Evaluate if a proposal is worth building.
    Returns True if it should be built.
    """
    name = proposal.get("name", "")
    description = proposal.get("description", "")

    # Check if something similar already exists in surprises/
    if SURPRISES_DIR.exists():
        for existing in SURPRISES_DIR.iterdir():
            if existing.is_dir() and _slugify(name) in existing.name.lower():
                logger.info(f"Similar surprise already exists: {existing.name}")
                return False

    # Quick sanity check: reject if instructions are too vague
    if len(description) < 20:
        logger.info("Proposal too vague — skipping")
        return False

    return True


async def _announce_surprise(proposal: dict, build_result: str):
    """Deposit build announcement into DM queue — bot drains it every 2 min."""
    try:
        from src.utils.dm_queue import enqueue_dm

        name        = proposal.get("name", "Mystery Tool")
        description = proposal.get("description", "")
        why         = proposal.get("why", "")
        result_snippet = build_result[:300] if build_result else ""

        msg = (
            f"**Built while you slept: {name}**\n\n"
            f"{description}\n\n"
            f"**Why:** {why}"
        )
        if result_snippet:
            msg += f"\n\n```\n{result_snippet}\n```"

        enqueue_dm(msg, title=name, priority=1)
        logger.info(f"Surprise announcement queued: {name}")
    except Exception as e:
        logger.error(f"Failed to queue surprise announcement: {e}")


async def _send_discord_message(text: str):
    """Attempt to send a message via Discord bot if running."""
    try:
        # Try to import and use the running bot
        from src.interfaces.discord_bot import send_to_channel, CHANNEL_COMMANDS
        await send_to_channel(CHANNEL_COMMANDS, text=text)
    except Exception:
        logger.info(f"Discord message (bot not running): {text}")


def _parse_proposal(json_str: str) -> dict:
    """Parse proposal from LM Studio JSON response."""
    import json
    match = re.search(r'\{.*\}', json_str, re.DOTALL)
    if not match:
        return {}
    try:
        return json.loads(match.group())
    except json.JSONDecodeError:
        logger.warning(f"Failed to parse proposal JSON")
        return {}


def _slugify(text: str) -> str:
    """Convert text to filename-safe slug."""
    text = text.lower()
    text = re.sub(r'[^a-z0-9]+', '-', text)
    return text.strip('-')[:40]
