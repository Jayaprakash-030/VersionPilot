from unittest.mock import patch

import pytest

from app.agents.report_node import report_node
from app.agents.scoring_node import scoring_node
from app.agents.state import create_initial_state
from app.core.models import DependencyMetrics, RepoMetrics, SecurityMetrics
from app.core.pipeline import (
    compute_activity_score,
    compute_data_quality,
    compute_dependency_score,
    compute_security_score,
    determine_risk_level,
)
from app.core.risk_scoring import compute_health_score, load_scoring_config


def test_adding_critical_vulnerability_does_not_improve_health_score():
    config = load_scoring_config("config/scoring_v1.yaml")
    clean_security = SecurityMetrics(critical=0, high=0, medium=0, low=0)
    critical_security = SecurityMetrics(critical=1, high=0, medium=0, low=0)

    clean_security_score = compute_security_score(clean_security)
    critical_security_score = compute_security_score(critical_security)

    clean_health_score, _ = compute_health_score(
        activity_score=80.0,
        dependency_score=80.0,
        security_score=clean_security_score,
        config=config,
    )
    critical_health_score, _ = compute_health_score(
        activity_score=80.0,
        dependency_score=80.0,
        security_score=critical_security_score,
        config=config,
    )

    assert critical_security_score <= clean_security_score
    assert critical_health_score <= clean_health_score


@pytest.mark.parametrize("severity", ["high", "medium", "low"])
def test_adding_noncritical_vulnerability_does_not_improve_health_score(severity):
    config = load_scoring_config("config/scoring_v1.yaml")
    clean_security = SecurityMetrics(critical=0, high=0, medium=0, low=0)
    vulnerability_counts = {"critical": 0, "high": 0, "medium": 0, "low": 0}
    vulnerability_counts[severity] = 1
    degraded_security = SecurityMetrics(**vulnerability_counts)

    clean_security_score = compute_security_score(clean_security)
    degraded_security_score = compute_security_score(degraded_security)
    clean_health_score, _ = compute_health_score(
        activity_score=80.0,
        dependency_score=80.0,
        security_score=clean_security_score,
        config=config,
    )
    degraded_health_score, _ = compute_health_score(
        activity_score=80.0,
        dependency_score=80.0,
        security_score=degraded_security_score,
        config=config,
    )

    assert degraded_security_score <= clean_security_score
    assert degraded_health_score <= clean_health_score


def test_increasing_outdated_dependencies_does_not_improve_health_score():
    config = load_scoring_config("config/scoring_v1.yaml")
    fresher = DependencyMetrics(total_dependencies=10, outdated_dependencies=1)
    more_outdated = DependencyMetrics(total_dependencies=10, outdated_dependencies=4)

    fresher_dependency_score = compute_dependency_score(fresher)
    more_outdated_dependency_score = compute_dependency_score(more_outdated)

    fresher_health_score, _ = compute_health_score(
        activity_score=80.0,
        dependency_score=fresher_dependency_score,
        security_score=80.0,
        config=config,
    )
    more_outdated_health_score, _ = compute_health_score(
        activity_score=80.0,
        dependency_score=more_outdated_dependency_score,
        security_score=80.0,
        config=config,
    )

    assert more_outdated_dependency_score <= fresher_dependency_score
    assert more_outdated_health_score <= fresher_health_score


def test_increasing_commit_age_does_not_improve_health_score():
    config = load_scoring_config("config/scoring_v1.yaml")
    recent = RepoMetrics(
        stars=100,
        forks=10,
        last_commit_days=5,
        last_release_days=20,
        open_issues=5,
        closed_issues=50,
    )
    stale = RepoMetrics(
        stars=100,
        forks=10,
        last_commit_days=60,
        last_release_days=20,
        open_issues=5,
        closed_issues=50,
    )

    recent_activity_score = compute_activity_score(recent)
    stale_activity_score = compute_activity_score(stale)

    recent_health_score, _ = compute_health_score(
        activity_score=recent_activity_score,
        dependency_score=80.0,
        security_score=80.0,
        config=config,
    )
    stale_health_score, _ = compute_health_score(
        activity_score=stale_activity_score,
        dependency_score=80.0,
        security_score=80.0,
        config=config,
    )

    assert stale_activity_score <= recent_activity_score
    assert stale_health_score <= recent_health_score


