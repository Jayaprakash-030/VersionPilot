from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict

from .models import ScoreBreakdown


@dataclass(frozen=True)
class ScoringConfig:
    version: str
    weights: Dict[str, float]


def _parse_simple_yaml(path: Path) -> ScoringConfig:
    version = ""
    weights: Dict[str, float] = {}
    in_weights = False

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.rstrip()
        if not line or line.strip().startswith("#"):
            continue

        if line.startswith("version:"):
            version = line.split(":", 1)[1].strip()
            continue

        if line.startswith("weights:"):
            in_weights = True
            continue

        if in_weights and line.startswith("  ") and ":" in line:
            key, value = line.strip().split(":", 1)
            weights[key.strip()] = float(value.strip())

    if not version:
        raise ValueError("Missing 'version' in scoring config")

    required = {"activity", "dependency", "security"}
    if set(weights.keys()) != required:
        raise ValueError("Weights must include exactly: activity, dependency, security")

    total = sum(weights.values())
    if abs(total - 1.0) > 1e-9:
        raise ValueError("Weights must sum to 1.0")

    return ScoringConfig(version=version, weights=weights)


def load_scoring_config(config_path: str = "config/scoring_v1.yaml") -> ScoringConfig:
    return _parse_simple_yaml(Path(config_path))


def compute_health_score(
    activity_score: float,
    dependency_score: float,
    security_score: float,
    config: ScoringConfig,
) -> tuple[float, ScoreBreakdown]:
    for value in (activity_score, dependency_score, security_score):
        if not 0 <= value <= 100:
            raise ValueError("All component scores must be in [0, 100]")

    weights = config.weights
    health_score = (
        activity_score * weights["activity"]
        + dependency_score * weights["dependency"]
        + security_score * weights["security"]
    )

    return round(health_score, 2), ScoreBreakdown(
        activity_score=activity_score,
        dependency_score=dependency_score,
        security_score=security_score,
    )


def risk_level_from_score(score: float) -> str:
    if score >= 75:
        return "Low"
    if score >= 50:
        return "Medium"
    return "High"
