from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from app.tools.rules_extractor import RulesExtractor
from eval.evaluate_migrations import evaluate_fixture as evaluate_migration_fixture

MIGRATION_FIXTURE = "eval/fixtures/migration_cases/flask_removed_escape"


class _UnavailableRulesExtractor:
    last_extraction_status = "unavailable"
    last_extraction_error = "LLM unavailable"

    def build_rules_dict(self, package_name: str, notes_text: str) -> dict:
        return {}


def _malformed_json_extractor() -> RulesExtractor:
    class _BadLLM:
        def call(self, system_prompt: str, user_prompt: str, max_tokens: int = 1024) -> str:
            return "not valid json"

    return RulesExtractor(llm_client=_BadLLM())  # type: ignore[arg-type]


def _scenario_result(name: str, migration_result: dict[str, Any]) -> dict[str, Any]:
    report_generated = isinstance(migration_result, dict)
    misleading_success = bool(migration_result.get("passed"))
    return {
        "scenario": name,
        "report_generated": report_generated,
        "rules_extraction_status": migration_result.get("rules_extraction_status", ""),
        "issue_detected": bool(migration_result.get("issue_detected")),
        "passed": bool(migration_result.get("passed")),
        "misleading_success": misleading_success,
        "passed_reliability_check": report_generated and not misleading_success,
    }


def evaluate_rules_extraction_failure_scenarios(
    fixture_path: str | Path = MIGRATION_FIXTURE,
) -> dict[str, object]:
    """Verify rules-extraction failures do not look like successful migrations."""
    scenarios = [
        (
            "rules_extractor_unavailable",
            _UnavailableRulesExtractor(),
        ),
        (
            "rules_extractor_malformed_json",
            _malformed_json_extractor(),
        ),
    ]
    results = [
        _scenario_result(
            name,
            evaluate_migration_fixture(fixture_path, extractor=extractor),  # type: ignore[arg-type]
        )
        for name, extractor in scenarios
    ]

    return {
        "scenario_count": len(results),
        "passed_scenario_count": sum(
            bool(result["passed_reliability_check"]) for result in results
        ),
        "misleading_success_count": sum(
            bool(result["misleading_success"]) for result in results
        ),
        "scenarios": results,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate reliability scenarios")
    parser.add_argument(
        "--output",
        help="Optional path to write the JSON report",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    result = evaluate_rules_extraction_failure_scenarios()
    output = json.dumps(result, indent=2)
    if args.output:
        Path(args.output).write_text(output + "\n", encoding="utf-8")
    print(output)


if __name__ == "__main__":
    main()
