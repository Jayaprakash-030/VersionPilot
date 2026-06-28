from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any
from unittest.mock import patch

from app.agents.evidence_node import evidence_node
from app.agents.report_node import report_node
from app.agents.scoring_node import scoring_node
from app.agents.state import create_initial_state
from app.tools.rules_extractor import RulesExtractor
from eval.evaluate_migrations import evaluate_fixture as evaluate_migration_fixture

MIGRATION_FIXTURE = "eval/fixtures/migration_cases/flask_removed_escape"
CRITICAL_FAILURE_STEPS = [
    "github_data_collector",
    "dependency_parser",
    "dependency_freshness",
    "vulnerability_scanner",
    "v1_pipeline",
]


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


def _create_report_state() -> dict[str, Any]:
    state = create_initial_state("https://github.com/example/repo")
    state.update(
        {
            "health_score": 72.5,
            "risk_level": "Medium",
            "data_completeness": 0.9,
            "confidence_score": 0.8,
            "critic_passed": True,
            "deprecated_findings": [
                {
                    "package": "flask",
                    "symbol": "flask.escape",
                    "file_path": "app.py",
                    "line": 5,
                    "replacement": "markupsafe.escape",
                    "severity": "high",
                }
            ],
            "migration_plan": {
                "steps": [
                    {
                        "type": "deprecated_api_replacement",
                        "package": "flask",
                        "symbol": "flask.escape",
                        "action": "markupsafe.escape",
                        "severity": "high",
                    }
                ]
            },
        }
    )
    return state


def _report_llm_invalid_json_scenario() -> dict[str, Any]:
    state = _create_report_state()

    with patch("app.agents.report_node.LLMClient.is_available", return_value=True), patch(
        "app.agents.report_node.LLMClient"
    ) as mock_llm:
        mock_llm.return_value.call.return_value = "not valid json"
        result = report_node(state)

    final_report = result["final_report"]
    trace_statuses = [entry.get("status") for entry in result.get("agent_trace", [])]
    required_keys = {
        "summary",
        "health_score",
        "risk_level",
        "key_findings",
        "migration_recommendations",
        "data_quality",
        "critic",
    }
    factual_fields_preserved = (
        final_report.get("health_score") == 72.5
        and final_report.get("risk_level") == "Medium"
        and final_report.get("data_quality", {}).get("completeness") == 0.9
        and final_report.get("data_quality", {}).get("confidence") == 0.8
    )

    return {
        "scenario": "report_llm_invalid_json",
        "report_generated": isinstance(final_report, dict),
        "fallback_used": "fallback" in trace_statuses,
        "required_keys_present": required_keys.issubset(final_report),
        "factual_fields_preserved": factual_fields_preserved,
        "passed_reliability_check": isinstance(final_report, dict)
        and "fallback" in trace_statuses
        and required_keys.issubset(final_report)
        and factual_fields_preserved,
    }


def _critic_rejected_report_scenario() -> dict[str, Any]:
    state = _create_report_state()
    state.update(
        {
            "critic_passed": False,
            "critic_feedback": "Report could not be verified",
            "retry_count": 2,
        }
    )

    with patch("app.agents.report_node.LLMClient.is_available", return_value=False):
        result = report_node(state)

    final_report = result["final_report"]
    critic = final_report.get("critic", {})
    factual_fields_preserved = (
        final_report.get("health_score") == 72.5
        and final_report.get("risk_level") == "Unverified"
        and final_report.get("data_quality", {}).get("completeness") == 0.9
        and final_report.get("data_quality", {}).get("confidence") == 0.8
    )

    return {
        "scenario": "critic_rejected_report",
        "report_generated": isinstance(final_report, dict),
        "risk_level": final_report.get("risk_level", ""),
        "critic_passed": critic.get("passed"),
        "critic_feedback_present": bool(critic.get("feedback")),
        "factual_fields_preserved": factual_fields_preserved,
        "passed_reliability_check": isinstance(final_report, dict)
        and final_report.get("risk_level") == "Unverified"
        and critic.get("passed") is False
        and bool(critic.get("feedback"))
        and factual_fields_preserved,
    }


