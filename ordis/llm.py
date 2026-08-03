"""
LLM adapter — OpenRouter (OpenAI-compatible chat completions + tool calling)

Thin wrapper. Not tied to any specific model — set OPENROUTER_MODEL to
whatever's currently available on https://openrouter.ai/models. Model
catalogs on OpenRouter change over time, so don't assume the default here
stays valid forever.

Auth: reads OPENROUTER_API_KEY from the environment. Never hardcode a key
in source. Get one at https://openrouter.ai/keys.

Docs: https://openrouter.ai/docs/api-reference/chat-completion
"""

import os
from typing import Any, Dict, List, Optional

import requests

from .config import DEFAULT_CONFIG, OrdisConfig


class LLMError(RuntimeError):
    """Raised for missing credentials or a failed/malformed LLM call."""


class OpenRouterClient:
    def __init__(
        self,
        config: OrdisConfig = DEFAULT_CONFIG,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
    ):
        self._config = config
        self.api_key = api_key or os.environ.get("OPENROUTER_API_KEY")
        if not self.api_key:
            raise LLMError(
                "No OpenRouter API key found. Set the OPENROUTER_API_KEY "
                "environment variable (get one at https://openrouter.ai/keys), "
                "or pass api_key= explicitly."
            )
        self.model = model or os.environ.get("OPENROUTER_MODEL", config.openrouter_default_model)
        self._session = requests.Session()
        self._session.headers.update(
            {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                # Optional but recommended by OpenRouter for their
                # rankings/analytics — harmless to include, safe to remove.
                "HTTP-Referer": "https://github.com/your-org/project-ordis",
                "X-Title": "Project ORDIS",
            }
        )

    def chat(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_choice: str = "auto",
    ) -> Dict[str, Any]:
        """Send a chat completion request, return the raw assistant message
        dict (may contain 'content' and/or 'tool_calls')."""
        payload: Dict[str, Any] = {"model": self.model, "messages": messages}
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = tool_choice

        try:
            resp = self._session.post(
                f"{self._config.openrouter_base}/chat/completions",
                json=payload,
                timeout=self._config.request_timeout * 3,
            )
            resp.raise_for_status()
            data = resp.json()
        except requests.RequestException as exc:
            raise LLMError(f"OpenRouter request failed: {exc}") from exc

        if isinstance(data, dict) and data.get("error"):
            raise LLMError(f"OpenRouter returned an error: {data['error']}")

        choices = data.get("choices") or []
        if not choices:
            raise LLMError(f"OpenRouter returned no choices: {data}")
        return choices[0]["message"]
