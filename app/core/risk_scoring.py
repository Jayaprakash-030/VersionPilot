from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, FrozenSet

from .models import ScoreBreakdown


@dataclass(frozen=True)
class ScoringConfig:
    version: str
    weights: Dict[str, float]
    include_gap_levels: FrozenSet[str]


def _parse_simple_yaml(path: Path) -> ScoringConfig:
    version = ""
    weights: Dict[str, float] = {}
    include_gap_levels: set[str] = {"major"}
    in_weights = False
    in_freshness_policy = False

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.rstrip()
        if not line or line.strip().startswith("#"):
            continue

        if line.startswith("version:"):
            version = line.split(":", 1)[1].strip()
            continue

        if line.startswith("weights:"):
            in_weights = True
            in_freshness_policy = False
            continue

        if line.startswith("freshness_policy:"):
            in_freshness_policy = True
            in_weights = False
            continue

        if in_weights and line.startswith("  ") and ":" in line:
            key, value = line.strip().split(":", 1)
            weights[key.strip()] = float(value.strip())
            continue

        if in_freshness_policy and line.startswith("  include_gap_levels:"):
            _, raw_value = line.strip().split(":", 1)
            raw_value = raw_value.strip()
            try:
                parsed = ast.literal_eval(raw_value)
            except (ValueError, SyntaxError) as exc:
                raise ValueError("freshness_policy.include_gap_levels must be a list literal") from exc

            if not isinstance(parsed, list) or not all(isinstance(v, str) for v in parsed):
                raise ValueError("freshness_policy.include_gap_levels must be a list of strings")

            include_gap_levels = {v.strip().lower() for v in parsed if v.strip()}

    if not version:
        raise ValueError("Missing 'version' in scoring config")

    required = {"activity", "dependency", "security"}
    if set(weights.keys()) != required:
        raise ValueError("Weights must include exactly: activity, dependency, security")

    total = sum(weights.values())
    if abs(total - 1.0) > 1e-9:
        raise ValueError("Weights must sum to 1.0")

    allowed_levels = {"major", "minor", "patch"}
    if not include_gap_levels.issubset(allowed_levels):
        raise ValueError("include_gap_levels must be subset of: major, minor, patch")

    return ScoringConfig(
        version=version,
        weights=weights,
        include_gap_levels=frozenset(include_gap_levels),
    )


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
