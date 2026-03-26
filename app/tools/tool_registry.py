from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.changelog_analyzer import ChangelogAnalyzer
from app.deprecated_api_scanner import DeprecatedAPIScanner
from app.migration_planner import MigrationPlanner
from app.pipeline import run_pipeline
from app.release_notes_fetcher import fetch_release_notes as _fetch_release_notes


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class ToolRegistry:
    """Wraps existing VersionPilot modules as callable tools.

    Every method returns either::

        {"status": "ok", ...data}

    or on failure::

        {"status": "error", "error": "<message>"}

    This means callers never crash — they just record failures.
    """

    # ------------------------------------------------------------------
    # V1 pipeline
    # ------------------------------------------------------------------

    def run_v1_pipeline(self, repo_url: str, config_path: str = "config/scoring_v1.yaml") -> dict[str, Any]:
        """Run the full V1 pipeline and return the HealthReport as a dict."""
        try:
            report = run_pipeline(repo_url=repo_url, config_path=config_path)
            return {
                "status": "ok",
                "run_id": report.run_id,
                "health_score": report.health_score,
                "risk_level": report.risk_level,
                "repo_metrics": {
                    "stars": report.repo_metrics.stars,
                    "forks": report.repo_metrics.forks,
                    "last_commit_days": report.repo_metrics.last_commit_days,
                    "last_release_days": report.repo_metrics.last_release_days,
                    "open_issues": report.repo_metrics.open_issues,
                    "closed_issues": report.repo_metrics.closed_issues,
                },
                "dependency_metrics": {
                    "total_dependencies": report.dependency_metrics.total_dependencies,
                    "outdated_dependencies": report.dependency_metrics.outdated_dependencies,
                },
                "security_metrics": {
                    "critical": report.security_metrics.critical,
                    "high": report.security_metrics.high,
                    "medium": report.security_metrics.medium,
                    "low": report.security_metrics.low,
                },
                "breakdown": {
                    "activity_score": report.breakdown.activity_score,
                    "dependency_score": report.breakdown.dependency_score,
                    "security_score": report.breakdown.security_score,
                },
                "failed_steps": list(report.failed_steps),
                "data_completeness": report.data_completeness,
                "confidence_score": report.confidence_score,
            }
        except Exception as exc:
            return {"status": "error", "error": str(exc)}

    # ------------------------------------------------------------------
    # Deprecated API scanner
    # ------------------------------------------------------------------

    def scan_deprecated_apis(
        self,
        repo_path: str,
        rules_path: str = "data/deprecation_rules.json",
        rules: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Scan for deprecated API usage in a local repo clone.

        If ``rules`` is provided it takes precedence over ``rules_path``.
        """
        try:
            scanner = DeprecatedAPIScanner(rules_path=rules_path, rules=rules)
            findings = scanner.scan_repository_path(repo_path)
            return {
                "status": "ok",
                "finding_count": len(findings),
                "findings": [f.to_dict() for f in findings],
            }
        except Exception as exc:
            return {"status": "error", "error": str(exc)}

    # ------------------------------------------------------------------
    # Release notes fetcher
    # ------------------------------------------------------------------

    def fetch_release_notes(self, repo_url: str) -> dict[str, Any]:
        """Fetch the latest release notes from GitHub for a repo URL."""
        try:
            notes_text = _fetch_release_notes(repo_url)
            return {
                "status": "ok",
                "notes_text": notes_text or "",
                "has_notes": notes_text is not None,
            }
        except Exception as exc:
            return {"status": "error", "error": str(exc)}

    # ------------------------------------------------------------------
    # Changelog analyzer
    # ------------------------------------------------------------------

    def analyze_changelog(
        self,
        notes_text: str,
        package_name: str,
        from_version: str = "unknown",
        to_version: str = "latest",
    ) -> dict[str, Any]:
        """Analyze changelog/release notes text for breaking changes and deprecations."""
        try:
            analyzer = ChangelogAnalyzer()
            result = analyzer.analyze_release_notes(
                package_name=package_name,
                from_version=from_version,
                to_version=to_version,
                notes_text=notes_text,
            )
            return {"status": "ok", **result}
        except Exception as exc:
            return {"status": "error", "error": str(exc)}

    # ------------------------------------------------------------------
    # Migration planner
    # ------------------------------------------------------------------

    def generate_migration_plan(
        self,
        deprecated_findings: list[dict[str, Any]],
        breaking_change_analysis: dict[str, Any],
    ) -> dict[str, Any]:
        """Generate ordered migration steps from deprecated API findings and breaking changes."""
        try:
            planner = MigrationPlanner()
            result = planner.generate_plan(
                deprecated_findings=deprecated_findings,
                breaking_change_analysis=breaking_change_analysis,
            )
            return {"status": "ok", **result}
        except Exception as exc:
            return {"status": "error", "error": str(exc)}
