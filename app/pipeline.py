from __future__ import annotations

import hashlib

from .dependency_freshness import DependencyFreshnessError, count_outdated_dependencies
from .dependency_parser import DependencyParserError, fetch_dependencies
from .github_client import GitHubClientError, fetch_repo_metrics
from .models import DependencyMetrics, HealthReport, RepoMetrics, SecurityMetrics
from .risk_scoring import compute_health_score, load_scoring_config, risk_level_from_score
from .vulnerability_scanner import VulnerabilityScannerError, fetch_security_metrics


def build_run_id(repo_url: str, config_version: str) -> str:
    payload = f"{repo_url}|{config_version}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()[:16]


def compute_activity_score(repo_metrics: RepoMetrics) -> float:
    # Simple deterministic baseline: stale commits/releases and open issues reduce activity score.
    recency_penalty = float(min(repo_metrics.last_commit_days, 100))
    release_penalty = 0.0
    if repo_metrics.last_release_days is not None:
        release_penalty = float(min(repo_metrics.last_release_days, 120)) * 0.2
    open_issue_penalty = float(min(repo_metrics.open_issues * 2, 40))
    resolution_bonus = 0.0
    total_issues = repo_metrics.open_issues + repo_metrics.closed_issues
    if total_issues > 0:
        resolution_rate = repo_metrics.closed_issues / total_issues
        resolution_bonus = round(resolution_rate * 15.0, 2)

    score = 100.0 - recency_penalty - release_penalty - open_issue_penalty + resolution_bonus
    return max(0.0, min(100.0, round(score, 2)))


def compute_dependency_score(dependency_metrics: DependencyMetrics) -> float:
    if dependency_metrics.total_dependencies <= 0:
        return 100.0

    outdated_ratio = dependency_metrics.outdated_dependencies / dependency_metrics.total_dependencies
    score = 100.0 - (outdated_ratio * 100.0)
    return max(0.0, min(100.0, round(score, 2)))


def compute_security_score(security_metrics: SecurityMetrics) -> float:
    # Weighted penalty by severity; clamp to [0, 100].
    penalty = (
        security_metrics.critical * 40
        + security_metrics.high * 20
        + security_metrics.medium * 8
        + security_metrics.low * 2
    )
    score = 100.0 - float(penalty)
    return max(0.0, min(100.0, round(score, 2)))


def compute_data_quality(failed_steps: list[str], total_steps: int = 3) -> tuple[float, float]:
    if total_steps <= 0:
        raise ValueError("total_steps must be > 0")

    failed_count = min(len(set(failed_steps)), total_steps)
    data_completeness = round((total_steps - failed_count) / total_steps, 2)

    # Confidence is slightly conservative vs completeness.
    confidence_score = round(max(0.0, min(1.0, data_completeness - 0.1)), 2)
    return data_completeness, confidence_score


def run_pipeline(repo_url: str, config_path: str = "config/scoring_v1.yaml") -> HealthReport:
    config = load_scoring_config(config_path)
    failed_steps = []
    failed_reasons: dict[str, str] = {}

    try:
        repo_metrics = fetch_repo_metrics(repo_url)
    except GitHubClientError as exc:
        failed_steps.append("github_data_collector")
        failed_reasons["github_data_collector"] = str(exc)
        repo_metrics = RepoMetrics(
            stars=0,
            forks=0,
            last_commit_days=0,
            last_release_days=None,
            open_issues=0,
            closed_issues=0,
        )

    try:
        dependencies = fetch_dependencies(repo_url)
        try:
            outdated_dependencies = count_outdated_dependencies(
                dependencies,
                include_gap_levels=config.include_gap_levels,
            )
        except DependencyFreshnessError as exc:
            failed_steps.append("dependency_freshness")
            failed_reasons["dependency_freshness"] = str(exc)
            outdated_dependencies = 0

        dependency_metrics = DependencyMetrics(
            total_dependencies=len(dependencies),
            outdated_dependencies=outdated_dependencies,
        )
    except DependencyParserError as exc:
        failed_steps.append("dependency_parser")
        failed_reasons["dependency_parser"] = str(exc)
        dependencies = []
        dependency_metrics = DependencyMetrics(total_dependencies=0, outdated_dependencies=0)

    try:
        security_metrics = fetch_security_metrics(dependencies)
    except VulnerabilityScannerError as exc:
        failed_steps.append("vulnerability_scanner")
        failed_reasons["vulnerability_scanner"] = str(exc)
        security_metrics = SecurityMetrics(critical=0, high=0, medium=0, low=0)

    activity_score = compute_activity_score(repo_metrics)
    dependency_score = compute_dependency_score(dependency_metrics)
    security_score = compute_security_score(security_metrics)

    health_score, breakdown = compute_health_score(
        activity_score=activity_score,
        dependency_score=dependency_score,
        security_score=security_score,
        config=config,
    )
    data_completeness, confidence_score = compute_data_quality(failed_steps)

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
        security_metrics=security_metrics,
        failed_steps=failed_steps,
        failed_reasons=failed_reasons,
        data_completeness=data_completeness,
        confidence_score=confidence_score,
    )
