import unittest

from app.core.models import RepoMetrics
from app.core.pipeline import compute_activity_score, compute_data_quality, compute_dependency_score, compute_security_score


class TestPipelineActivityScore(unittest.TestCase):
    def test_activity_score_decreases_with_staleness_and_open_issues(self) -> None:
        metrics = RepoMetrics(
            stars=0,
            forks=0,
            last_commit_days=42,
            last_release_days=None,
            open_issues=5,
            closed_issues=0,
        )

        # 100 - 42 - (5*2) = 48
        self.assertEqual(compute_activity_score(metrics), 48.0)

    def test_activity_score_adds_issue_resolution_bonus(self) -> None:
        metrics = RepoMetrics(
            stars=0,
            forks=0,
            last_commit_days=10,
            last_release_days=None,
            open_issues=5,
            closed_issues=15,
        )

        # Base: 100 - 10 - (5*2) = 80; resolution bonus: (15/20)*15 = 11.25 -> 91.25
        self.assertEqual(compute_activity_score(metrics), 91.25)


class TestPipelineDependencyScore(unittest.TestCase):
    def test_dependency_score_uses_outdated_ratio(self) -> None:
        # 2 outdated out of 8 total => 25% outdated => score 75
        from app.core.models import DependencyMetrics

        metrics = DependencyMetrics(total_dependencies=8, outdated_dependencies=2)
        self.assertEqual(compute_dependency_score(metrics), 75.0)


class TestPipelineSecurityScore(unittest.TestCase):
    def test_security_score_applies_severity_penalties(self) -> None:
        from app.core.models import SecurityMetrics

        metrics = SecurityMetrics(critical=1, high=1, medium=1, low=1)
        # 100 - (40 + 20 + 8 + 2) = 30
        self.assertEqual(compute_security_score(metrics), 30.0)


class TestPipelineDataQuality(unittest.TestCase):
    def test_data_quality_based_on_failed_steps(self) -> None:
        completeness, confidence = compute_data_quality(["github_data_collector"])
        self.assertEqual(completeness, 0.65)
        self.assertEqual(confidence, 0.55)


if __name__ == "__main__":
    unittest.main()
