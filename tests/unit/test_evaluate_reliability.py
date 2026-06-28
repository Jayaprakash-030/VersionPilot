from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from eval.evaluate_reliability import (
    evaluate_reliability_scenarios,
    evaluate_rules_extraction_failure_scenarios,
    main,
)


def test_rules_extraction_failures_do_not_pass_migration_case():
    result = evaluate_rules_extraction_failure_scenarios()

    assert result["scenario_count"] == 2
    assert result["passed_scenario_count"] == 2
    assert result["misleading_success_count"] == 0

    statuses = {
        scenario["scenario"]: scenario["rules_extraction_status"]
        for scenario in result["scenarios"]
    }
    assert statuses["rules_extractor_unavailable"] == "unavailable"
    assert statuses["rules_extractor_malformed_json"] == "error"

    assert all(
        scenario["report_generated"] is True
        and scenario["issue_detected"] is False
        and scenario["passed"] is False
        for scenario in result["scenarios"]
    )


def test_all_reliability_scenarios_include_report_llm_fallback():
    result = evaluate_reliability_scenarios()

    assert result["scenario_count"] == 4
    assert result["passed_scenario_count"] == 4
    assert result["misleading_success_count"] == 0

    scenarios = {
        scenario["scenario"]: scenario
        for scenario in result["scenarios"]
    }
    report_scenario = scenarios["report_llm_invalid_json"]

    assert report_scenario["report_generated"] is True
    assert report_scenario["fallback_used"] is True
    assert report_scenario["required_keys_present"] is True
    assert report_scenario["factual_fields_preserved"] is True
    assert report_scenario["passed_reliability_check"] is True

    critic_scenario = scenarios["critic_rejected_report"]
    assert critic_scenario["report_generated"] is True
    assert critic_scenario["risk_level"] == "Unverified"
    assert critic_scenario["critic_passed"] is False
    assert critic_scenario["critic_feedback_present"] is True
    assert critic_scenario["factual_fields_preserved"] is True
    assert critic_scenario["passed_reliability_check"] is True


def test_main_writes_reliability_output_file(tmp_path: Path):
    output_path = tmp_path / "reliability_report.json"

    with patch(
        "sys.argv",
        ["evaluate_reliability", "--output", str(output_path)],
    ):
        main()

    report = json.loads(output_path.read_text(encoding="utf-8"))
    assert report["scenario_count"] == 4
    assert report["misleading_success_count"] == 0