def test_increasing_release_age_does_not_improve_health_score():
    config = load_scoring_config("config/scoring_v1.yaml")
    recent_release = RepoMetrics(
        stars=100,
        forks=10,
        last_commit_days=5,
        last_release_days=20,
        open_issues=5,
        closed_issues=50,
    )
    stale_release = RepoMetrics(
        stars=100,
        forks=10,
        last_commit_days=5,
        last_release_days=100,
        open_issues=5,
        closed_issues=50,
    )

    recent_activity_score = compute_activity_score(recent_release)
    stale_activity_score = compute_activity_score(stale_release)
    recent_health_score, _ = compute_health_score(
        activity_score=recent_activity_score,
        dependency_score=80.0,
        security_score=80.0,
        config=config,
    )
    stale_health_score, _ = compute_health_score(
        activity_score=stale_activity_score,
        dependency_score=80.0,
        security_score=80.0,
        config=config,
    )

    assert stale_activity_score <= recent_activity_score
    assert stale_health_score <= recent_health_score


def test_increasing_open_issues_does_not_improve_health_score():
    config = load_scoring_config("config/scoring_v1.yaml")
    fewer_open_issues = RepoMetrics(
        stars=100,
        forks=10,
        last_commit_days=5,
        last_release_days=20,
        open_issues=5,
        closed_issues=50,
    )
    more_open_issues = RepoMetrics(
        stars=100,
        forks=10,
        last_commit_days=5,
        last_release_days=20,
        open_issues=20,
        closed_issues=50,
    )

    fewer_issues_activity_score = compute_activity_score(fewer_open_issues)
    more_issues_activity_score = compute_activity_score(more_open_issues)

    fewer_issues_health_score, _ = compute_health_score(
        activity_score=fewer_issues_activity_score,
        dependency_score=80.0,
        security_score=80.0,
        config=config,
    )
    more_issues_health_score, _ = compute_health_score(
        activity_score=more_issues_activity_score,
        dependency_score=80.0,
        security_score=80.0,
        config=config,
    )

    assert more_issues_activity_score <= fewer_issues_activity_score
    assert more_issues_health_score <= fewer_issues_health_score


def test_healthier_state_on_every_dimension_has_higher_health_score():
    config = load_scoring_config("config/scoring_v1.yaml")
    healthier_repo = RepoMetrics(
        stars=100,
        forks=10,
        last_commit_days=5,
        last_release_days=20,
        open_issues=5,
        closed_issues=50,
    )
    less_healthy_repo = RepoMetrics(
        stars=100,
        forks=10,
        last_commit_days=40,
        last_release_days=90,
        open_issues=20,
        closed_issues=50,
    )
    healthier_dependencies = DependencyMetrics(
        total_dependencies=10,
        outdated_dependencies=1,
    )
    less_healthy_dependencies = DependencyMetrics(
        total_dependencies=10,
        outdated_dependencies=5,
    )
    healthier_security = SecurityMetrics(critical=0, high=0, medium=1, low=0)
    less_healthy_security = SecurityMetrics(critical=1, high=1, medium=1, low=0)

    healthier_components = (
        compute_activity_score(healthier_repo),
        compute_dependency_score(healthier_dependencies),
        compute_security_score(healthier_security),
    )
    less_healthy_components = (
        compute_activity_score(less_healthy_repo),
        compute_dependency_score(less_healthy_dependencies),
        compute_security_score(less_healthy_security),
    )

    healthier_score, _ = compute_health_score(*healthier_components, config=config)
    less_healthy_score, _ = compute_health_score(
        *less_healthy_components,
        config=config,
    )

    assert all(
        healthier >= less_healthy
        for healthier, less_healthy in zip(
            healthier_components,
            less_healthy_components,
            strict=True,
        )
    )
    assert healthier_score > less_healthy_score


