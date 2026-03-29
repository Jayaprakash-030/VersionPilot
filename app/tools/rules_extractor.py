from __future__ import annotations

import json
from typing import Optional

from app.agents.llm_client import LLMClient

_SYSTEM_PROMPT = """\
You are a Python package deprecation analyst. Given release notes or a changelog for a
Python package, extract any deprecated or removed symbols, functions, classes, or import
paths. Return a JSON array only — no explanation.

Each item must have:
  "symbol":      the deprecated import path or attribute (e.g. "flask.ext")
  "replacement": what to use instead (empty string if none given)
  "severity":    "high" if removed/breaking, "medium" if deprecated with warning, "low" otherwise
  "note":        short human-readable reason

If no deprecations are found, return [].
"""


class RulesExtractor:
    """Extracts deprecation rules from package release notes via LLM."""

    def __init__(self, llm_client: Optional[LLMClient] = None) -> None:
        if llm_client is not None:
            self.llm: Optional[LLMClient] = llm_client
        else:
            self.llm = LLMClient() if LLMClient.is_available() else None

    def extract_rules(self, package_name: str, notes_text: str) -> list[dict]:
        """Return a list of rule dicts, or [] if LLM unavailable / nothing found."""
        if not self.llm or not notes_text.strip():
            return []
        user_prompt = f"Package: {package_name}\nRelease notes:\n{notes_text}"
        try:
            raw = self.llm.call(_SYSTEM_PROMPT, user_prompt, max_tokens=512)
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                return parsed
            return []
        except Exception:  # noqa: BLE001
            return []

    def build_rules_dict(self, package_name: str, notes_text: str) -> dict:
        """Return a rules dict in the deprecation_rules.json schema for one package."""
        rules = self.extract_rules(package_name, notes_text)
        if not rules:
            return {}
        deprecated_symbols = {
            r["symbol"]: {
                "replacement": r.get("replacement", ""),
                "severity": r.get("severity", "medium"),
                "note": r.get("note", ""),
            }
            for r in rules
            if "symbol" in r
        }
        if not deprecated_symbols:
            return {}
        return {package_name: {"deprecated_symbols": deprecated_symbols}}
