from __future__ import annotations

from unittest.mock import patch

import pytest

from app.agents.scoring_node import scoring_node


def _base_state(**overrides) -> dict:
    state = {
        "repo_url": "https://github.com/test/repo",
        "repo_path": "",
        "config_version": "config/scoring_v1.yaml",
        "repo_metrics": {
            "stars": 100,
            "forks": 10,
            "last_commit_days": 5,
            "last_release_days": 10,
            "open_issues": 2,
            "closed_issues": 20,
        },
        "dependency_metrics": {
            "total_dependencies": 10,
            "outdated_dependencies": 2,
        },
        "security_metrics": {
            "critical": 0,
            "high": 0,
            "medium": 1,
            "low": 1,
        },
        "failed_steps": [],
        "agent_trace": [],
    }
    state.update(overrides)
    return state


def test_scoring_node_returns_required_keys():
    result = scoring_node(_base_state())
    assert "health_score" in result
    assert "risk_level" in result
    assert "breakdown" in result
    assert "data_completeness" in result
    assert "confidence_score" in result
    assert "agent_trace" in result


def test_scoring_node_known_inputs_score_and_risk():
    result = scoring_node(_base_state())
    assert 0.0 <= result["health_score"] <= 100.0
    assert result["risk_level"] in ("Low", "Medium", "High")


def test_scoring_node_zero_metrics_defaults_gracefully():
    state = _base_state(repo_metrics={}, dependency_metrics={}, security_metrics={})
    result = scoring_node(state)
    # Zero/default metrics: no penalty → score = 100.0, but no failed steps so Low is valid
    assert result["health_score"] == 100.0
    assert result["risk_level"] == "Low"


def test_scoring_node_v1_pipeline_failure_gives_unknown():
    state = _base_state(failed_steps=["v1_pipeline"])
    result = scoring_node(state)
    assert result["risk_level"] == "Unknown"


def test_scoring_node_critical_step_failure_gives_unknown():
    for step in ("github_data_collector", "dependency_parser", "dependency_freshness",
                 "vulnerability_scanner"):
        state = _base_state(failed_steps=[step])
        result = scoring_node(state)
        assert result["risk_level"] == "Unknown", f"Expected Unknown for failed step: {step}"


def test_scoring_node_v1_failure_has_zero_completeness():
    result = scoring_node(_base_state(failed_steps=["v1_pipeline"]))
    assert result["data_completeness"] == 0.0
    assert result["confidence_score"] == 0.0


def test_confidence_penalty_applied_after_recovery():
    # confidence_penalty written by recovery_node must survive rescoring
    state = _base_state(failed_steps=[], confidence_penalty=0.4)
    result = scoring_node(state)
    # Base confidence with no failed steps = 0.9; penalty 0.4 → 0.5
    assert result["confidence_score"] == pytest.approx(0.5, abs=1e-9)


def test_completeness_not_reduced_by_confidence_penalty():
    # completeness_penalty was removed — data_completeness must not be affected by recovery
    state = _base_state(failed_steps=[], confidence_penalty=0.4)
    result = scoring_node(state)
    assert result["data_completeness"] == 1.0


def test_scoring_node_failed_steps_reduce_data_quality():
    state = _base_state(failed_steps=["github_data_collector", "dependency_parser"])
    result = scoring_node(state)
    assert result["data_completeness"] < 1.0
    assert result["confidence_score"] <= result["data_completeness"]


def test_scoring_node_no_failed_steps_full_confidence():
    result = scoring_node(_base_state(failed_steps=[]))
    assert result["data_completeness"] == 1.0


def test_scoring_node_breakdown_has_correct_keys():
    result = scoring_node(_base_state())
    breakdown = result["breakdown"]
    assert "activity_score" in breakdown
    assert "dependency_score" in breakdown
    assert "security_score" in breakdown


def test_scoring_node_config_version_is_forwarded():
    with patch("app.agents.scoring_node.load_scoring_config") as mock_load:
        from app.core.risk_scoring import ScoringConfig
        mock_load.return_value = ScoringConfig(
            version="v1",
            weights={"activity": 0.3, "dependency": 0.4, "security": 0.3},
            include_gap_levels=frozenset({"major"}),
        )
        scoring_node(_base_state(config_version="config/custom.yaml"))
        mock_load.assert_called_once_with("config/custom.yaml")


def test_scoring_node_appends_to_agent_trace():
    prior_trace = [{"node": "evidence", "status": "complete"}]
    result = scoring_node(_base_state(agent_trace=prior_trace))
    assert len(result["agent_trace"]) == 2
    assert result["agent_trace"][-1]["node"] == "scoring"
    assert result["agent_trace"][-1]["status"] == "complete"


def test_scoring_node_high_vulnerabilities_lowers_score():
    state = _base_state(security_metrics={"critical": 3, "high": 2, "medium": 0, "low": 0})
    result = scoring_node(state)
    # critical vulns should push score down significantly
    assert result["health_score"] < 80.0
