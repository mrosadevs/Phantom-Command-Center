"""
router.py — Smart model router for Phantom Command Center.

Decides which model/provider handles each task:
  - Simple Q&A, formatting, drafts → LM Studio (free, local)
  - Complex reasoning, code, multi-step → Claude Code (Max sub)
  - Vision tasks → Groq
  - Speech/transcription → Groq

Tracks routing decisions and estimated token usage.
"""

import logging
import json
from datetime import datetime
from pathlib import Path
from typing import Optional

from src.core.config import CONFIG, ROUTES, ROOT_DIR

logger = logging.getLogger(__name__)

# Simple log file for routing decisions (read by dashboard)
ROUTING_LOG = ROOT_DIR / "memory" / "routing-log.jsonl"


def _complexity_score(task: str) -> int:
    """
    Score task complexity from 1-10.
    Higher = more complex = needs Claude.
    Based on length, keyword presence, and question depth.
    """
    score = 1
    task_lower = task.lower()
    task_len = len(task.split())

    # Length heuristic
    if task_len > 100:
        score += 3
    elif task_len > 50:
        score += 2
    elif task_len > 20:
        score += 1

    # Complexity keywords
    heavy_keywords = [
        "implement", "build", "create", "refactor", "debug", "fix", "architect",
        "design system", "code", "write a", "generate", "multi-step", "complex",
        "integrate", "deploy", "set up", "configure", "automate"
    ]
    light_keywords = [
        "what is", "explain", "define", "summarize", "list", "format",
        "rephrase", "clean up", "shorter", "longer", "translate"
    ]

    for kw in heavy_keywords:
        if kw in task_lower:
            score += 2

    for kw in light_keywords:
        if kw in task_lower:
            score -= 1

    return max(1, min(10, score))


def _keyword_match_provider(task: str) -> Optional[str]:
    """Check routing rules from routes.json for keyword-based provider match."""
    task_lower = task.lower()
    rules = ROUTES.get("routing_rules", [])

    for rule in rules:
        for keyword in rule.get("keywords", []):
            if keyword in task_lower:
                return rule["provider"], rule["reason"]

    return None, "No keyword match"


async def route_task(task: str, context: dict = None) -> dict:
    """
    Main routing function. Returns a dict with provider, model, reason, and
    estimated token count.

    Usage:
        result = await route_task("Build me a Python script that...")
        # result = {"provider": "claude-code", "model": "...", "reason": "...", "estimated_tokens": 500}
    """
    context = context or {}

    # Check for vision/image tasks first
    if any(w in task.lower() for w in ["image", "screenshot", "picture", "photo"]):
        provider = "groq"
        model = CONFIG["models"]["vision"]["model"]
        reason = "Vision task routed to Groq"

    # Check for speech/transcription tasks
    elif any(w in task.lower() for w in ["transcribe", "audio", "voice", "speech", "recording"]):
        provider = "groq"
        model = CONFIG["models"]["speech"]["model"]
        reason = "Speech task routed to Groq"

    else:
        # Keyword-based routing
        keyword_provider, keyword_reason = _keyword_match_provider(task)
        complexity = _complexity_score(task)
        threshold = ROUTES.get("thresholds", {}).get("complexity_score_for_heavy", 7)

        if keyword_provider == "claude-code" or complexity >= threshold:
            provider = "claude-code"
            model = CONFIG["models"]["heavy"]["model"]
            reason = keyword_reason if keyword_provider == "claude-code" else f"Complexity score {complexity}/{threshold}"
        elif keyword_provider == "lm-studio":
            provider = "lm-studio"
            model = CONFIG["models"]["light"]["model"]
            reason = keyword_reason
        else:
            # Default to free local model
            provider = "lm-studio"
            model = CONFIG["models"]["light"]["model"]
            reason = f"Default routing (complexity {complexity})"

    # Estimate token count (rough heuristic: 1 token ≈ 4 chars)
    estimated_tokens = max(50, len(task) // 4 + 200)

    result = {
        "provider": provider,
        "model": model,
        "reason": reason,
        "estimated_tokens": estimated_tokens,
        "timestamp": datetime.now().isoformat(),
        "task_preview": task[:80] + "..." if len(task) > 80 else task
    }

    # Log the routing decision
    _log_routing(result)

    logger.info(f"Routed to {provider} ({model}): {reason}")
    return result


def _log_routing(result: dict):
    """Append routing decision to the routing log file."""
    try:
        ROUTING_LOG.parent.mkdir(parents=True, exist_ok=True)
        with open(ROUTING_LOG, "a") as f:
            f.write(json.dumps(result) + "\n")
    except Exception as e:
        logger.warning(f"Failed to log routing decision: {e}")


def get_recent_routing_stats(n: int = 50) -> dict:
    """Read last N routing decisions and return summary stats for dashboard."""
    stats = {"claude_code": 0, "lm_studio": 0, "groq": 0, "total": 0}
    try:
        if not ROUTING_LOG.exists():
            return stats
        lines = ROUTING_LOG.read_text().strip().split("\n")
        recent = lines[-n:]
        for line in recent:
            if not line:
                continue
            entry = json.loads(line)
            provider = entry.get("provider", "lm-studio")
            if provider == "claude-code":
                stats["claude_code"] += 1
            elif provider == "groq":
                stats["groq"] += 1
            else:
                stats["lm_studio"] += 1
            stats["total"] += 1
    except Exception as e:
        logger.warning(f"Failed to read routing stats: {e}")
    return stats
