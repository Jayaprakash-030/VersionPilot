from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock
from unittest.mock import patch

from app.tools.rules_extractor import RulesExtractor
from eval.evaluate_migrations import evaluate_fixture, evaluate_suite, main


def _mock_extractor(rules: dict) -> RulesExtractor:
    extractor = MagicMock(spec=RulesExtractor)
    extractor.build_rules_dict.return_value = rules
    extractor.last_extraction_status = "ok"
    extractor.last_extraction_error = ""
    return extractor


def test_evaluate_fixture_detects_flask_removed_escape_case():
    rules = {
        "flask": {
            "deprecated_symbols": {
                "flask.escape": {
                    "replacement": "markupsafe.escape",
                    "severity": "high",
                    "note": "Removed from Flask",
                }
            }
        }
    }

    result = evaluate_fixture(
        "eval/fixtures/migration_cases/flask_removed_escape",
        extractor=_mock_extractor(rules),
    )

    assert result["fixture"] == "flask_removed_escape"
    assert result["issue_detected"] is True
    assert result["correct_file_line"] is True
    assert result["useful_recommendation"] is True
    assert result["tests_pass_after_fix"] is True
    assert result["passed"] is True


def test_evaluate_fixture_fails_when_rules_extraction_misses_symbol():
    result = evaluate_fixture(
        "eval/fixtures/migration_cases/flask_removed_escape",
        extractor=_mock_extractor({}),
    )

    assert result["issue_detected"] is False
    assert result["correct_file_line"] is False
    assert result["useful_recommendation"] is False
    assert result["passed"] is False


def test_evaluate_fixture_detects_requests_vendored_urllib3_case():
    rules = {
        "requests": {
            "deprecated_symbols": {
                "requests.packages.urllib3": {
                    "replacement": "urllib3",
                    "severity": "high",
                    "note": "Removed vendored import path",
                }
            }
        }
    }

    result = evaluate_fixture(
        "eval/fixtures/migration_cases/requests_vendored_urllib3",
        extractor=_mock_extractor(rules),
    )

    assert result["fixture"] == "requests_vendored_urllib3"
    assert result["issue_detected"] is True
    assert result["correct_file_line"] is True
    assert result["useful_recommendation"] is True
    assert result["tests_pass_after_fix"] is True
    assert result["passed"] is True


def test_evaluate_fixture_detects_numpy_deprecated_bool_alias_case():
    rules = {
        "numpy": {
            "deprecated_symbols": {
                "numpy.bool": {
                    "replacement": "bool",
                    "severity": "medium",
                    "note": "Deprecated alias for built-in bool",
                }
            }
        }
    }

    result = evaluate_fixture(
        "eval/fixtures/migration_cases/numpy_deprecated_bool_alias",
        extractor=_mock_extractor(rules),
    )

    assert result["fixture"] == "numpy_deprecated_bool_alias"
    assert result["issue_detected"] is True
    assert result["correct_file_line"] is True
    assert result["useful_recommendation"] is True
    assert result["tests_pass_after_fix"] is True
    assert result["passed"] is True


def test_evaluate_suite_aggregates_migration_cases():
    rules = {
        "flask": {
            "deprecated_symbols": {
                "flask.escape": {
                    "replacement": "markupsafe.escape",
                    "severity": "high",
                }
            }
        },
        "requests": {
            "deprecated_symbols": {
                "requests.packages.urllib3": {
                    "replacement": "urllib3",
                    "severity": "high",
                }
            }
        },
        "numpy": {
            "deprecated_symbols": {
                "numpy.bool": {
                    "replacement": "bool",
                    "severity": "medium",
                }
            }
        }
    }

    result = evaluate_suite(
        "eval/fixtures/migration_cases",
        extractor=_mock_extractor(rules),
    )

    assert result["fixture_count"] == 3
    assert result["passed_fixture_count"] == 3
    assert result["failed_fixtures"] == []
    assert result["issue_detected_count"] == 3
    assert result["correct_file_line_count"] == 3
    assert result["useful_recommendation_count"] == 3
    assert result["post_migration_test_case_count"] == 3
    assert result["post_migration_tests_passed_count"] == 3


def test_main_writes_output_file_when_requested(tmp_path: Path):
    output_path = tmp_path / "migration_report.json"
    fake_result = {"fixture": "flask_removed_escape", "passed": True}

    with patch(
        "sys.argv",
        [
            "evaluate_migrations",
            "eval/fixtures/migration_cases/flask_removed_escape",
            "--output",
            str(output_path),
        ],
    ), patch(
        "eval.evaluate_migrations.evaluate_fixture",
        return_value=fake_result,
    ):
        main()

    assert json.loads(output_path.read_text(encoding="utf-8")) == fake_result
