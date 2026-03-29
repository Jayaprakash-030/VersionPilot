from __future__ import annotations

from typing import Any, Dict, List


class MigrationPlanner:
    """Baseline deterministic migration planner from detected findings."""

    def generate_plan(
        self,
        deprecated_findings: list[dict[str, Any]],
        breaking_change_analysis: dict[str, Any],
    ) -> Dict[str, Any]:
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
                }
            )

        # Step 2: include generic breakage mitigation actions.
        findings = breaking_change_analysis.get("findings", [])
        for item in findings:
            if str(item.get("category", "")) != "breaking_change":
                continue
            steps.append(
                {
                    "priority": 2,
                    "type": "breaking_change_review",
                    "action": str(item.get("text", "Review breaking change in release notes")),
                    "severity": str(item.get("severity", "high")),
                }
            )

        effort_level = self._estimate_effort(len(steps))

        return {
            "total_steps": len(steps),
            "effort_level": effort_level,
            "steps": steps,
        }

    def _estimate_effort(self, step_count: int) -> str:
        if step_count <= 2:
            return "low"
        if step_count <= 6:
            return "medium"
        return "high"
