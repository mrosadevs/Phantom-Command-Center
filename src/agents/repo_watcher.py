"""
repo_watcher.py — GitHub repo monitoring agent.

Watches Theodore's GitHub repos and identifies improvement opportunities:
  - Missing features
  - Outdated dependencies
  - Documentation gaps
  - Performance improvements
  - New tools that could be added

Results feed into the builder.py overnight build proposals.
"""

import logging
from datetime import datetime

from src.core import memory
from src.utils import lm_studio_client
from src.utils.github_client import scan_watched_repos, get_repo_contents

logger = logging.getLogger(__name__)


async def analyze_repos() -> list:
    """
    Scan watched repos and return a list of improvement proposals.
    Each proposal can be passed to builder.py.
    """
    logger.info("Starting repo watcher analysis...")

    repo_data = await scan_watched_repos()
    context = memory.get_full_context()
    proposals = []

    for repo_info in repo_data:
        repo = repo_info["repo"]
        logger.info(f"Analyzing: {repo}")

        # Get the top-level file structure
        files = await get_repo_contents(repo)
        file_list = [f["name"] for f in files if isinstance(f, dict)]

        prompt = (
            f"Analyze this GitHub repo owned by Theodore and suggest ONE specific improvement:\n\n"
            f"Repo: {repo}\n"
            f"Description: {repo_info.get('description', 'N/A')}\n"
            f"Language: {repo_info.get('language', 'N/A')}\n"
            f"Open issues: {repo_info.get('open_issues', 0)}\n"
            f"Files at root: {', '.join(file_list[:20])}\n"
            f"Recent commits: {repo_info.get('recent_commits', 0)} in last 7 days\n\n"
            f"Context about Theodore:\n{context[:600]}\n\n"
            f"Propose ONE specific, actionable improvement. Be concrete.\n"
            f"Output JSON: "
            f'{{"improvement": "description", "why": "reasoning", "complexity": "low|medium|high"}}'
        )

        result = await lm_studio_client.chat(
            prompt,
            system="You are a code reviewer identifying practical improvements.",
            max_tokens=300
        )

        import json, re
        match = re.search(r'\{.*\}', result, re.DOTALL)
        if match:
            try:
                proposal = json.loads(match.group())
                proposal["repo"] = repo
                proposal["source"] = "repo_watcher"
                proposals.append(proposal)
                logger.info(f"Proposal for {repo}: {proposal.get('improvement', '')[:60]}")
            except json.JSONDecodeError:
                pass

    return proposals


async def check_for_security_issues(repo_data: list) -> list:
    """
    Check if any repos have potential security concerns based on their stack.
    Returns list of urgent issues to flag.
    """
    urgent = []

    for repo in repo_data:
        files = await get_repo_contents(repo["repo"])
        file_names = [f["name"] for f in files if isinstance(f, dict)]

        # Check for common security-sensitive files
        security_flags = []
        if "package.json" in file_names:
            security_flags.append("npm_deps")
        if "requirements.txt" in file_names:
            security_flags.append("python_deps")
        if ".env" in file_names:
            security_flags.append("env_file_exposed")

        if ".env" in file_names:
            urgent.append({
                "repo": repo["repo"],
                "issue": ".env file found in repository root — may contain exposed secrets!",
                "severity": "critical"
            })

    return urgent
