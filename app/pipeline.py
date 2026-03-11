from __future__ import annotations

import hashlib

from .dependency_parser import DependencyParserError, fetch_dependency_metrics
from .github_client import GitHubClientError, fetch_repo_metrics
from .models import DependencyMetrics, HealthReport, RepoMetrics, SecurityMetrics
from .risk_scoring import compute_health_score, load_scoring_config, risk_level_from_score


def build_run_id(repo_url: str, config_version: str) -> str:
    payload = f"{repo_url}|{config_version}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()[:16]


def compute_activity_score(repo_metrics: RepoMetrics) -> float:
    # Simple deterministic baseline: stale repos and many open issues reduce activity score.
    recency_penalty = float(min(repo_metrics.last_commit_days, 100))
    open_issue_penalty = float(min(repo_metrics.open_issues * 2, 40))
    score = 100.0 - recency_penalty - open_issue_penalty
    return max(0.0, min(100.0, round(score, 2)))


def compute_dependency_score(dependency_metrics: DependencyMetrics) -> float:
    if dependency_metrics.total_dependencies <= 0:
        return 100.0

    outdated_ratio = dependency_metrics.outdated_dependencies / dependency_metrics.total_dependencies
    score = 100.0 - (outdated_ratio * 100.0)
    return max(0.0, min(100.0, round(score, 2)))


def _mock_security_score() -> float:
    # Keep security mocked in this step.
    return 66.0


def run_pipeline(repo_url: str, config_path: str = "config/scoring_v1.yaml") -> HealthReport:
    config = load_scoring_config(config_path)
    failed_steps = []

    try:
        repo_metrics = fetch_repo_metrics(repo_url)
    except GitHubClientError:
        failed_steps.append("github_data_collector")
        repo_metrics = RepoMetrics(
            stars=0,
            forks=0,
            last_commit_days=0,
            open_issues=0,
            closed_issues=0,
        )

    try:
        dependency_metrics = fetch_dependency_metrics(repo_url)
    except DependencyParserError:
        failed_steps.append("dependency_parser")
        dependency_metrics = DependencyMetrics(total_dependencies=0, outdated_dependencies=0)

    activity_score = compute_activity_score(repo_metrics)
    dependency_score = compute_dependency_score(dependency_metrics)
    security_score = _mock_security_score()

    health_score, breakdown = compute_health_score(
        activity_score=activity_score,
        dependency_score=dependency_score,
        security_score=security_score,
        config=config,
    )

    run_id = build_run_id(repo_url=repo_url, config_version=config.version)

    return HealthReport(
        run_id=run_id,
        repo_url=repo_url,
        config_version=config.version,
        health_score=health_score,
        risk_level=risk_level_from_score(health_score),
        breakdown=breakdown,
        repo_metrics=repo_metrics,
        dependency_metrics=dependency_metrics,
        security_metrics=SecurityMetrics(critical=0, high=0, medium=0, low=0),
        failed_steps=failed_steps,
        data_completeness=0.8 if failed_steps else 1.0,
        confidence_score=0.5 if failed_steps else 0.6,
    )
