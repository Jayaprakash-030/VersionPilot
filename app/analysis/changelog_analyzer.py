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

    def to_dict(self) -> Dict[str, Any]:
        """Serialize this finding to a plain dictionary."""
        return asdict(self)


class ChangelogAnalyzer:
    """Deterministic baseline analyzer for release/changelog text."""

    _BREAKING_PATTERNS = [
        re.compile(r"\bbreaking\b", re.IGNORECASE),
        re.compile(r"\bremoved\b", re.IGNORECASE),
        re.compile(r"\bincompatible\b", re.IGNORECASE),
        re.compile(r"\bno longer supported\b", re.IGNORECASE),
    ]
    _DEPRECATION_PATTERNS = [
        re.compile(r"\bdeprecated\b", re.IGNORECASE),
        re.compile(r"\bwill be removed\b", re.IGNORECASE),
    ]

    def analyze_release_notes(self, package_name: str, from_version: str, to_version: str, notes_text: str) -> Dict[str, Any]:
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
        }

    def _extract_findings(self, notes_text: str) -> List[BreakingChangeFinding]:
        """Extract deprecation and breaking-change findings from notes line by line."""
        findings: List[BreakingChangeFinding] = []
        for raw_line in notes_text.splitlines():
            line = raw_line.strip()
            if not line:
                continue

            if self._matches_any(line, self._DEPRECATION_PATTERNS):
                findings.append(BreakingChangeFinding(category="deprecation", text=line, severity="medium"))
                continue

            if self._matches_any(line, self._BREAKING_PATTERNS):
                findings.append(BreakingChangeFinding(category="breaking_change", text=line, severity="high"))
                continue

        return findings

    def _matches_any(self, text: str, patterns: List[re.Pattern[str]]) -> bool:
        """Return True if any compiled regex pattern matches the text."""
        return any(pattern.search(text) for pattern in patterns)
