"""
github_client.py — GitHub API client for Phantom Command Center.

Used to:
  - Fetch repo information for repos Theodore maintains
  - Check for recent commits and activity
  - Identify improvement opportunities
  - Post issues or PRs on Theodore's behalf (with his approval)
"""

import logging
from datetime import datetime, timedelta
from typing import Optional

import httpx

from src.core.config import CONFIG, get_secret

logger = logging.getLogger(__name__)

GITHUB_API = "https://api.github.com"
REPOS_TO_WATCH = CONFIG.get("repos_to_watch", [])


def _get_headers() -> dict:
    """Build auth headers using GITHUB_TOKEN from environment."""
    try:
        token = get_secret("GITHUB_TOKEN")
        return {
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github.v3+json"
        }
    except EnvironmentError:
        logger.warning("GITHUB_TOKEN not set — using unauthenticated GitHub API (rate-limited)")
        return {"Accept": "application/vnd.github.v3+json"}


async def get_repo_info(repo: str) -> dict:
    """
    Get basic info about a repo (stars, description, last push, etc.)
    repo format: "owner/repo-name"
    """
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(f"{GITHUB_API}/repos/{repo}", headers=_get_headers())
        if resp.status_code != 200:
            logger.error(f"GitHub API error for {repo}: {resp.status_code}")
            return {}
        return resp.json()


async def get_recent_commits(repo: str, days: int = 7) -> list:
    """Get commits from the last N days for a repo."""
    since = (datetime.utcnow() - timedelta(days=days)).isoformat() + "Z"
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(
            f"{GITHUB_API}/repos/{repo}/commits",
            params={"since": since, "per_page": 20},
            headers=_get_headers()
        )
        if resp.status_code != 200:
            return []
        return resp.json()


async def get_open_issues(repo: str) -> list:
    """Get open issues for a repo."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(
            f"{GITHUB_API}/repos/{repo}/issues",
            params={"state": "open", "per_page": 10},
            headers=_get_headers()
        )
        if resp.status_code != 200:
            return []
        return resp.json()


async def get_repo_contents(repo: str, path: str = "") -> list:
    """List files/directories in a repo path."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(
            f"{GITHUB_API}/repos/{repo}/contents/{path}",
            headers=_get_headers()
        )
        if resp.status_code != 200:
            return []
        data = resp.json()
        return data if isinstance(data, list) else [data]


async def scan_watched_repos() -> list:
    """
    Scan all repos in repos_to_watch and return a summary of each.
    Used by the overnight builder to find improvement opportunities.
    """
    results = []
    for repo in REPOS_TO_WATCH:
        logger.info(f"Scanning repo: {repo}")
        info = await get_repo_info(repo)
        commits = await get_recent_commits(repo, days=7)
        issues = await get_open_issues(repo)

        results.append({
            "repo": repo,
            "description": info.get("description", ""),
            "language": info.get("language", ""),
            "stars": info.get("stargazers_count", 0),
            "last_push": info.get("pushed_at", ""),
            "recent_commits": len(commits),
            "open_issues": len(issues),
            "topics": info.get("topics", []),
            "homepage": info.get("homepage", "")
        })

    return results
