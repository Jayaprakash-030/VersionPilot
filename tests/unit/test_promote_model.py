from __future__ import annotations

import json
from pathlib import Path

from pipelines.promote_model import (
    validate_migration_report,
    validate_registry,
    validate_reliability_report,
    validate_rules_extractor_report,
)


def test_validate_registry_accepts_current_baseline():
    assert validate_registry() == []


def test_validate_rules_extractor_report_rejects_failed_run(tmp_path: Path):
    report = {
        "fixture_count": 16,
        "run_count": 48,
        "passed_fixture_count": 16,
        "passed_run_count": 47,
        "failed_fixtures": [],
        "consistency_rate": 1.0,
        "valid_schema_rate": 1.0,
        "metrics": {"f1": 1.0},
    }
    path = tmp_path / "rules_report.json"
    path.write_text(json.dumps(report), encoding="utf-8")

    failures = validate_rules_extractor_report(path)

    assert "rules extractor runs did not all pass" in failures


def test_validate_migration_report_requires_post_migration_tests(tmp_path: Path):
    report = {
        "fixture_count": 3,
        "passed_fixture_count": 3,
        "failed_fixtures": [],
        "issue_detected_count": 3,
        "correct_file_line_count": 3,
        "useful_recommendation_count": 3,
        "post_migration_test_case_count": 2,
        "post_migration_tests_passed_count": 2,
    }
    path = tmp_path / "migration_report.json"
    path.write_text(json.dumps(report), encoding="utf-8")

    failures = validate_migration_report(path)

    assert "not all migration cases have post-migration tests" in failures
    assert "post-migration tests did not all pass" in failures


def test_validate_reliability_report_rejects_misleading_low_result(tmp_path: Path):
    report = {
        "scenario_count": 10,
        "passed_scenario_count": 10,
        "misleading_success_count": 0,
        "misleading_verified_low_count": 1,
    }
    path = tmp_path / "reliability_report.json"
    path.write_text(json.dumps(report), encoding="utf-8")

    failures = validate_reliability_report(path)

    assert "reliability report has misleading verified-Low cases" in failures
