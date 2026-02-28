"""
config.py — Configuration loader for Phantom Command Center.
Loads phantom.config.json and exposes a typed config object.
Also loads .env secrets into the environment.
"""

import json
import os
from pathlib import Path
from dotenv import load_dotenv

# Determine project root (two levels up from this file: src/core -> src -> root)
ROOT = Path(__file__).resolve().parent.parent.parent

# Load .env file
load_dotenv(ROOT / ".env")


def load_config() -> dict:
    """Load and return the master config from config/phantom.config.json."""
    config_path = ROOT / "config" / "phantom.config.json"
    with open(config_path, "r") as f:
        return json.load(f)


def load_routes() -> dict:
    """Load routing rules from config/routes.json."""
    routes_path = ROOT / "config" / "routes.json"
    with open(routes_path, "r") as f:
        return json.load(f)


def load_schedules() -> dict:
    """Load schedule definitions from config/schedules.json."""
    schedules_path = ROOT / "config" / "schedules.json"
    with open(schedules_path, "r") as f:
        return json.load(f)


def load_mcp_registry() -> dict:
    """Load MCP server registry from config/mcp-servers.json."""
    mcp_path = ROOT / "config" / "mcp-servers.json"
    with open(mcp_path, "r") as f:
        return json.load(f)


def save_mcp_registry(data: dict):
    """Save updated MCP registry back to disk."""
    mcp_path = ROOT / "config" / "mcp-servers.json"
    with open(mcp_path, "w") as f:
        json.dump(data, f, indent=2)


def get_secret(key: str, fallback: str = None) -> str:
    """Retrieve a secret from environment variables."""
    val = os.getenv(key, fallback)
    if val is None:
        raise EnvironmentError(f"Missing required secret: {key}")
    return val


# Singleton config loaded once at import time
CONFIG = load_config()
ROUTES = load_routes()
ROOT_DIR = ROOT
MEMORY_DIR = ROOT / "memory"
SKILLS_DIR = ROOT / "skills"
SURPRISES_DIR = ROOT / "surprises"
