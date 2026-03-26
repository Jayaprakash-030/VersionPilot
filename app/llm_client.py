from __future__ import annotations

import os
import time
from typing import Optional

import anthropic


class LLMClient:
    """Thin wrapper around AnthropicVertex with retry logic and token tracking."""

    DEFAULT_MODEL = "claude-sonnet-4-6"
    MAX_RETRIES = 3
    RETRY_BASE_DELAY = 1.0  # seconds

    def __init__(self, model: Optional[str] = None) -> None:
        self.model = model or self.DEFAULT_MODEL
        self.client = anthropic.AnthropicVertex(
            region=os.environ.get("CLOUD_ML_REGION", "us-east5"),
            project_id=os.environ.get("GOOGLE_CLOUD_PROJECT", ""),
        )
        self.total_input_tokens: int = 0
        self.total_output_tokens: int = 0

    def call(
        self,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int = 1024,
    ) -> str:
        """Call the LLM and return the text response. Retries on transient errors."""
        last_exc: Optional[Exception] = None
        for attempt in range(self.MAX_RETRIES):
            try:
                response = self.client.messages.create(
                    model=self.model,
                    max_tokens=max_tokens,
                    system=system_prompt,
                    messages=[{"role": "user", "content": user_prompt}],
                )
                self.total_input_tokens += response.usage.input_tokens
                self.total_output_tokens += response.usage.output_tokens
                return response.content[0].text
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                if attempt < self.MAX_RETRIES - 1:
                    time.sleep(self.RETRY_BASE_DELAY * (2**attempt))
        raise RuntimeError(f"LLM call failed after {self.MAX_RETRIES} attempts") from last_exc

    @classmethod
    def is_available(cls) -> bool:
        """Returns True if GCP credentials appear to be configured."""
        return bool(os.environ.get("GOOGLE_CLOUD_PROJECT"))
