import unittest
from unittest.mock import patch

from app.models import DependencySpec, RepoMetrics, SecurityMetrics
from app.pipeline import run_pipeline


class TestPipelineIntegration(unittest.TestCase):
    @patch("app.pipeline.count_outdated_dependencies")
    @patch("app.pipeline.fetch_security_metrics")
    @patch("app.pipeline.fetch_dependencies")
    @patch("app.pipeline.fetch_repo_metrics")
    def test_run_pipeline_with_mocked_sources(self, mock_repo, mock_deps, mock_sec, mock_outdated) -> None:
        mock_repo.return_value = RepoMetrics(
            stars=120,
            forks=30,
            last_commit_days=10,
            open_issues=2,
            closed_issues=20,
        )
        mock_deps.return_value = [
            DependencySpec(name="requests", version="2.31.0"),
            DependencySpec(name="fastapi", version="0.110.0"),
        ]
        mock_outdated.return_value = 1
        mock_sec.return_value = SecurityMetrics(critical=0, high=1, medium=1, low=0)

        report = run_pipeline("https://github.com/org/repo")

        self.assertEqual(report.failed_steps, [])
        self.assertEqual(report.dependency_metrics.total_dependencies, 2)
        self.assertEqual(report.security_metrics.high, 1)
        self.assertEqual(report.security_metrics.medium, 1)

        # activity = 100 - 10 - (2*2) = 86
        self.assertEqual(report.breakdown.activity_score, 86.0)
        # dependency score = 50 (1 outdated / 2 total)
        self.assertEqual(report.breakdown.dependency_score, 50.0)
        # security penalty = 20 + 8 = 28 => 72
        self.assertEqual(report.breakdown.security_score, 72.0)

        # weighted: 86*0.3 + 50*0.4 + 72*0.3 = 67.4
        self.assertEqual(report.health_score, 67.4)
        self.assertEqual(report.risk_level, "Medium")
        self.assertEqual(report.data_completeness, 1.0)
        self.assertEqual(report.confidence_score, 0.9)


if __name__ == "__main__":
    unittest.main()
