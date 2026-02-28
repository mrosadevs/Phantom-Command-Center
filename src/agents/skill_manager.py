"""
skill_manager.py — Skill and MCP installer for Phantom Command Center.

Handles two types of installs:
  1. Skills: Download SKILL.md files from URLs and register them
  2. MCPs: Install MCP server npm packages and configure Claude Desktop

When Theodore says "learn [url]" or "install [mcp name]", this runs.
"""

import json
import logging
import os
import re
import subprocess
from pathlib import Path

import httpx

from src.core import memory
from src.core.config import ROOT_DIR, load_mcp_registry, save_mcp_registry, get_secret

logger = logging.getLogger(__name__)

SKILLS_DIR = ROOT_DIR / "skills"
CLAUDE_DESKTOP_CONFIG = Path.home() / "AppData/Roaming/Claude/claude_desktop_config.json"


async def install_skill(url_or_name: str) -> str:
    """
    Install a skill from a URL or known skill name.

    If a URL is provided, downloads the skill file and registers it.
    Returns a status message.
    """
    url_or_name = url_or_name.strip()

    # Check if it's a URL
    if url_or_name.startswith("http://") or url_or_name.startswith("https://"):
        return await _install_skill_from_url(url_or_name)
    else:
        return f"Skill by name not yet supported. Please provide a direct URL to the skill file."


def _resolve_raw_url(url: str) -> list[str]:
    """
    Convert a human-facing URL to a list of raw content URLs to try in order.
    Handles GitHub repos, ClawHub pages, and direct raw URLs.
    """
    import re

    # Already a raw URL — use as-is
    if "raw.githubusercontent.com" in url or url.endswith(".md"):
        return [url]

    # GitHub repo page: github.com/{owner}/{repo}
    gh = re.match(r'https?://github\.com/([^/]+)/([^/]+?)/?$', url)
    if gh:
        owner, repo = gh.group(1), gh.group(2)
        base = f"https://raw.githubusercontent.com/{owner}/{repo}"
        return [
            f"{base}/main/SKILL.md",
            f"{base}/main/README.md",
            f"{base}/master/SKILL.md",
            f"{base}/master/README.md",
        ]

    # ClawHub page: clawhub.ai/{owner}/{slug}
    ch = re.match(r'https?://(?:www\.)?clawhub\.(?:ai|com)/([^/]+)/([^/]+?)/?$', url)
    if ch:
        owner, slug = ch.group(1), ch.group(2)
        owner_lc = owner.lower()
        slug_lc = slug.lower()
        return [
            # openclaw/skills monorepo (lowercase paths)
            f"https://raw.githubusercontent.com/openclaw/skills/main/skills/{owner_lc}/{slug_lc}/SKILL.md",
            f"https://raw.githubusercontent.com/openclaw/skills/main/skills/{owner}/{slug}/SKILL.md",
            # author's own repo
            f"https://raw.githubusercontent.com/{owner}/{slug}/main/SKILL.md",
            f"https://raw.githubusercontent.com/{owner_lc}/{slug_lc}/main/SKILL.md",
            f"https://raw.githubusercontent.com/peterskoett/{slug}/main/SKILL.md",
        ]

    return [url]


async def _install_skill_from_url(url: str) -> str:
    """Download a skill file from a URL and register it."""
    logger.info(f"Downloading skill from: {url}")

    raw_urls = _resolve_raw_url(url)
    content = None

    async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
        for raw_url in raw_urls:
            try:
                resp = await client.get(raw_url)
                if resp.status_code == 200 and not resp.text.strip().startswith("<"):
                    content = resp.text
                    logger.info(f"Fetched skill content from: {raw_url}")
                    break
            except Exception:
                continue

    if not content:
        return (
            f"Couldn't fetch skill content from {url}\n"
            f"Tried {len(raw_urls)} URL(s). Make sure it's a GitHub repo or ClawHub skill link."
        )

    # Extract skill name from content (look for # Title or first heading)
    name_match = re.search(r'^#\s+(.+)', content, re.MULTILINE)
    skill_name = name_match.group(1).strip() if name_match else _slugify(url.split("/")[-1])

    # Save the skill file
    safe_name = _slugify(skill_name)
    skill_path = SKILLS_DIR / f"{safe_name}.md"
    skill_path.write_text(content, encoding="utf-8")

    # Extract capabilities from the skill content (look for ## Description or similar)
    cap_match = re.search(r'(?:##?\s*Description|##?\s*What|##?\s*Overview)\s*\n(.+?)(?=\n##|\Z)',
                          content, re.DOTALL | re.IGNORECASE)
    capabilities = cap_match.group(1).strip()[:200] if cap_match else "See skill file for details"

    # Register in memory
    memory.register_skill(skill_name, url, capabilities)

    logger.info(f"Skill installed: {skill_name} -> {skill_path}")
    return (
        f"**Skill Installed: {skill_name}**\n"
        f"File saved to: `{skill_path.relative_to(ROOT_DIR)}`\n"
        f"Capabilities: {capabilities}"
    )


