"""
orchestrator.py — Main agent brain for Phantom Command Center.

Coordinates all other agents. Decides what to do based on context,
time of day, and incoming requests. Acts as the central hub.
"""

import logging
from datetime import datetime

from src.core import memory, router
from src.core.config import CONFIG

logger = logging.getLogger(__name__)


async def process_request(request: str, source: str = "discord") -> dict:
    """
    Process any incoming request and return a structured response.

    Args:
        request: The user's message or task
        source: Where it came from ("discord", "dashboard", "cron")

    Returns:
        {"response": str, "provider": str, "actions_taken": list}
    """
    logger.info(f"Orchestrator received [{source}]: {request[:80]}")

    # Get routing decision
    route = await router.route_task(request)
    actions = []

    # Execute based on routing
    response = ""
    if route["provider"] == "lm-studio":
        from src.utils import lm_studio_client
        context = memory.get_full_context()
        system = f"You are Phantom, Theodore's personal AI. Context:\n{context[:1000]}"
        response = await lm_studio_client.chat(request, system=system)
        actions.append("routed_to_lm_studio")

    elif route["provider"] == "claude-code":
        from src.utils import claude_code_sdk
        context = memory.get_full_context()
        full_prompt = f"Context about Theodore:\n{context[:800]}\n\nTask:\n{request}"
        response = await claude_code_sdk.run_task(full_prompt)
        actions.append("routed_to_claude_code")

    elif route["provider"] == "groq":
        from src.utils import groq_client
        context = memory.get_full_context()
        system = f"You are Phantom, Theodore's personal AI. Context:\n{context[:1000]}"
        response = await groq_client.chat(request, system=system)
        actions.append("routed_to_groq")

    elif route["provider"] == "gemini":
        from src.utils import gemini_client
        context = memory.get_full_context()
        full_prompt = f"Context about Theodore:\n{context[:800]}\n\nMessage:\n{request}"
        response = await gemini_client.chat(full_prompt)
        actions.append("routed_to_gemini")

    return {
        "response": response,
        "provider": route["provider"],
        "model": route["model"],
        "reason": route["reason"],
        "actions_taken": actions,
        "timestamp": datetime.now().isoformat()
    }


async def morning_briefing() -> str:
    """
    Generate a morning briefing summary.
    Called by the morning_briefing cron script.
    """
    context = memory.get_full_context()
    today = datetime.now().strftime("%A, %B %d, %Y")

    prompt = (
        f"Generate a morning briefing for Theodore for {today}.\n\n"
        f"Include:\n"
        f"1. A brief good morning\n"
        f"2. Summary of what happened overnight (check research and surprises logs)\n"
        f"3. Suggested focus areas for today based on his projects\n"
        f"4. Any upcoming scheduled tasks\n\n"
        f"Context:\n{context[:1500]}\n\n"
        f"Keep it concise and energizing. Be like a smart assistant, not a report generator."
    )

    from src.utils import lm_studio_client
    briefing = await lm_studio_client.chat(
        prompt,
        system="You are Phantom, Theodore's AI agent. Write an engaging morning briefing.",
        max_tokens=600
    )

    return briefing
