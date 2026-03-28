from __future__ import annotations

from dataclasses import asdict

from app.agents.state import VersionPilotState
from app.models import DependencyMetrics, RepoMetrics, SecurityMetrics
from app.pipeline import (
    compute_activity_score,
    compute_data_quality,
    compute_dependency_score,
    compute_health_score,
    compute_security_score,
)
from app.risk_scoring import load_scoring_config, risk_level_from_score

_REPO_DEFAULTS = {
    "stars": 0,
    "forks": 0,
    "last_commit_days": 0,
    "last_release_days": None,
    "open_issues": 0,
    "closed_issues": 0,
}
_DEP_DEFAULTS = {"total_dependencies": 0, "outdated_dependencies": 0}
_SEC_DEFAULTS = {"critical": 0, "high": 0, "medium": 0, "low": 0}


def scoring_node(state: VersionPilotState) -> dict:
    """Deterministic node: computes health score from evidence node metrics."""
    config_version = state.get("config_version", "config/scoring_v1.yaml")
    config = load_scoring_config(config_version)

    repo_dict = {**_REPO_DEFAULTS, **state.get("repo_metrics", {})}
    dep_dict = {**_DEP_DEFAULTS, **state.get("dependency_metrics", {})}
    sec_dict = {**_SEC_DEFAULTS, **state.get("security_metrics", {})}

    repo_metrics = RepoMetrics(**repo_dict)
    dep_metrics = DependencyMetrics(**dep_dict)
    sec_metrics = SecurityMetrics(**sec_dict)

    activity = compute_activity_score(repo_metrics)
    dependency = compute_dependency_score(dep_metrics)
    security = compute_security_score(sec_metrics)

    health_score, breakdown = compute_health_score(activity, dependency, security, config)
    risk_level = risk_level_from_score(health_score)
    data_completeness, confidence_score = compute_data_quality(state.get("failed_steps", []))

    trace = list(state.get("agent_trace", []))
    trace.append({"node": "scoring", "status": "complete", "health_score": health_score, "risk_level": risk_level})

    return {
        "health_score": health_score,
        "risk_level": risk_level,
        "breakdown": asdict(breakdown),
        "data_completeness": data_completeness,
        "confidence_score": confidence_score,
        "agent_trace": trace,
    }