def _critical_evidence_failure_scenario(failed_step: str) -> dict[str, Any]:
    state = create_initial_state("https://github.com/example/repo")
    state.update(
        {
            "repo_metrics": {
                "stars": 100,
                "forks": 20,
                "last_commit_days": 1,
                "last_release_days": 5,
                "open_issues": 0,
                "closed_issues": 100,
            },
            "dependency_metrics": {
                "total_dependencies": 10,
                "outdated_dependencies": 0,
            },
            "security_metrics": {
                "critical": 0,
                "high": 0,
                "medium": 0,
                "low": 0,
            },
            "failed_steps": [failed_step],
            "critic_passed": True,
        }
    )

    scored = {**state, **scoring_node(state)}
    with patch("app.agents.report_node.LLMClient.is_available", return_value=False):
        report_result = report_node(scored)

    final_report = report_result["final_report"]
    risk_level = final_report.get("risk_level", "")
    failed_steps = final_report.get("data_quality", {}).get("failed_steps", [])

    return {
        "scenario": f"critical_evidence_failure:{failed_step}",
        "report_generated": isinstance(final_report, dict),
        "failed_step": failed_step,
        "risk_level": risk_level,
        "health_score": final_report.get("health_score"),
        "failed_step_reported": failed_step in failed_steps,
        "misleading_verified_low": risk_level == "Low",
        "passed_reliability_check": isinstance(final_report, dict)
        and risk_level == "Unknown"
        and failed_step in failed_steps,
    }


def _clone_failure_scenario() -> dict[str, Any]:
    state = create_initial_state("https://github.com/example/repo", repo_path="")

    with patch("app.agents.evidence_node.ToolRegistry") as mock_registry_class, patch(
        "app.agents.evidence_node.RulesExtractor"
    ) as mock_extractor:
        registry = mock_registry_class.return_value
        registry.run_v1_pipeline.return_value = {
            "status": "ok",
            "repo_metrics": {},
            "dependency_metrics": {},
            "security_metrics": {},
            "failed_steps": [],
        }
        registry.fetch_dependency_names.return_value = {"status": "ok", "names": []}
        registry.clone_repo.return_value = {
            "status": "error",
            "error": "network error",
        }
        registry.generate_migration_plan.return_value = {
            "status": "ok",
            "steps": [],
            "total_steps": 0,
            "effort_level": "low",
        }
        mock_extractor.return_value.build_rules_dict.return_value = {}

        result = evidence_node(state)

    failed_steps = result.get("failed_steps", [])
    migration_failed_steps = result.get("migration_analysis_failed_steps", [])
    clone_provenance = [
        entry
        for entry in result.get("provenance", [])
        if entry.get("source") == "clone_repo"
    ]

    return {
        "scenario": "clone_repo_failure",
        "report_generated": isinstance(result, dict),
        "clone_failed_step_recorded": "clone_repo" in failed_steps,
        "deprecated_scan_failed_for_migration": "deprecated_api_scan"
        in migration_failed_steps,
        "clone_provenance_recorded": bool(clone_provenance)
        and clone_provenance[-1].get("status") == "error",
        "passed_reliability_check": isinstance(result, dict)
        and "clone_repo" in failed_steps
        and "deprecated_api_scan" in migration_failed_steps
        and bool(clone_provenance)
        and clone_provenance[-1].get("status") == "error",
    }


def evaluate_reliability_scenarios() -> dict[str, object]:
    """Evaluate all currently implemented reliability scenarios."""
    rules_result = evaluate_rules_extraction_failure_scenarios()
    scenarios = list(rules_result["scenarios"])
    scenarios.append(_report_llm_invalid_json_scenario())
    scenarios.append(_critic_rejected_report_scenario())
    scenarios.extend(
        _critical_evidence_failure_scenario(step)
        for step in CRITICAL_FAILURE_STEPS
    )
    scenarios.append(_clone_failure_scenario())

    return {
        "scenario_count": len(scenarios),
        "passed_scenario_count": sum(
            bool(scenario["passed_reliability_check"]) for scenario in scenarios
        ),
        "misleading_success_count": sum(
            bool(scenario.get("misleading_success", False)) for scenario in scenarios
        ),
        "misleading_verified_low_count": sum(
            bool(scenario.get("misleading_verified_low", False))
            for scenario in scenarios
        ),
        "scenarios": scenarios,
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
    result = evaluate_reliability_scenarios()
    output = json.dumps(result, indent=2)
    if args.output:
        Path(args.output).write_text(output + "\n", encoding="utf-8")
    print(output)


if __name__ == "__main__":
    main()
