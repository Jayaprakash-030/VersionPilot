from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from eval.evaluate_groundedness import (
    evaluate_fixture,
    evaluate_report,
    evaluate_suite,
    main,
)


def test_verified_deprecated_fixture_is_grounded():
    result = evaluate_fixture("eval/fixtures/groundedness/verified_deprecated")
    assert result["fixture_check_passed"] is True
    assert result["passed"] is True
    assert result["ungrounded_claims"] == 0
    assert result["migration_recommendations_total"] == 1
    assert result["key_findings_total"] == 1


def test_upstream_hints_fixture_is_grounded():
    result = evaluate_fixture("eval/fixtures/groundedness/with_upstream_hints")
    assert result["fixture_check_passed"] is True
    assert result["passed"] is True
    assert result["upstream_hints_total"] == 1
    assert result["migration_recommendations_total"] == 0


def test_empty_signals_fixture_is_vacuously_grounded():
    result = evaluate_fixture("eval/fixtures/groundedness/empty_signals")
    assert result["fixture_check_passed"] is True
    assert result["passed"] is True
    assert result["total_claims"] == 0
    assert result["groundedness_score"] == 1.0


def test_hallucinated_report_is_detected_as_ungrounded():
    result = evaluate_fixture("eval/fixtures/groundedness/hallucinated_report")
    assert result["expect_passed"] is False
    assert result["passed"] is False
    assert result["ungrounded_claims"] >= 1
    assert result["fixture_check_passed"] is True


def test_evaluate_suite_passes_all_groundedness_fixtures():
    result = evaluate_suite("eval/fixtures/groundedness")
    assert result["fixture_count"] == 4
    assert result["passed_fixture_count"] == 4
    assert result["failed_fixtures"] == []


def test_evaluate_report_rejects_mismatched_health_score():
    state = {
        "health_score": 70.0,
        "risk_level": "Medium",
        "critic_passed": True,
        "deprecated_findings": [],
        "migration_plan": {"steps": []},
        "breaking_change_analysis": {"findings": []},
    }
    report = {
        "health_score": 99.0,
        "risk_level": "Medium",
        "key_findings": [],
        "migration_recommendations": [],
        "upstream_breaking_change_hints": [],
    }
    result = evaluate_report(report, state)
    assert result["passed"] is False
    assert result["health_score_matches"] is False


def test_main_writes_output_file(tmp_path: Path):
    output_path = tmp_path / "groundedness.json"
    with patch(
        "sys.argv",
        [
            "evaluate_groundedness",
            "eval/fixtures/groundedness",
            "--output",
            str(output_path),
        ],
    ):
        main()
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["fixture_count"] == 4
    assert payload["passed_fixture_count"] == 4
