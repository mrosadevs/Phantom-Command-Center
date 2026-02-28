"""
lm_studio_client.py — Client for LM Studio local inference server.

LM Studio exposes an OpenAI-compatible API at http://localhost:1234/v1
This client wraps that API for use across the Phantom system.
"""

import logging
from typing import Optional, AsyncGenerator

import httpx
from openai import AsyncOpenAI

from src.core.config import CONFIG

logger = logging.getLogger(__name__)

LM_STUDIO_BASE = CONFIG["models"]["light"]["endpoint"]
LM_STUDIO_MODEL = CONFIG["models"]["light"]["model"]


def _get_client() -> AsyncOpenAI:
    """Create an AsyncOpenAI client pointed at LM Studio."""
    return AsyncOpenAI(
        base_url=LM_STUDIO_BASE,
        api_key="lm-studio"  # LM Studio accepts any key value
    )


async def is_available() -> bool:
    """Check if LM Studio server is running and reachable."""
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.get(f"{LM_STUDIO_BASE}/models")
            return resp.status_code == 200
    except Exception:
        return False


async def chat(
    prompt: str,
    system: str = "You are a helpful AI assistant.",
    model: Optional[str] = None,
    max_tokens: int = 1000,
    temperature: float = 0.7
) -> str:
    """
    Send a chat message to LM Studio and return the response text.
    Falls back gracefully if LM Studio is offline.
    """
    if not await is_available():
        logger.warning("LM Studio is not available — task cannot be routed locally")
        return "[LM Studio offline. Please start LM Studio to handle this request locally.]"

    client = _get_client()
    used_model = model or LM_STUDIO_MODEL

    try:
        response = await client.chat.completions.create(
            model=used_model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": prompt}
            ],
            max_tokens=max_tokens,
            temperature=temperature
        )
        text = response.choices[0].message.content
        logger.info(f"LM Studio responded ({len(text)} chars)")
        return text
    except Exception as e:
        logger.error(f"LM Studio chat failed: {e}")
        return f"[LM Studio error: {e}]"


async def stream_chat(
    prompt: str,
    system: str = "You are a helpful AI assistant.",
    model: Optional[str] = None,
    max_tokens: int = 1000,
) -> AsyncGenerator[str, None]:
    """
    Stream a chat response from LM Studio chunk by chunk.
    Yields text chunks as they arrive.
    """
    if not await is_available():
        yield "[LM Studio offline]"
        return

    client = _get_client()
    used_model = model or LM_STUDIO_MODEL

    try:
        stream = await client.chat.completions.create(
            model=used_model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": prompt}
            ],
            max_tokens=max_tokens,
            stream=True
        )
        async for chunk in stream:
            delta = chunk.choices[0].delta.content
            if delta:
                yield delta
    except Exception as e:
        logger.error(f"LM Studio stream failed: {e}")
        yield f"[LM Studio stream error: {e}]"


async def list_models() -> list:
    """List all models currently loaded in LM Studio."""
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.get(f"{LM_STUDIO_BASE}/models")
            data = resp.json()
            return [m["id"] for m in data.get("data", [])]
    except Exception as e:
        logger.error(f"Failed to list LM Studio models: {e}")
        return []
