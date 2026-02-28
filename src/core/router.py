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

# Model override file — stores the alias (e.g. "opus", "sonnet", "lm")
_OVERRIDE_FILE = ROOT_DIR / "memory" / "model-override.txt"

# Full registry: alias → {provider, model, label}
# model=None means use the provider's default
MODEL_REGISTRY = {
    # Claude variants
    "claude":   {"provider": "claude-code", "model": "claude-sonnet-4-6",          "label": "☁️ Claude Sonnet"},
    "sonnet":   {"provider": "claude-code", "model": "claude-sonnet-4-6",          "label": "☁️ Claude Sonnet"},
    "opus":     {"provider": "claude-code", "model": "claude-opus-4-5",            "label": "🧠 Claude Opus"},
    "haiku":    {"provider": "claude-code", "model": "claude-haiku-4-5",           "label": "⚡ Claude Haiku"},
    # Other providers
    "lm":       {"provider": "lm-studio",   "model": "local-model",               "label": "🖥️ LM Studio"},
    "local":    {"provider": "lm-studio",   "model": "local-model",               "label": "🖥️ LM Studio"},
    "groq":     {"provider": "groq",        "model": "llama-3.3-70b-versatile",   "label": "⚡ Groq"},
    "gemini":   {"provider": "gemini",      "model": "gemini-2.5-pro",            "label": "✨ Gemini"},
    # Clear override
    "auto":     None,
    "off":      None,
}


def get_override() -> Optional[dict]:
    """
    Return the current override dict {provider, model, label} or None for auto-routing.
    """
    try:
        if _OVERRIDE_FILE.exists():
            alias = _OVERRIDE_FILE.read_text().strip().lower()
            if alias and alias in MODEL_REGISTRY and MODEL_REGISTRY[alias] is not None:
                return MODEL_REGISTRY[alias]
    except Exception:
        pass
    return None


def set_override(alias: str) -> str:
    """
    Set a model override by alias (e.g. 'opus', 'sonnet', 'lm', 'auto').
    Stores the alias in the override file. Returns a confirmation string.
    """
    alias = alias.strip().lower()

    # Strip leading slash for /opus /sonnet style
    if alias.startswith("/"):
        alias = alias[1:]

    # Handle "claude opus", "claude sonnet" etc.
    alias = alias.replace("claude ", "").replace(" claude", "")

    if alias not in MODEL_REGISTRY:
        valid = "`sonnet`, `opus`, `haiku`, `lm`, `groq`, `gemini`, `auto`"
        return f"Unknown model `{alias}`. Valid options: {valid}"

    entry = MODEL_REGISTRY[alias]
    try:
        _OVERRIDE_FILE.parent.mkdir(parents=True, exist_ok=True)
        if entry is None:
            _OVERRIDE_FILE.write_text("")
            return "✅ Back to **auto-routing** — I'll pick the best model for each task."
        else:
            _OVERRIDE_FILE.write_text(alias)
            return (
                f"✅ Locked to **{entry['label']}** (`{entry['model']}`) for all messages.\n"
                f"Say `use auto` to switch back to smart routing."
            )
    except Exception as e:
        return f"Failed to set override: {e}"


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

    # ── Check for manual override first ──────────────────────────────────────
    override = get_override()
    if override:
        result = {
            "provider": override["provider"],
            "model": override["model"],
            "label": override["label"],
            "reason": f"🔒 {override['label']}",
            "estimated_tokens": max(50, len(task) // 4 + 200),
            "timestamp": datetime.now().isoformat(),
            "task_preview": task[:80] + "..." if len(task) > 80 else task
        }
        _log_routing(result)
        return result

    task_lower = task.lower()

    # ── Working context active → Claude ONLY for action requests ─────────────
    # If Offline has focused on a repo and gives an action command, route to
    # Claude so it can actually run bash, edit files, push, etc.
    # Casual questions / chat still use LM Studio even with context set.
    _WORKING_CTX_ACTION_TRIGGERS = [
        "add ", "update ", "edit ", "change ", "fix ", "remove ", "delete ",
        "rename ", "move ", "push ", "commit ", "deploy ", "publish ",
        "refactor ", "rewrite ", "improve ", "create ", "build ", "make ",
        "generate ", "implement ", "set up ", "configure ",
        "pr", "pull request", "readme", "test", "style", "dark mode",
        "git ", "branch ", "merge ",
    ]
    try:
        from src.core.memory import get_working_context
        _wc = get_working_context()
        if _wc and any(w in task_lower for w in _WORKING_CTX_ACTION_TRIGGERS):
            provider = "claude-code"
            model = CONFIG["models"]["heavy"]["model"]
            reason = f"🎯 Working context + action → Claude ({_wc.get('name', '?')})"
            result = {
                "provider": provider, "model": model, "reason": reason,
                "estimated_tokens": max(50, len(task) // 4 + 200),
                "timestamp": datetime.now().isoformat(),
                "task_preview": task[:80] + "..." if len(task) > 80 else task
            }
            _log_routing(result)
            return result
    except Exception:
        pass  # Don't let a memory read failure break routing

    # ── Action verbs → Claude (LM Studio can't execute, only talk) ───────────
    # These words imply "do something real" — files, git, GitHub, etc.
    _action_triggers = [
        "add a ", "add the ", "add an ", "update the ", "update my ", "update a ",
        "edit the ", "edit my ", "change the ", "change my ", "fix the ", "fix my ",
        "remove the ", "delete the ", "rename the ", "move the ",
        "push it", "push to", "push the ", "commit ", "git ",
        "deploy ", "publish ", "create a pr", "open a pr", "pull request",
        "refactor ", "rewrite ", "improve the ", "improve my ",
        "add dark mode", "add light mode", "add a readme", "add readme",
        "add a feature", "add feature", "add tests", "add a test",
        "make it ", "make the ", "make my ",
    ]
    if any(w in task_lower for w in _action_triggers):
        provider = "claude-code"
        model = CONFIG["models"]["heavy"]["model"]
        reason = "Action request → Claude (can execute bash/git/files)"

    # ── Web-search intent → Gemini (Google Search grounded) ──────────────────
    elif any(w in task_lower for w in [
        "search the web", "search online", "look it up online", "google it",
        "find online", "look online", "search for", "find out online",
        "what's the weather", "what is the weather", "weather in",
        "current price", "latest news", "news about", "what's happening with",
    ]):
        provider = "gemini"
        model = "gemini-2.5-pro"
        reason = "Web search → Gemini (Google Search grounded)"

    # ── Vision tasks → Groq ───────────────────────────────────────────────────
    elif any(w in task_lower for w in ["image", "screenshot", "picture", "photo"]):
        provider = "groq"
        model = CONFIG["models"]["vision"]["model"]
        reason = "Vision task routed to Groq"

    # ── Speech tasks → Groq ───────────────────────────────────────────────────
    elif any(w in task_lower for w in ["transcribe", "audio", "voice", "speech", "recording"]):
        provider = "groq"
        model = CONFIG["models"]["speech"]["model"]
        reason = "Speech task routed to Groq"

    else:
        # Keyword-based routing + complexity scoring
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
