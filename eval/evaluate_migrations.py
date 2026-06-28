from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from app.analysis.deprecated_api_scanner import DeprecatedAPIScanner
from app.analysis.migration_planner import MigrationPlanner
from app.tools.rules_extractor import RulesExtractor


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _normalize_finding(finding: dict[str, Any], project_root: Path) -> dict[str, Any]:
    file_path = Path(str(finding.get("file_path", "")))
    try:
        normalized_path = file_path.relative_to(project_root)
    except ValueError:
        normalized_path = file_path

    return {
        "package": str(finding.get("package", "")),
        "symbol": str(finding.get("symbol", "")),
        "file_path": str(normalized_path),
        "line": int(finding.get("line", 0)),
        "replacement": str(finding.get("replacement", "")),
        "severity": str(finding.get("severity", "")),
    }


def _finding_key(finding: dict[str, Any]) -> tuple[str, str, int]:
    return (
        str(finding.get("symbol", "")),
        str(finding.get("file_path", "")),
        int(finding.get("line", 0)),
    )


def _plan_step_key(step: dict[str, Any]) -> tuple[str, str, str]:
    return (
        str(step.get("type", "")),
        str(step.get("symbol", "")),
        str(step.get("action", "")),
    )


def evaluate_fixture(
    fixture_path: str | Path,
    extractor: RulesExtractor | None = None,
) -> dict[str, object]:
    """Evaluate one controlled migration case end to end."""
    fixture = Path(fixture_path)
    metadata = _load_json(fixture / "metadata.json")
    expected = _load_json(fixture / "expected.json")
    package_name = metadata["package"]
    notes_text = (fixture / "release_notes.txt").read_text(encoding="utf-8")
    project_root = fixture / "project"

    extractor = extractor or RulesExtractor()
    rules = extractor.build_rules_dict(package_name, notes_text)
    scanner = DeprecatedAPIScanner(rules=rules)
    findings = [
        _normalize_finding(finding.to_dict(), project_root)
        for finding in scanner.scan_repository_path(str(project_root))
    ]
    plan = MigrationPlanner().generate_plan(findings, {"findings": []})

    expected_findings = expected.get("findings", [])
    expected_plan_steps = expected.get("plan_steps", [])
    finding_keys = {_finding_key(finding) for finding in findings}
    expected_finding_keys = {_finding_key(finding) for finding in expected_findings}
    plan_step_keys = {_plan_step_key(step) for step in plan["steps"]}
    expected_plan_step_keys = {
        _plan_step_key(step) for step in expected_plan_steps
    }

    return {
        "fixture": fixture.name,
        "package": package_name,
        "rules_extraction_status": extractor.last_extraction_status,
        "rules_extraction_error": extractor.last_extraction_error,
        "rules": rules,
        "findings": findings,
        "expected_findings": expected_findings,
        "plan": plan,
        "expected_plan_steps": expected_plan_steps,
        "issue_detected": bool(finding_keys & expected_finding_keys),
        "correct_file_line": finding_keys == expected_finding_keys,
        "useful_recommendation": expected_plan_step_keys.issubset(plan_step_keys),
        "passed": finding_keys == expected_finding_keys
        and expected_plan_step_keys.issubset(plan_step_keys),
    }


def evaluate_suite(
    fixtures_path: str | Path,
    extractor: RulesExtractor | None = None,
) -> dict[str, object]:
    """Evaluate every controlled migration fixture."""
    root = Path(fixtures_path)
    results = [
        evaluate_fixture(fixture, extractor=extractor)
        for fixture in sorted(root.iterdir())
        if fixture.is_dir()
    ]
    return {
        "fixture_count": len(results),
        "passed_fixture_count": sum(bool(result["passed"]) for result in results),
        "failed_fixtures": [
            result["fixture"] for result in results if not result["passed"]
        ],
        "issue_detected_count": sum(
            bool(result["issue_detected"]) for result in results
        ),
        "correct_file_line_count": sum(
            bool(result["correct_file_line"]) for result in results
        ),
        "useful_recommendation_count": sum(
            bool(result["useful_recommendation"]) for result in results
        ),
        "fixtures": results,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate controlled migration cases")
    parser.add_argument("fixtures_path", help="Path to one fixture or a fixture root")
    parser.add_argument("--output", help="Optional path to write the JSON report")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    path = Path(args.fixtures_path)
    result = (
        evaluate_fixture(path)
        if (path / "release_notes.txt").exists()
        else evaluate_suite(path)
    )
    output = json.dumps(result, indent=2)
    if args.output:
        Path(args.output).write_text(output + "\n", encoding="utf-8")
    print(output)


if __name__ == "__main__":
    main()
