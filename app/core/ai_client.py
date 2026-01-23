"""Anthropic Claude AI client wrapper."""

import time
import logging
from typing import Optional
from pathlib import Path

from anthropic import Anthropic
from app.config import get_settings

logger = logging.getLogger(__name__)

settings = get_settings()

# Initialize client
_client: Optional[Anthropic] = None


def get_client() -> Anthropic:
    """Get or create Anthropic client."""
    global _client
    if _client is None:
        _client = Anthropic(api_key=settings.anthropic_api_key)
    return _client


def load_prompt(prompt_name: str) -> str:
    """Load a prompt template from the prompts directory."""
    prompt_path = Path(__file__).parent.parent / "prompts" / f"{prompt_name}.txt"
    if not prompt_path.exists():
        raise FileNotFoundError(f"Prompt template not found: {prompt_name}")
    return prompt_path.read_text(encoding="utf-8")


def call_claude(
    prompt: str,
    session_id: str,
    prompt_version: str = "v1",
    max_retries: int = 1,
) -> Optional[str]:
    """
    Call Claude API with retry logic and logging.

    Args:
        prompt: The formatted prompt to send
        session_id: Session ID for logging
        prompt_version: Version identifier for logging
        max_retries: Number of retries on failure

    Returns:
        The response text or None if all retries fail
    """
    client = get_client()
    input_size = len(prompt)
    start_time = time.time()

    for attempt in range(max_retries + 1):
        try:
            response = client.messages.create(
                model=settings.ai_model,
                max_tokens=settings.ai_max_tokens,
                temperature=settings.ai_temperature,
                messages=[
                    {"role": "user", "content": prompt}
                ]
            )

            output_text = response.content[0].text
            latency_ms = int((time.time() - start_time) * 1000)

            logger.info(
                "AI call successful",
                extra={
                    "session_id": session_id,
                    "prompt_version": prompt_version,
                    "input_size": input_size,
                    "output_size": len(output_text),
                    "latency_ms": latency_ms,
                    "attempt": attempt + 1,
                }
            )

            return output_text

        except Exception as e:
            logger.warning(
                f"AI call failed (attempt {attempt + 1}/{max_retries + 1}): {e}",
                extra={
                    "session_id": session_id,
                    "prompt_version": prompt_version,
                    "error": str(e),
                }
            )
            if attempt == max_retries:
                logger.error(
                    "AI call failed after all retries",
                    extra={
                        "session_id": session_id,
                        "prompt_version": prompt_version,
                    }
                )
                return None

    return None
