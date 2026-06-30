"""
Pluggable LLM client for AI-powered agents.

OpenAI-compatible: works with AICredits (https://aicredits.in/v1), Ollama
(http://localhost:11434/v1), OpenAI, OpenRouter, etc. — configured purely by env:

    LLM_BASE_URL   default https://aicredits.in/v1
    LLM_API_KEY    required to enable real AI (kept in .env, never committed)
    LLM_MODEL      default openai/gpt-4o-mini

If no API key is configured, is_available() is False and callers fall back to
the deterministic task path, so the swarm always runs even with no AI backend.
"""
import os
from typing import Optional

import httpx


class LLMClient:
    def __init__(self):
        self.base_url = os.getenv("LLM_BASE_URL", "https://aicredits.in/v1").rstrip("/")
        self.api_key = os.getenv("LLM_API_KEY", "")
        self.model = os.getenv("LLM_MODEL", "openai/gpt-4o-mini")
        self._client: Optional[httpx.AsyncClient] = None

    def is_available(self) -> bool:
        return bool(self.api_key)

    def _http(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=60.0)
        return self._client

    async def complete(self, system: str, user: str, max_tokens: int = 512,
                       temperature: float = 0.3) -> Optional[str]:
        """Run a chat completion. Returns the text, or None on failure."""
        if not self.is_available():
            return None
        try:
            resp = await self._http().post(
                f"{self.base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                    "max_tokens": max_tokens,
                    "temperature": temperature,
                },
            )
            if resp.status_code != 200:
                print(f"⚠️ LLM call failed: HTTP {resp.status_code} {resp.text[:200]}")
                return None
            data = resp.json()
            return data["choices"][0]["message"]["content"].strip()
        except Exception as e:
            print(f"⚠️ LLM call error: {e}")
            return None

    async def close(self):
        if self._client is not None:
            await self._client.aclose()
            self._client = None


# Shared singleton
_llm: Optional[LLMClient] = None


def get_llm() -> LLMClient:
    global _llm
    if _llm is None:
        _llm = LLMClient()
    return _llm
