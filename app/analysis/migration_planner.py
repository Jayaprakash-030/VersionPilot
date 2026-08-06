from __future__ import annotations

from typing import Any, Dict, List


class MigrationPlanner:
    """Baseline deterministic migration planner from detected findings."""

    _MAX_BREAKING_STEPS = 8
    _MAX_BREAKING_PER_PACKAGE = 3

    def generate_plan(
        self,
        deprecated_findings: list[dict[str, Any]],
        breaking_change_analysis: dict[str, Any],
    ) -> Dict[str, Any]:
        """Build an ordered migration plan from deprecated API and breaking-change findings."""
        steps: List[Dict[str, Any]] = []

        # Step 1: address explicit deprecated API findings.
        for finding in deprecated_findings:
            steps.append(
                {
                    "priority": 1,
                    "type": "deprecated_api_replacement",
                    "package": finding.get("package", "unknown"),
                    "symbol": finding.get("symbol", "unknown"),
                    "file_path": finding.get("file_path", "<unknown>"),
                    "line": finding.get("line", 0),
                    "action": finding.get("replacement", "Replace deprecated API usage"),
                    "severity": finding.get("severity", "medium"),
                    "confidence": "ast_scan",
                }
            )

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