async def install_mcp(mcp_name: str) -> str:
    """
    Install an MCP server by name.

    Looks up the package in the registry, installs via npm,
    configures Claude Desktop, and registers in memory.
    """
    mcp_name = mcp_name.strip().lower()
    registry = load_mcp_registry()
    known = registry.get("known_servers", {})

    # Find the server (allow partial name match)
    matched_name = None
    for name in known:
        if mcp_name in name or name in mcp_name:
            matched_name = name
            break

    if not matched_name:
        return (
            f"Unknown MCP server: '{mcp_name}'\n"
            f"Known servers: {', '.join(known.keys())}\n"
            f"Or provide a full npm package name."
        )

    server_info = known[matched_name]
    package = server_info["package"]
    env_keys = server_info.get("env_keys", [])
    description = server_info.get("description", "")

    # Check if already installed
    installed = [s["name"] for s in registry.get("installed", [])]
    if matched_name in installed:
        return f"MCP '{matched_name}' is already installed."

    # Collect any required env keys
    env_values = {}
    missing_keys = []
    for key in env_keys:
        try:
            env_values[key] = get_secret(key)
        except EnvironmentError:
            missing_keys.append(key)

    if missing_keys:
        return (
            f"Missing required secrets for {matched_name}: {', '.join(missing_keys)}\n"
            f"Add them to your .env file and try again."
        )

    # Install the npm package globally
    logger.info(f"Installing MCP package: {package}")
    result = subprocess.run(
        ["npm", "install", "-g", package],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        logger.error(f"npm install failed: {result.stderr}")
        return f"Failed to install {package}:\n```\n{result.stderr[:500]}\n```"

    # Update Claude Desktop config
    _add_to_claude_desktop(matched_name, package, env_values)

    # Update MCP registry
    registry["installed"].append({
        "name": matched_name,
        "package": package,
        "installed_at": __import__('datetime').datetime.now().isoformat()
    })
    save_mcp_registry(registry)

    # Register in memory
    memory.register_mcp(matched_name, package, description)

    logger.info(f"MCP installed: {matched_name}")
    return (
        f"**MCP Installed: {matched_name}**\n"
        f"Package: `{package}`\n"
        f"Description: {description}\n"
        f"Restart Claude Desktop to activate it."
    )


def _add_to_claude_desktop(name: str, package: str, env_values: dict):
    """Add an MCP server entry to Claude Desktop's config file."""
    # Load existing config or create new
    if CLAUDE_DESKTOP_CONFIG.exists():
        with open(CLAUDE_DESKTOP_CONFIG) as f:
            config = json.load(f)
    else:
        config = {}

    if "mcpServers" not in config:
        config["mcpServers"] = {}

    # Build the server entry
    server_key = name.replace(" ", "-")
    config["mcpServers"][server_key] = {
        "command": "npx",
        "args": ["-y", package],
        "env": env_values
    }

    # Write back
    CLAUDE_DESKTOP_CONFIG.parent.mkdir(parents=True, exist_ok=True)
    with open(CLAUDE_DESKTOP_CONFIG, "w") as f:
        json.dump(config, f, indent=2)

    logger.info(f"Added {name} to Claude Desktop config")


def _slugify(text: str) -> str:
    """Convert a string to a filesystem-safe slug."""
    text = text.lower()
    text = re.sub(r'[^a-z0-9]+', '-', text)
    return text.strip('-')[:50]
