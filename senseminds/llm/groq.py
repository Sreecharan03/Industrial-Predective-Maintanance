"""Groq language model adapter (ADR-018).

Groq exposes an OpenAI-compatible chat API, so the adapter is thin: post the
assembled (system, user) prompt and return the completion text. Grounding and
citation enforcement happen around this call, so a hallucinated claim is dropped
by the validator rather than trusted. Requires ``GROQ_API_KEY``; when absent the
platform uses the deterministic stub (so CI never needs the network).
"""

from __future__ import annotations

from typing import ClassVar

import httpx

from senseminds.llm.base import LanguageModel

_ENDPOINT = "https://api.groq.com/openai/v1/chat/completions"


class GroqLanguageModel(LanguageModel):
    """Calls a Groq-hosted open model (default Llama 3.3 70B)."""

    name: ClassVar[str] = "groq"

    def __init__(
        self,
        api_key: str,
        model: str = "llama-3.3-70b-versatile",
        timeout: float = 30.0,
        temperature: float = 0.0,
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._timeout = timeout
        self._temperature = temperature

    def complete(self, system: str, user: str) -> str:
        response = httpx.post(
            _ENDPOINT,
            headers={"Authorization": f"Bearer {self._api_key}"},
            json={
                "model": self._model,
                "temperature": self._temperature,
                "response_format": {"type": "json_object"},
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            },
            timeout=self._timeout,
        )
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"]
