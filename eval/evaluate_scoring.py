from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from app.agents.report_node import report_node
from app.agents.state import create_initial_state
from app.core.pipeline import determine_risk_level

BEHAVIORAL_TEST_PATH = "tests/behavioral/test_scoring_behavior.py"
CRITICAL_FAILURE_STEPS = [
    "github_data_collector",
    "dependency_parser",
    "dependency_freshness",
    "vulnerability_scanner",
    "v1_pipeline",
]


class _ResultCollector:
    def __init__(self) -> None:
        self.passed = 0
        self.failed = 0

    def pytest_runtest_logreport(self, report: pytest.TestReport) -> None:
        if report.when != "call":
            return
        if report.passed:
            self.passed += 1
        elif report.failed:
            self.failed += 1


def count_misleading_verified_low_results() -> int:
    """Count failure scenarios incorrectly published as verified Low risk."""
    published_risks = [
        determine_risk_level(95.0, [step])
        for step in CRITICAL_FAILURE_STEPS
    ]

    state = create_initial_state("https://github.com/example/repo")
    state.update(
        {
            "health_score": 95.0,
            "risk_level": "Low",
            "critic_passed": False,
            "critic_feedback": "Report could not be verified",
        }
    )
    with patch("app.agents.report_node.LLMClient.is_available", return_value=False):
        published_risks.append(report_node(state)["final_report"]["risk_level"])

    return sum(risk == "Low" for risk in published_risks)


def run_evaluation() -> dict[str, int]:
    collector = _ResultCollector()
    pytest.main(["-q", "-p", "no:warnings", BEHAVIORAL_TEST_PATH], plugins=[collector])
    return {
        "checks_passed": collector.passed,
        "checks_total": collector.passed + collector.failed,
        "misleading_verified_low_results": count_misleading_verified_low_results(),
    }


def main() -> None:
    result = run_evaluation()
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
