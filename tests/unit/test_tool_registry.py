"""Tests for ToolRegistry — all underlying modules are mocked."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.tools.tool_registry import ToolRegistry


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_health_report():
    """Return a minimal fake HealthReport-like object."""
    from app.core.models import (
        DependencyMetrics,
        HealthReport,
        RepoMetrics,
        ScoreBreakdown,
        SecurityMetrics,
    )
    return HealthReport(
        run_id="abc123",
        repo_url="https://github.com/test/repo",
        config_version="v1",
        health_score=75.0,
        risk_level="medium",
        breakdown=ScoreBreakdown(activity_score=80.0, dependency_score=70.0, security_score=75.0),
        repo_metrics=RepoMetrics(stars=100, forks=10, last_commit_days=5, last_release_days=30, open_issues=3, closed_issues=20),
        dependency_metrics=DependencyMetrics(total_dependencies=10, outdated_dependencies=2),
        security_metrics=SecurityMetrics(critical=0, high=1, medium=2, low=3),
        failed_steps=[],
        failed_reasons={},
        data_completeness=1.0,
        confidence_score=0.9,
    )


# ---------------------------------------------------------------------------
# run_v1_pipeline
# ---------------------------------------------------------------------------

class TestRunV1Pipeline:
    def test_happy_path(self):
        registry = ToolRegistry()
        report = _make_health_report()

        with patch("app.tools.tool_registry.run_pipeline", return_value=report):
            result = registry.run_v1_pipeline("https://github.com/test/repo")

        assert result["status"] == "ok"
        assert result["health_score"] == 75.0
        assert result["risk_level"] == "medium"
        assert result["run_id"] == "abc123"
        assert result["repo_metrics"]["stars"] == 100
        assert result["dependency_metrics"]["total_dependencies"] == 10
        assert result["security_metrics"]["critical"] == 0
        assert result["breakdown"]["activity_score"] == 80.0
        assert result["failed_steps"] == []
        assert result["data_completeness"] == 1.0
        assert result["confidence_score"] == 0.9

    def test_pipeline_error_returns_error_status(self):
        registry = ToolRegistry()

        with patch("app.tools.tool_registry.run_pipeline", side_effect=Exception("network timeout")):
            result = registry.run_v1_pipeline("https://github.com/test/repo")

        assert result["status"] == "error"
        assert "network timeout" in result["error"]

    def test_custom_config_path_is_passed_through(self):
        registry = ToolRegistry()
        report = _make_health_report()

        with patch("app.tools.tool_registry.run_pipeline", return_value=report) as mock_pipeline:
            registry.run_v1_pipeline("https://github.com/test/repo", config_path="config/custom.yaml")

        mock_pipeline.assert_called_once_with(
            repo_url="https://github.com/test/repo",
            config_path="config/custom.yaml",
        )


# ---------------------------------------------------------------------------
# scan_deprecated_apis
# ---------------------------------------------------------------------------

class TestScanDeprecatedApis:
    def _make_finding(self):
        from app.analysis.deprecated_api_scanner import DeprecatedAPIFinding
        return DeprecatedAPIFinding(
            package="requests",
            symbol="requests.get",
            file_path="/repo/main.py",
            line=10,
            replacement="httpx.get",
            severity="medium",
            note="use httpx instead",
        )

    def test_happy_path(self):
        registry = ToolRegistry()
        finding = self._make_finding()

        mock_scanner = MagicMock()
        mock_scanner.scan_repository_path.return_value = [finding]

        with patch("app.tools.tool_registry.DeprecatedAPIScanner", return_value=mock_scanner):
            result = registry.scan_deprecated_apis("/fake/repo")

        assert result["status"] == "ok"
        assert result["finding_count"] == 1
        assert result["findings"][0]["package"] == "requests"
        assert result["findings"][0]["severity"] == "medium"

    def test_no_findings(self):
        registry = ToolRegistry()
        mock_scanner = MagicMock()
        mock_scanner.scan_repository_path.return_value = []

        with patch("app.tools.tool_registry.DeprecatedAPIScanner", return_value=mock_scanner):
            result = registry.scan_deprecated_apis("/fake/repo")

        assert result["status"] == "ok"
        assert result["finding_count"] == 0
        assert result["findings"] == []

    def test_scanner_error_returns_error_status(self):
        registry = ToolRegistry()

        with patch(
            "app.tools.tool_registry.DeprecatedAPIScanner",
            side_effect=Exception("rules file not found"),
        ):
            result = registry.scan_deprecated_apis("/fake/repo")

        assert result["status"] == "error"
        assert "rules file not found" in result["error"]


# ---------------------------------------------------------------------------
# fetch_release_notes
# ---------------------------------------------------------------------------

class TestFetchReleaseNotes:
    def test_happy_path_with_notes(self):
        registry = ToolRegistry()

        with patch("app.tools.tool_registry._fetch_release_notes", return_value="## v2.0 - breaking changes"):
            result = registry.fetch_release_notes("https://github.com/test/repo")

        assert result["status"] == "ok"
        assert result["has_notes"] is True
        assert "breaking" in result["notes_text"]

    def test_no_notes_returns_empty_string(self):
        registry = ToolRegistry()

        with patch("app.tools.tool_registry._fetch_release_notes", return_value=None):
            result = registry.fetch_release_notes("https://github.com/test/repo")

        assert result["status"] == "ok"
        assert result["has_notes"] is False
        assert result["notes_text"] == ""

    def test_fetch_error_returns_error_status(self):
        registry = ToolRegistry()

        with patch(
            "app.tools.tool_registry._fetch_release_notes",
            side_effect=Exception("HTTP 500"),
        ):
            result = registry.fetch_release_notes("https://github.com/test/repo")

        assert result["status"] == "error"
        assert "HTTP 500" in result["error"]


# ---------------------------------------------------------------------------
# analyze_changelog
# ---------------------------------------------------------------------------

class TestAnalyzeChangelog:
    def _canned_analysis(self):
        return {
            "package": "requests",
            "from_version": "2.0",
            "to_version": "3.0",
            "finding_count": 2,
            "severity_counts": {"high": 1, "medium": 1, "low": 0},
            "findings": [
                {"category": "breaking_change", "text": "removed old API", "severity": "high"},
                {"category": "deprecation", "text": "deprecated method", "severity": "medium"},
            ],
        }

    def test_happy_path(self):
        registry = ToolRegistry()
        mock_analyzer = MagicMock()
        mock_analyzer.analyze_release_notes.return_value = self._canned_analysis()

        with patch("app.tools.tool_registry.ChangelogAnalyzer", return_value=mock_analyzer):
            result = registry.analyze_changelog(
                notes_text="removed old API\ndeprecated method",
                package_name="requests",
                from_version="2.0",
                to_version="3.0",
            )

        assert result["status"] == "ok"
        assert result["finding_count"] == 2
        assert result["severity_counts"]["high"] == 1

    def test_error_returns_error_status(self):
        registry = ToolRegistry()

        with patch(
            "app.tools.tool_registry.ChangelogAnalyzer",
            side_effect=Exception("parse error"),
        ):
            result = registry.analyze_changelog("some notes", "mypkg")

        assert result["status"] == "error"
        assert "parse error" in result["error"]

    def test_default_versions(self):
        registry = ToolRegistry()
        mock_analyzer = MagicMock()
        mock_analyzer.analyze_release_notes.return_value = {
            "package": "mypkg", "from_version": "unknown", "to_version": "latest",
            "finding_count": 0, "severity_counts": {}, "findings": [],
        }

        with patch("app.tools.tool_registry.ChangelogAnalyzer", return_value=mock_analyzer):
            result = registry.analyze_changelog("notes", "mypkg")

        mock_analyzer.analyze_release_notes.assert_called_once_with(
            package_name="mypkg",
            from_version="unknown",
            to_version="latest",
            notes_text="notes",
        )


# ---------------------------------------------------------------------------
# generate_migration_plan
# ---------------------------------------------------------------------------

class TestGenerateMigrationPlan:
    def _canned_plan(self):
        return {
            "total_steps": 2,
            "effort_level": "low",
            "steps": [
                {"priority": 1, "type": "deprecated_api_replacement", "package": "requests",
                 "symbol": "requests.get", "file_path": "/repo/main.py", "line": 10,
                 "action": "use httpx.get", "severity": "medium"},
                {"priority": 2, "type": "breaking_change_review",
                 "action": "Review breaking change", "severity": "high"},
            ],
        }

    def test_happy_path(self):
        registry = ToolRegistry()
        mock_planner = MagicMock()
        mock_planner.generate_plan.return_value = self._canned_plan()

        with patch("app.tools.tool_registry.MigrationPlanner", return_value=mock_planner):
            result = registry.generate_migration_plan(
                deprecated_findings=[{"package": "requests", "symbol": "requests.get",
                                      "file_path": "/repo/main.py", "line": 10,
                                      "replacement": "use httpx.get", "severity": "medium"}],
                breaking_change_analysis={"findings": [{"category": "breaking_change",
                                                         "text": "removed old API", "severity": "high"}]},
            )

        assert result["status"] == "ok"
        assert result["total_steps"] == 2
        assert result["effort_level"] == "low"

    def test_empty_inputs_returns_empty_plan(self):
        registry = ToolRegistry()
        mock_planner = MagicMock()
        mock_planner.generate_plan.return_value = {"total_steps": 0, "effort_level": "low", "steps": []}

        with patch("app.tools.tool_registry.MigrationPlanner", return_value=mock_planner):
            result = registry.generate_migration_plan([], {})

        assert result["status"] == "ok"
        assert result["total_steps"] == 0

    def test_error_returns_error_status(self):
        registry = ToolRegistry()

        with patch(
            "app.tools.tool_registry.MigrationPlanner",
            side_effect=Exception("planner crashed"),
        ):
            result = registry.generate_migration_plan([], {})

        assert result["status"] == "error"
        assert "planner crashed" in result["error"]
