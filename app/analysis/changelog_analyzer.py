from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any, Dict, List


@dataclass(frozen=True)
class BreakingChangeFinding:
    """A single breaking-change or deprecation finding from release notes."""

    category: str
    text: str
    severity: str
    confidence: str = "regex_heuristic"

    def to_dict(self) -> Dict[str, Any]:
        """Serialize this finding to a plain dictionary."""
        return asdict(self)


class ChangelogAnalyzer:
    """Deterministic baseline analyzer for release/changelog text.

    This is intentionally conservative: regex over-reports on headings and
    prose, so we only keep lines that look like concrete changelog bullets.
    Findings are labeled ``regex_heuristic`` because this is not semantic
    understanding — callers should treat them as review hints, not proof.
    """

    _BREAKING_PATTERNS = [
        re.compile(r"\bbreaking(?:\s+changes?|:)\b", re.IGNORECASE),
        re.compile(r"\bremoved\b", re.IGNORECASE),
        re.compile(r"\bincompatible\b", re.IGNORECASE),
        re.compile(r"\bno longer supported\b", re.IGNORECASE),
    ]
    _DEPRECATION_PATTERNS = [
        re.compile(r"\bdeprecated\b", re.IGNORECASE),
        re.compile(r"\bwill be removed\b", re.IGNORECASE),
    ]
    _BULLET_PREFIX = re.compile(r"^(?:[-*]|\d+[.)])\s+")
    _MARKDOWN_HEADING = re.compile(r"^#{1,6}\s+")
    _BOLD_HEADING = re.compile(r"^\*\*[^*].*[^*]\*\*:?\s*$")
    _SECTION_TITLE = re.compile(
        r"^(?:"
        r"breaking(?:\s+changes?)?(?:\s+vs\.?\s+[\w.]+)?"
        r"|incompatible(?:\s+changes?)?"
        r"|removed"
        r"|deprecations?(?:\s+and\s+removals?)?"
        r"|changes?"
        r"|what's\s+changed"
        r"|security"
        r"|features?"
        r"|bugfixes?"
        r")\.?:?$",
        re.IGNORECASE,
    )
    # Concrete signal: code ticks, call-like tokens, version/runtime mentions.
    _CONCRETE_SIGNAL = re.compile(
        r"`[^`]+`"
        r"|\b\w+\.\w+\("
        r"|\bPython\s+\d"
        r"|\bPyPy"
        r"|\bv?\d+\.\d+"
        r"|https?://",
        re.IGNORECASE,
    )
    _MIN_BULLET_LEN = 28
    _MIN_NON_BULLET_LEN = 48

    def analyze_release_notes(
        self,
        package_name: str,
        from_version: str,
        to_version: str,
        notes_text: str,
    ) -> Dict[str, Any]:
        """Analyze release notes text and return structured breaking-change findings."""
        findings = self._extract_findings(notes_text)

        severity_counts = {"high": 0, "medium": 0, "low": 0}
        for finding in findings:
            severity_counts[finding.severity] += 1

        return {
            "package": package_name,
            "from_version": from_version,
            "to_version": to_version,
            "finding_count": len(findings),
            "severity_counts": severity_counts,
            "findings": [f.to_dict() for f in findings],
            "analysis_method": "regex_heuristic",
        }

    def _extract_findings(self, notes_text: str) -> List[BreakingChangeFinding]:
        """Extract deprecation and breaking-change findings from notes line by line."""
        findings: List[BreakingChangeFinding] = []
        seen: set[str] = set()

        for raw_line in notes_text.splitlines():
            line = raw_line.strip()
            if not line or self._is_noise_line(line):
                continue

            is_bullet = bool(self._BULLET_PREFIX.match(line))
            body = self._BULLET_PREFIX.sub("", line).strip()
            if not self._is_actionable_body(body, is_bullet=is_bullet):
                continue

            normalized = re.sub(r"\s+", " ", body).casefold()
            if normalized in seen:
                continue

            if self._matches_any(body, self._DEPRECATION_PATTERNS):
                seen.add(normalized)
                findings.append(
                    BreakingChangeFinding(
                        category="deprecation",
                        text=body,
                        severity="medium",
                        confidence="regex_heuristic",
                    )
                )
                continue

            if self._matches_any(body, self._BREAKING_PATTERNS):
                seen.add(normalized)
                findings.append(
                    BreakingChangeFinding(
                        category="breaking_change",
                        text=body,
                        severity="high",
                        confidence="regex_heuristic",
                    )
                )

        return findings

    def _is_noise_line(self, line: str) -> bool:
        """Skip markdown headings and title-only section labels."""
        if self._MARKDOWN_HEADING.match(line):
            return True
        if self._BOLD_HEADING.match(line):
            return True
        body = self._BULLET_PREFIX.sub("", line).strip().strip("*").strip(":").strip()
        return bool(self._SECTION_TITLE.match(body))

    def _is_actionable_body(self, body: str, *, is_bullet: bool) -> bool:
        """Prefer concrete changelog bullets; keep non-bullets only with strong signals."""
        if self._SECTION_TITLE.match(body.strip("*").strip(":").strip()):
            return False
        if is_bullet:
            return len(body) >= self._MIN_BULLET_LEN
        if len(body) < self._MIN_NON_BULLET_LEN:
            return False
        return bool(self._CONCRETE_SIGNAL.search(body))

    def _matches_any(self, text: str, patterns: List[re.Pattern[str]]) -> bool:
        """Return True if any compiled regex pattern matches the text."""
        return any(pattern.search(text) for pattern in patterns)
