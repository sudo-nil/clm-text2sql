"""Swappable LLM interface. Only app.agent should import GeminiLLM directly --
everything else should type against the LLM protocol so the backing model
(or provider) can change without touching the agent loop.
"""
from __future__ import annotations

import logging
from typing import Protocol

from google import genai
from google.genai import errors
from tenacity import before_sleep_log, retry, retry_if_exception, stop_after_attempt, wait_exponential

from app.config import Settings

logger = logging.getLogger(__name__)


class LLM(Protocol):
    def generate(self, prompt: str) -> str:
        ...


def _is_transient(exc: BaseException) -> bool:
    """5xx is always worth retrying; 429 (rate limit) is a 4xx in google-genai's
    scheme but is also transient. Other 4xx (bad request, auth, not found) are
    not -- retrying those just wastes the repair budget on a bug that won't
    fix itself.
    """
    if isinstance(exc, errors.ServerError):
        return True
    return isinstance(exc, errors.ClientError) and exc.code == 429


class GeminiLLM:
    """Vertex AI Gemini, via the google-genai SDK. Same project/ADC as BigQuery."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or Settings.load()
        self._client = genai.Client(
            vertexai=self.settings.use_vertexai,
            project=self.settings.project,
            location=self.settings.location,
        )

    @retry(
        retry=retry_if_exception(_is_transient),
        stop=stop_after_attempt(4),
        wait=wait_exponential(multiplier=1, min=1, max=20),
        reraise=True,
        before_sleep=before_sleep_log(logger, logging.WARNING),
    )
    def _generate_content(self, prompt: str):
        return self._client.models.generate_content(
            model=self.settings.model,
            contents=prompt,
        )

    def generate(self, prompt: str) -> str:
        try:
            response = self._generate_content(prompt)
        except (errors.ServerError, errors.ClientError) as e:
            logger.warning("Gemini call failed after retries: %s", e)
            raise
        text = response.text
        if not text:
            # .text is None/empty when the response has no text part -- a safety
            # block, an empty candidate, or truncation. Fail with the reason
            # rather than letting a None flow downstream into a cryptic error.
            finish = response.candidates[0].finish_reason if response.candidates else None
            raise RuntimeError(f"Gemini returned no text (finish_reason={finish}).")
        return text
