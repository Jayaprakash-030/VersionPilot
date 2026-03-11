import unittest

from app.models import RepoMetrics
from app.pipeline import compute_activity_score, compute_dependency_score, compute_security_score


class TestPipelineActivityScore(unittest.TestCase):
    def test_activity_score_decreases_with_staleness_and_open_issues(self) -> None:
        metrics = RepoMetrics(
            stars=0,
            forks=0,
            last_commit_days=42,
            open_issues=5,
            closed_issues=0,
        )

        # 100 - 42 - (5*2) = 48
        self.assertEqual(compute_activity_score(metrics), 48.0)


class TestPipelineDependencyScore(unittest.TestCase):
    def test_dependency_score_uses_outdated_ratio(self) -> None:
        # 2 outdated out of 8 total => 25% outdated => score 75
        from app.models import DependencyMetrics

        metrics = DependencyMetrics(total_dependencies=8, outdated_dependencies=2)
        self.assertEqual(compute_dependency_score(metrics), 75.0)


class TestPipelineSecurityScore(unittest.TestCase):
    def test_security_score_applies_severity_penalties(self) -> None:
        from app.models import SecurityMetrics

        metrics = SecurityMetrics(critical=1, high=1, medium=1, low=1)
        # 100 - (40 + 20 + 8 + 2) = 30
        self.assertEqual(compute_security_score(metrics), 30.0)


if __name__ == "__main__":
    unittest.main()
