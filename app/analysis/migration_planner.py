from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List


class MigrationPlanner:
    """Baseline deterministic migration planner from detected findings."""

    _MAX_BREAKING_STEPS = 8
    _MAX_BREAKING_PER_PACKAGE = 3
    _MAX_SAMPLE_LOCATIONS = 3

    def generate_plan(
        self,
        deprecated_findings: list[dict[str, Any]],
        breaking_change_analysis: dict[str, Any],
    ) -> Dict[str, Any]:
        """Build an ordered migration plan from deprecated API and breaking-change findings."""
        steps: List[Dict[str, Any]] = []
        steps.extend(self._build_deprecated_steps(deprecated_findings))

        # Step 2: changelog heuristic hits (review hints, not proven code impact).
        findings = [
            item
            for item in breaking_change_analysis.get("findings", [])
            if str(item.get("category", "")) == "breaking_change"
        ]
        findings.sort(key=self._breaking_rank, reverse=True)

        breaking_steps: List[Dict[str, Any]] = []
        seen_actions: set[str] = set()
        per_package: dict[str, int] = {}

        for item in findings:
            package = str(item.get("package") or "unknown")
            if per_package.get(package, 0) >= self._MAX_BREAKING_PER_PACKAGE:
                continue

            action = str(item.get("text", "")).strip()
            if not action:
                action = "Review breaking change in release notes"
            action_key = " ".join(action.casefold().split())
            if action_key in seen_actions:
                continue
            seen_actions.add(action_key)

            from_version = item.get("from_version")
            to_version = item.get("to_version")
            version_span = ""
            if from_version and to_version:
                version_span = f"{from_version}→{to_version}"

            breaking_steps.append(
                {
                    "priority": 2,
                    "type": "breaking_change_review",
                    "package": package,
                    "action": action,
                    "severity": str(item.get("severity", "high")),
                    "confidence": str(item.get("confidence") or "regex_heuristic"),
                    "version_span": version_span or None,
                }
            )
            per_package[package] = per_package.get(package, 0) + 1
            if len(breaking_steps) >= self._MAX_BREAKING_STEPS:
                break

        steps.extend(breaking_steps)
        effort_level = self._estimate_effort(len(steps))

        return {
            "total_steps": len(steps),
            "effort_level": effort_level,
            "steps": steps,
        }

    def _build_deprecated_steps(
        self, deprecated_findings: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Collapse duplicate AST findings into polished, user-facing steps."""
        groups: dict[tuple[str, str, str], dict[str, Any]] = {}
        order: list[tuple[str, str, str]] = []

        for finding in deprecated_findings:
            package = str(finding.get("package") or "unknown")
            symbol = str(finding.get("symbol") or "unknown")
            replacement = finding.get("replacement")
            replacement_text = (
                str(replacement).strip()
                if isinstance(replacement, str) and replacement.strip()
                else ""
            )
            key = (package, symbol, replacement_text)
            file_path = str(finding.get("file_path") or "<unknown>")
            line = finding.get("line", 0)
            line_num = line if isinstance(line, int) else 0
            location = self._format_location(file_path, line_num)

            if key not in groups:
                groups[key] = {
                    "package": package,
                    "symbol": symbol,
                    "replacement": replacement_text,
                    "severity": finding.get("severity", "medium"),
                    "locations": [],
                    "file_path": file_path,
                    "line": line_num,
                }
                order.append(key)

            group = groups[key]
            if location and location not in group["locations"]:
                group["locations"].append(location)

        steps: list[dict[str, Any]] = []
        for key in order:
            group = groups[key]
            occurrence_count = len(group["locations"]) or 1
            action = self._format_deprecated_action(
                symbol=group["symbol"],
                replacement=group["replacement"],
                locations=group["locations"],
                occurrence_count=occurrence_count,
            )
            steps.append(
                {
                    "priority": 1,
                    "type": "deprecated_api_replacement",
                    "package": group["package"],
                    "symbol": group["symbol"],
                    "file_path": group["file_path"],
                    "line": group["line"],
                    "action": action,
                    "severity": group["severity"],
                    "confidence": "ast_scan",
                    "occurrence_count": occurrence_count,
                    "sample_locations": group["locations"][: self._MAX_SAMPLE_LOCATIONS],
                }
            )
        return steps

    def _format_deprecated_action(
        self,
        *,
        symbol: str,
        replacement: str,
        locations: list[str],
        occurrence_count: int,
    ) -> str:
        """Build a readable action sentence for a verified deprecated-API finding."""
        location_suffix = self._location_suffix(locations, occurrence_count)
        if not replacement:
            return (
                f"Review deprecated usage of `{symbol}`{location_suffix}; "
                "no replacement specified in extracted rules"
            )

        if self._looks_like_bare_symbol(replacement):
            return (
                f"Replace deprecated usage of `{symbol}` with `{replacement}`"
                f"{location_suffix}"
            )

        # Already a natural-language note — keep it, then add location context.
        base = replacement.rstrip(".")
        return f"{base}{location_suffix}"

    def _location_suffix(self, locations: list[str], occurrence_count: int) -> str:
        if not locations:
            if occurrence_count > 1:
                return f" ({occurrence_count} occurrences)"
            return ""

        samples = locations[: self._MAX_SAMPLE_LOCATIONS]
        sample_text = ", ".join(samples)
        if occurrence_count > len(samples):
            return (
                f" ({occurrence_count} occurrences; e.g. {sample_text})"
            )
        if occurrence_count == 1:
            return f" (at {sample_text})"
        return f" ({occurrence_count} occurrences: {sample_text})"

    @staticmethod
    def _format_location(file_path: str, line: int) -> str:
        short = MigrationPlanner._short_path(file_path)
        if short == "<unknown>":
            return ""
        if isinstance(line, int) and line > 0:
            return f"{short}:{line}"
        return short

    @staticmethod
    def _short_path(file_path: str) -> str:
        """Keep the last few path parts so temp clone prefixes stay readable."""
        if not file_path or file_path == "<unknown>":
            return "<unknown>"
        parts = Path(file_path).parts
        if len(parts) <= 3:
            return str(Path(*parts)) if parts else file_path
        return str(Path(*parts[-3:]))

    @staticmethod
    def _looks_like_bare_symbol(text: str) -> bool:
        """True when replacement is a symbol/path, not a full instruction sentence."""
        cleaned = text.strip().strip("`")
        if not cleaned or " " in cleaned:
            return False
        lower = cleaned.casefold()
        if lower.startswith(("use ", "replace ", "migrate ", "switch ")):
            return False
        return True

    def _breaking_rank(self, item: dict[str, Any]) -> int:
        """Prefer concrete API/runtime removals when capping noisy regex hits."""
        text = str(item.get("text", ""))
        score = 0
        if "`" in text:
            score += 3
        lower = text.casefold()
        if "python" in lower or "pypy" in lower:
            score += 3
        if "method" in lower or "api" in lower or "support" in lower:
            score += 2
        if "http" in lower:
            score += 1
        if "asset" in lower or "github releases" in lower:
            score -= 2
        return score

    def _estimate_effort(self, step_count: int) -> str:
        """Estimate migration effort as low, medium, or high from step count."""
        if step_count <= 2:
            return "low"
        if step_count <= 6:
            return "medium"
        return "high"
