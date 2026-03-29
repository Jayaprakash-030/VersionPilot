from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict, List


@dataclass(frozen=True)
class RepoMetrics:
    stars: int
    forks: int
    last_commit_days: int
    last_release_days: int | None
    open_issues: int
    closed_issues: int


@dataclass(frozen=True)
class DependencyMetrics:
    total_dependencies: int
    outdated_dependencies: int


@dataclass(frozen=True)
class DependencySpec:
    name: str
    version: str | None = None


@dataclass(frozen=True)
class SecurityMetrics:
    critical: int
    high: int
    medium: int
    low: int


@dataclass(frozen=True)
class ScoreBreakdown:
    activity_score: float
    dependency_score: float
    security_score: float


@dataclass(frozen=True)
class HealthReport:
    run_id: str
    repo_url: str
    config_version: str
    health_score: float
    risk_level: str
    breakdown: ScoreBreakdown
    repo_metrics: RepoMetrics
    dependency_metrics: DependencyMetrics
    security_metrics: SecurityMetrics
    failed_steps: List[str]
    failed_reasons: Dict[str, str]
    data_completeness: float
    confidence_score: float

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
