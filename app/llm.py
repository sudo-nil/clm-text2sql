"""Swappable LLM interface. Only app.agent should import GeminiLLM directly --
everything else should type against the LLM protocol so the backing model
(or provider) can change without touching the agent loop.
"""
from __future__ import annotations

from typing import Protocol

from google import genai

from app.config import Settings


class LLM(Protocol):
    def generate(self, prompt: str) -> str:
        ...


class GeminiLLM:
    """Vertex AI Gemini, via the google-genai SDK. Same project/ADC as BigQuery."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or Settings.load()
        self._client = genai.Client(
            vertexai=self.settings.use_vertexai,
            project=self.settings.project,
            location=self.settings.location,
        )

    def generate(self, prompt: str) -> str:
        response = self._client.models.generate_content(
            model=self.settings.model,
            contents=prompt,
        )
        text = response.text
        if not text:
            # .text is None/empty when the response has no text part -- a safety
            # block, an empty candidate, or truncation. Fail with the reason
            # rather than letting a None flow downstream into a cryptic error.
            finish = response.candidates[0].finish_reason if response.candidates else None
            raise RuntimeError(f"Gemini returned no text (finish_reason={finish}).")
        return text
