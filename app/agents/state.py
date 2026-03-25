import uuid
from typing import NotRequired, TypedDict


class VersionPilotState(TypedDict):
    # Input
    repo_url: str
    repo_path: str
    config_version: str
    run_id: str

    # V1 signals
    repo_metrics: dict
    dependency_metrics: dict
    security_metrics: dict
    health_score: float
    risk_level: str
    breakdown: dict

    # Phase 2 signals
    deprecated_findings: list[dict]
    breaking_change_analysis: dict
    migration_plan: dict

    # Agent reasoning
    agent_plan: dict
    agent_trace: list[dict]

    # Critic
    critic_feedback: str
    critic_passed: bool
    retry_count: int

    # Production / data quality
    provenance: list[dict]
    data_completeness: float
    confidence_score: float
    failed_steps: list[str]

    # Output
    final_report: NotRequired[dict]


def create_initial_state(
    repo_url: str,
    repo_path: str = "",
    config_version: str = "config/scoring_v1.yaml",
) -> VersionPilotState:
    return VersionPilotState(
        repo_url=repo_url,
        repo_path=repo_path,
        config_version=config_version,
        run_id=str(uuid.uuid4()),
        repo_metrics={},
        dependency_metrics={},
        security_metrics={},
        health_score=0.0,
        risk_level="",
        breakdown={},
        deprecated_findings=[],
        breaking_change_analysis={},
        migration_plan={},
        agent_plan={},
        agent_trace=[],
        critic_feedback="",
        critic_passed=False,
        retry_count=0,
        provenance=[],
        data_completeness=0.0,
        confidence_score=0.0,
        failed_steps=[],
        final_report={},
    )
