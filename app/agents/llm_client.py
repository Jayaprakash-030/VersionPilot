from __future__ import annotations

import os
import time
from typing import Optional

import anthropic
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage, SystemMessage

load_dotenv()


class LLMClient:
    """Thin wrapper around AnthropicVertex with Gemini fallback.

    Call order:
      1. claude-sonnet-4-6 via Anthropic Vertex (preferred)
      2. gemini-3-flash-preview via Vertex AI (fallback on quota errors)
    """

    DEFAULT_MODEL = "claude-sonnet-4-6"
    GEMINI_MODEL = "gemini-3-flash-preview"
    MAX_RETRIES = 3
    RETRY_BASE_DELAY = 1.0  # seconds

    def __init__(self, model: Optional[str] = None) -> None:
        self.model = model or self.DEFAULT_MODEL
        self._project_id = os.environ.get("GOOGLE_CLOUD_PROJECT", "")
        self._region = os.environ.get("CLOUD_ML_REGION", "us-east5")
        self.client = anthropic.AnthropicVertex(
            region=self._region,
            project_id=self._project_id,
        )
        self.total_input_tokens: int = 0
        self.total_output_tokens: int = 0
        self.last_model_used: str = ""

    def call(
        self,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int = 1024,
    ) -> str:
        """Call Claude first; fall back to Gemini on quota errors."""
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
                self.last_model_used = self.model
                return response.content[0].text
            except anthropic.RateLimitError as exc:
                last_exc = exc
                break  # quota error — no point retrying, go straight to fallback
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                if attempt < self.MAX_RETRIES - 1:
                    time.sleep(self.RETRY_BASE_DELAY * (2**attempt))

        # Gemini fallback
        try:
            result = self._call_gemini(system_prompt, user_prompt, max_tokens)
            self.last_model_used = self.GEMINI_MODEL
            return result
        except Exception as gemini_exc:  # noqa: BLE001
            raise RuntimeError(
                f"Both Claude and Gemini failed. "
                f"Claude error: {last_exc}. Gemini error: {gemini_exc}"
            ) from gemini_exc

    def _call_gemini(self, system_prompt: str, user_prompt: str, max_tokens: int) -> str:
        """Call Gemini via Google AI API (langchain-google-genai)."""
        

        model = ChatGoogleGenerativeAI(
            model=self.GEMINI_MODEL,
            api_key=os.environ.get("GOOGLE_API_KEY", ""),
            max_tokens=max_tokens,
        )
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt),
        ]
        response = model.invoke(messages)
        content = response.content
        if isinstance(content, list):
            return "".join(c.get("text", "") for c in content if isinstance(c, dict))
        return str(content)

    @classmethod
    def is_available(cls) -> bool:
        """Returns True if GCP credentials appear to be configured."""
        return bool(os.environ.get("GOOGLE_CLOUD_PROJECT"))
