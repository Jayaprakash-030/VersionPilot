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

    def test_v1_pipeline_failure_has_zero_data_quality(self) -> None:
        self.assertEqual(compute_data_quality(["v1_pipeline"]), (0.0, 0.0))


class TestDetermineRiskLevel(unittest.TestCase):
    def test_normal_score_returns_risk_tier(self):
        from app.core.pipeline import determine_risk_level
        self.assertEqual(determine_risk_level(80.0, []), "Low")
        self.assertEqual(determine_risk_level(60.0, []), "Medium")
        self.assertEqual(determine_risk_level(40.0, []), "High")

    def test_github_failure_returns_unknown(self):
        from app.core.pipeline import determine_risk_level
        self.assertEqual(determine_risk_level(100.0, ["github_data_collector"]), "Unknown")

    def test_dependency_parser_failure_returns_unknown(self):
        from app.core.pipeline import determine_risk_level
        self.assertEqual(determine_risk_level(100.0, ["dependency_parser"]), "Unknown")

    def test_vulnerability_scanner_failure_returns_unknown(self):
        from app.core.pipeline import determine_risk_level
        self.assertEqual(determine_risk_level(100.0, ["vulnerability_scanner"]), "Unknown")

    def test_v1_pipeline_failure_returns_unknown(self):
        from app.core.pipeline import determine_risk_level
        self.assertEqual(determine_risk_level(100.0, ["v1_pipeline"]), "Unknown")

    def test_dependency_freshness_failure_returns_unknown(self):
        from app.core.pipeline import determine_risk_level
        self.assertEqual(determine_risk_level(80.0, ["dependency_freshness"]), "Unknown")


class TestRunPipelineUnknownRisk(unittest.TestCase):
    def test_github_failure_produces_unknown_risk(self):
        from unittest.mock import patch
        from app.core.pipeline import run_pipeline
        from app.core.github_client import GitHubClientError

        with patch("app.core.pipeline.fetch_repo_metrics", side_effect=GitHubClientError("fail")), \
             patch("app.core.pipeline.fetch_dependencies", return_value=[]), \
             patch("app.core.pipeline.count_outdated_dependencies", return_value=0), \
             patch("app.core.pipeline.fetch_security_metrics", return_value=__import__("app.core.models", fromlist=["SecurityMetrics"]).SecurityMetrics(0, 0, 0, 0)):
            report = run_pipeline("https://github.com/test/repo")

        self.assertEqual(report.risk_level, "Unknown")

    def test_dependency_parser_failure_produces_unknown_risk(self):
        from unittest.mock import patch
        from app.core.pipeline import run_pipeline
        from app.core.dependency_parser import DependencyParserError
        from app.core.models import RepoMetrics, SecurityMetrics

        mock_repo = RepoMetrics(stars=100, forks=10, last_commit_days=5,
                                last_release_days=10, open_issues=2, closed_issues=20)
        with patch("app.core.pipeline.fetch_repo_metrics", return_value=mock_repo), \
             patch("app.core.pipeline.fetch_dependencies", side_effect=DependencyParserError("fail")), \
             patch("app.core.pipeline.fetch_security_metrics", return_value=SecurityMetrics(0, 0, 0, 0)):
            report = run_pipeline("https://github.com/test/repo")

        self.assertEqual(report.risk_level, "Unknown")

    def test_dependency_freshness_failure_produces_unknown_risk(self):
        from unittest.mock import patch
        from app.core.pipeline import run_pipeline
        from app.core.dependency_freshness import DependencyFreshnessError
        from app.core.models import RepoMetrics, SecurityMetrics

        mock_repo = RepoMetrics(stars=100, forks=10, last_commit_days=5,
                                last_release_days=10, open_issues=2, closed_issues=20)
        with patch("app.core.pipeline.fetch_repo_metrics", return_value=mock_repo), \
             patch("app.core.pipeline.fetch_dependencies", return_value=[]), \
             patch("app.core.pipeline.count_outdated_dependencies",
                   side_effect=DependencyFreshnessError("fail")), \
             patch("app.core.pipeline.fetch_security_metrics",
                   return_value=SecurityMetrics(0, 0, 0, 0)):
            report = run_pipeline("https://github.com/test/repo")

        self.assertEqual(report.risk_level, "Unknown")


if __name__ == "__main__":
    unittest.main()
