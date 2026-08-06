from __future__ import annotations

import os
import time
from typing import Optional

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()


class LLMClient:
    """Thin OpenAI wrapper used by planner, critic, report, and extraction nodes."""

    DEFAULT_MODEL = "gpt-5.4-nano"
    MAX_RETRIES = 3
    RETRY_BASE_DELAY = 1.0  # seconds
    INPUT_USD_PER_1M = 0.20
    OUTPUT_USD_PER_1M = 1.25

    def __init__(self, model: Optional[str] = None) -> None:
        """Initialize the OpenAI client and per-run usage counters."""
        self.model = model or os.environ.get("OPENAI_MODEL", self.DEFAULT_MODEL)
        self.client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
        self.total_input_tokens: int = 0
        self.total_output_tokens: int = 0
        self.last_model_used: str = ""
        self.cost: float = 0.0

    def call(
        self,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int = 1024,
    ) -> str:
        """Call OpenAI Responses API and return plain output text."""
        last_exc: Optional[Exception] = None

        for attempt in range(self.MAX_RETRIES):
            try:
                response = self.client.responses.create(
                    model=self.model,
                    instructions=system_prompt,
                    input=user_prompt,
                    max_output_tokens=max_tokens,
                )
                self._track_usage(response)
                self._cost_per_run(self.total_input_tokens, self.total_output_tokens)
                self.last_model_used = self.model
                return self._extract_text(response)
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                if attempt < self.MAX_RETRIES - 1:
                    time.sleep(self.RETRY_BASE_DELAY * (2**attempt))

        raise RuntimeError(
            f"OpenAI call failed after {self.MAX_RETRIES} attempts: {last_exc}"
        )

    def _track_usage(self, response: object) -> None:
        """Accumulate input and output token counts from an API response."""
        usage = getattr(response, "usage", None)
        if not usage:
            return
        self.total_input_tokens += int(getattr(usage, "input_tokens", 0) or 0)
        self.total_output_tokens += int(getattr(usage, "output_tokens", 0) or 0)

    @classmethod
    def estimate_cost_usd(cls, input_tokens: int, output_tokens: int) -> float:
        """Estimate USD cost from input and output token counts."""
        return (input_tokens / 1_000_000 * cls.INPUT_USD_PER_1M) + (
            output_tokens / 1_000_000 * cls.OUTPUT_USD_PER_1M
        )

    def _cost_per_run(self, input_tokens: int, output_tokens: int) -> None:
        """Update the client's estimated cost for the current token totals."""
        self.cost = self.estimate_cost_usd(input_tokens, output_tokens)

    def _extract_text(self, response: object) -> str:
        """Pull plain text content out of an OpenAI Responses API payload."""
        output_text = getattr(response, "output_text", None)
        if isinstance(output_text, str):
            return output_text

        output_parts: list[str] = []
        for item in getattr(response, "output", []) or []:
            for content in getattr(item, "content", []) or []:
                text = getattr(content, "text", None)
                if isinstance(text, str):
                    output_parts.append(text)
        return "".join(output_parts)

    @classmethod
    def is_available(cls) -> bool:
        """Returns True if an OpenAI API key appears to be configured."""
        return bool(os.environ.get("OPENAI_API_KEY"))


def merge_llm_usage(telemetry: dict, llm: LLMClient) -> dict:
    """Add one client's cumulative usage into run telemetry and recompute cost.

    Call once per LLMClient instance (after all of its calls). Recomputes
    estimated_cost_usd from state token totals so multi-call clients are not
    double-counted.
    """
    updated = dict(telemetry)
    updated["input_tokens"] = int(updated.get("input_tokens", 0) or 0) + llm.total_input_tokens
    updated["output_tokens"] = int(updated.get("output_tokens", 0) or 0) + llm.total_output_tokens
    updated["model"] = llm.last_model_used or llm.model
    updated["estimated_cost_usd"] = LLMClient.estimate_cost_usd(
        updated["input_tokens"],
        updated["output_tokens"],
    )
    return updated