def test_identical_evidence_produces_identical_scoring_result():
    config = load_scoring_config("config/scoring_v1.yaml")
    repo_metrics = RepoMetrics(
        stars=100,
        forks=10,
        last_commit_days=12,
        last_release_days=45,
        open_issues=8,
        closed_issues=40,
    )
    dependency_metrics = DependencyMetrics(
        total_dependencies=12,
        outdated_dependencies=3,
    )
    security_metrics = SecurityMetrics(critical=0, high=1, medium=2, low=1)
    failed_steps = ["dependency_freshness"]

    def score_frozen_evidence():
        health_score, breakdown = compute_health_score(
            activity_score=compute_activity_score(repo_metrics),
            dependency_score=compute_dependency_score(dependency_metrics),
            security_score=compute_security_score(security_metrics),
            config=config,
        )
        completeness, confidence = compute_data_quality(failed_steps)
        return {
            "health_score": health_score,
            "risk_level": determine_risk_level(health_score, failed_steps),
            "breakdown": breakdown,
            "data_completeness": completeness,
            "confidence_score": confidence,
        }

    assert score_frozen_evidence() == score_frozen_evidence()


def test_critical_evidence_failure_produces_unknown_not_low_risk():
    health_score = 95.0

    risk_level = determine_risk_level(
        health_score,
        failed_steps=["vulnerability_scanner"],
    )

    assert risk_level == "Unknown"
    assert risk_level != "Low"


def test_valid_zero_dependency_repository_is_not_treated_as_failure():
    dependency_metrics = DependencyMetrics(
        total_dependencies=0,
        outdated_dependencies=0,
    )

    dependency_score = compute_dependency_score(dependency_metrics)
    risk_level = determine_risk_level(90.0, failed_steps=[])

    assert dependency_score == 100.0
    assert risk_level == "Low"


def test_confidence_penalty_does_not_reduce_evidence_completeness():
    state = {
        "config_version": "config/scoring_v1.yaml",
        "repo_metrics": {
            "stars": 100,
            "forks": 10,
            "last_commit_days": 5,
            "last_release_days": 20,
            "open_issues": 5,
            "closed_issues": 50,
        },
        "dependency_metrics": {
            "total_dependencies": 10,
            "outdated_dependencies": 1,
        },
        "security_metrics": {
            "critical": 0,
            "high": 0,
            "medium": 1,
            "low": 0,
        },
        "failed_steps": [],
        "agent_trace": [],
    }

    baseline = scoring_node({**state, "confidence_penalty": 0.0})
    penalized = scoring_node({**state, "confidence_penalty": 0.3})

    assert penalized["confidence_score"] < baseline["confidence_score"]
    assert penalized["data_completeness"] == baseline["data_completeness"]
    assert penalized["health_score"] == baseline["health_score"]


def test_adding_failed_collection_step_reduces_confidence():
    baseline_completeness, baseline_confidence = compute_data_quality([])
    failed_completeness, failed_confidence = compute_data_quality(
        ["github_data_collector"]
    )

    assert failed_completeness < baseline_completeness
    assert failed_confidence < baseline_confidence


@patch("app.agents.report_node.LLMClient.is_available", return_value=False)
def test_unresolved_critic_failure_publishes_unverified_not_low_risk(_mock):
    state = create_initial_state("https://github.com/example/repo")
    state.update(
        {
            "health_score": 95.0,
            "risk_level": "Low",
            "critic_passed": False,
            "critic_feedback": "Report could not be verified",
            "retry_count": 2,
            "data_completeness": 1.0,
            "confidence_score": 0.5,
        }
    )

    report = report_node(state)["final_report"]

    assert report["risk_level"] == "Unverified"
    assert report["risk_level"] != "Low"
    assert report["critic"]["passed"] is False
