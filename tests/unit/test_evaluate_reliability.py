from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from eval.evaluate_reliability import (
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


def test_main_writes_reliability_output_file(tmp_path: Path):
    output_path = tmp_path / "reliability_report.json"

    with patch(
        "sys.argv",
        ["evaluate_reliability", "--output", str(output_path)],
    ):
        main()

    report = json.loads(output_path.read_text(encoding="utf-8"))
    assert report["scenario_count"] == 2
    assert report["misleading_success_count"] == 0
