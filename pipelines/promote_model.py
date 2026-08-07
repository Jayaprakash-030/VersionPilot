from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = ROOT / "config" / "model_registry.json"

FOCUSED_TESTS = [
    "tests/unit/test_evaluate_scanner.py",
    "tests/unit/test_evaluate_rules_extractor.py",
    "tests/unit/test_evaluate_scoring.py",
    "tests/unit/test_evaluate_migrations.py",
    "tests/unit/test_evaluate_reliability.py",
    "tests/unit/test_evaluate_groundedness.py",
]


def _load_json(path: Path) -> dict[str, Any]:
    """Load a required JSON file or raise if it is missing."""
    if not path.exists():
        raise ValueError(f"missing required file: {path.relative_to(ROOT)}")
    return json.loads(path.read_text(encoding="utf-8"))


def _expect(condition: bool, message: str, failures: list[str]) -> None:
    """Append a failure message when the expected condition is false."""
    if not condition:
        failures.append(message)


def validate_registry(registry_path: Path = REGISTRY_PATH) -> list[str]:
    """Validate the production model registry against the approved baseline."""
    failures: list[str] = []
    registry = _load_json(registry_path)
    production = registry.get("production", {})

    _expect(
        production.get("system_version") == "versionpilot-python-v1.0",
        "registry system version is not versionpilot-python-v1.0",
        failures,
    )
    _expect(production.get("status") == "approved", "registry production status is not approved", failures)
    _expect(
        production.get("scoring_config") == "config/scoring_v1.yaml",
        "registry does not point to config/scoring_v1.yaml",
        failures,
    )
    _expect(production.get("llm_provider") == "openai", "registry LLM provider is not openai", failures)
    _expect(production.get("default_model") == "gpt-5.4-nano", "registry default model changed", failures)

    scoring_config = ROOT / production.get("scoring_config", "")
    eval_report = ROOT / production.get("eval_report", "")
    _expect(scoring_config.exists(), "registered scoring config file does not exist", failures)
    _expect(eval_report.exists(), "registered eval report file does not exist", failures)

    return failures


def validate_rules_extractor_report(path: Path = ROOT / "eval" / "rules_extractor_report.json") -> list[str]:
    """Validate the rules-extractor eval report against baseline thresholds."""
    failures: list[str] = []
    report = _load_json(path)

    _expect(report.get("fixture_count") == 16, "rules extractor fixture count is not 16", failures)
    _expect(report.get("run_count") == 48, "rules extractor run count is not 48", failures)
    _expect(report.get("passed_fixture_count") == 16, "rules extractor fixtures did not all pass", failures)
    _expect(report.get("passed_run_count") == 48, "rules extractor runs did not all pass", failures)
    _expect(report.get("failed_fixtures") == [], "rules extractor has failed fixtures", failures)
    _expect(report.get("consistency_rate") == 1.0, "rules extractor consistency rate regressed", failures)
    _expect(report.get("valid_schema_rate") == 1.0, "rules extractor schema validity regressed", failures)
    _expect(report.get("metrics", {}).get("f1") == 1.0, "rules extractor F1 regressed", failures)

    return failures


def validate_migration_report(path: Path = ROOT / "eval" / "migration_report.json") -> list[str]:
    """Validate the migration eval report against baseline thresholds."""
    failures: list[str] = []
    report = _load_json(path)

    _expect(report.get("fixture_count") == 3, "migration fixture count is not 3", failures)
    _expect(report.get("passed_fixture_count") == 3, "migration fixtures did not all pass", failures)
    _expect(report.get("failed_fixtures") == [], "migration report has failed fixtures", failures)
    _expect(report.get("issue_detected_count") == 3, "migration issue detection regressed", failures)
    _expect(report.get("correct_file_line_count") == 3, "migration file/line accuracy regressed", failures)
    _expect(report.get("useful_recommendation_count") == 3, "migration recommendation usefulness regressed", failures)
    _expect(
        report.get("post_migration_test_case_count") == 3,
        "not all migration cases have post-migration tests",
        failures,
    )
    _expect(
        report.get("post_migration_tests_passed_count") == 3,
        "post-migration tests did not all pass",
        failures,
    )

    return failures


def validate_reliability_report(path: Path = ROOT / "eval" / "reliability_report.json") -> list[str]:
    """Validate the reliability eval report against baseline thresholds."""
    failures: list[str] = []
    report = _load_json(path)

    _expect(report.get("scenario_count") == 10, "reliability scenario count is not 10", failures)
    _expect(report.get("passed_scenario_count") == 10, "reliability scenarios did not all pass", failures)
    _expect(report.get("misleading_success_count") == 0, "reliability report has misleading success cases", failures)
    _expect(
        report.get("misleading_verified_low_count") == 0,
        "reliability report has misleading verified-Low cases",
        failures,
    )

    return failures


def run_focused_tests() -> tuple[bool, str]:
    """Run the focused evaluation unit tests and return pass status plus output."""
    command = [sys.executable, "-m", "pytest", *FOCUSED_TESTS, "-q"]
    result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, check=False)
    output = "\n".join(part for part in [result.stdout.strip(), result.stderr.strip()] if part)
    return result.returncode == 0, output


def run_promotion_gate(skip_tests: bool = False) -> list[str]:
    """Run registry and eval-report validators, optionally plus focused tests."""
    failures: list[str] = []

    for validator in [
        validate_registry,
        validate_rules_extractor_report,
        validate_migration_report,
        validate_reliability_report,
    ]:
        try:
            failures.extend(validator())
        except (json.JSONDecodeError, ValueError) as exc:
            failures.append(str(exc))

    if not skip_tests:
        tests_passed, test_output = run_focused_tests()
        if not tests_passed:
            failures.append(f"focused evaluation tests failed:\n{test_output}")

    return failures


def main() -> int:
    """CLI entry point for the VersionPilot promotion quality gate."""
    parser = argparse.ArgumentParser(description="Run VersionPilot promotion quality gate.")
    parser.add_argument(
        "--skip-tests",
        action="store_true",
        help="Only validate existing registry and eval artifacts.",
    )
    args = parser.parse_args()

    failures = run_promotion_gate(skip_tests=args.skip_tests)
    if failures:
        print("PROMOTION FAILED")
        for failure in failures:
            print(f"- {failure}")
        return 1

    print("PROMOTION PASSED")
    print("- Registry baseline is valid")
    print("- Rules extractor report meets the baseline")
    print("- Migration report meets the baseline")
    print("- Reliability report meets the baseline")
    if not args.skip_tests:
        print("- Focused evaluation unit tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
