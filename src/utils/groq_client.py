"""
groq_client.py — Groq API client for Phantom Command Center.

Used for:
  - Vision tasks (image/screenshot analysis via llama-3.2-11b-vision)
  - Speech transcription (whisper-large-v3)
  - Fast LLM inference as a backup for light tasks
"""

import base64
import logging
from pathlib import Path
from typing import Optional

from groq import AsyncGroq

from src.core.config import CONFIG, get_secret

logger = logging.getLogger(__name__)

VISION_MODEL = CONFIG["models"]["vision"]["model"]
SPEECH_MODEL = CONFIG["models"]["speech"]["model"]


def _get_client() -> AsyncGroq:
    """Create an AsyncGroq client with API key from environment."""
    api_key = get_secret("GROQ_API_KEY")
    return AsyncGroq(api_key=api_key)


async def chat(
    prompt: str,
    system: str = "You are a helpful assistant.",
    model: str = "llama-3.3-70b-versatile",
    max_tokens: int = 1000,
    temperature: float = 0.7
) -> str:
    """Send a text chat message to Groq and return the response."""
    client = _get_client()
    try:
        response = await client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": prompt}
            ],
            max_tokens=max_tokens,
            temperature=temperature
        )
        text = response.choices[0].message.content
        logger.info(f"Groq responded ({len(text)} chars) via {model}")
        return text
    except Exception as e:
        logger.error(f"Groq chat failed: {e}")
        return f"[Groq error: {e}]"


async def analyze_image(
    image_path: str,
    question: str = "What do you see in this image?"
) -> str:
    """
    Analyze an image using Groq's vision model.
    image_path can be a local file path or a public URL.
    """
    client = _get_client()

    # Build the content array
    if image_path.startswith("http://") or image_path.startswith("https://"):
        image_content = {"type": "image_url", "image_url": {"url": image_path}}
    else:
        # Load local file and base64-encode it
        img_bytes = Path(image_path).read_bytes()
        b64 = base64.b64encode(img_bytes).decode("utf-8")
        # Guess MIME type from extension
        ext = Path(image_path).suffix.lower()
        mime = {"jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png",
                ".gif": "image/gif", ".webp": "image/webp"}.get(ext, "image/jpeg")
        image_content = {
            "type": "image_url",
            "image_url": {"url": f"data:{mime};base64,{b64}"}
        }

    try:
        response = await client.chat.completions.create(
            model=VISION_MODEL,
            messages=[{
                "role": "user",
                "content": [
                    image_content,
                    {"type": "text", "text": question}
                ]
            }],
            max_tokens=1000
        )
        return response.choices[0].message.content
    except Exception as e:
        logger.error(f"Groq vision failed: {e}")
        return f"[Groq vision error: {e}]"


async def transcribe_audio(audio_path: str, language: str = "en") -> str:
    """
    Transcribe an audio file using Groq's Whisper implementation.
    audio_path must be a local file path.
    """
    client = _get_client()
    try:
        with open(audio_path, "rb") as f:
            transcription = await client.audio.transcriptions.create(
                file=(Path(audio_path).name, f),
                model=SPEECH_MODEL,
                language=language,
                response_format="text"
            )
        logger.info(f"Groq transcribed audio: {audio_path}")
        return transcription
    except Exception as e:
        logger.error(f"Groq transcription failed: {e}")
        return f"[Groq transcription error: {e}]"
