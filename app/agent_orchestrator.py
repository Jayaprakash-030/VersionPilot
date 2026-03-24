from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from .changelog_analyzer import ChangelogAnalyzer
from .deprecated_api_scanner import DeprecatedAPIScanner, DeprecatedAPIScannerError
from .pipeline import run_pipeline


class AgentOrchestrator:
    """Minimal V2 orchestrator skeleton that wraps existing V1 pipeline tools."""

    def _build_deprecated_risk_summary(self, findings: list[dict[str, Any]]) -> dict[str, Any]:
        severity_counts = {"critical": 0, "high": 0, "medium": 0, "low": 0, "unknown": 0}
        symbol_counts: dict[tuple[str, str], int] = {}

        for finding in findings:
            severity = str(finding.get("severity", "unknown")).lower()
            if severity not in severity_counts:
                severity = "unknown"
            severity_counts[severity] += 1

            package = str(finding.get("package", "unknown"))
            symbol = str(finding.get("symbol", "unknown"))
            key = (package, symbol)
            symbol_counts[key] = symbol_counts.get(key, 0) + 1

        sorted_symbols = sorted(symbol_counts.items(), key=lambda item: (-item[1], item[0][1], item[0][0]))
        top_symbols = [
            {"package": package, "symbol": symbol, "count": count}
            for (package, symbol), count in sorted_symbols[:5]
        ]

        return {
            "total_findings": len(findings),
            "severity_counts": severity_counts,
            "top_symbols": top_symbols,
        }

    def analyze_repository(
        self,
        repo_url: str,
        config_path: str = "config/scoring_v1.yaml",
        repo_path: str | None = None,
        notes_file: str | None = None,
    ) -> Dict[str, Any]:
        agent_trace: List[Dict[str, str]] = [
            {"agent": "orchestrator", "action": "plan_analysis"},
            {"agent": "repo_agent", "action": "collect_repo_signals"},
            {"agent": "dependency_agent", "action": "collect_dependency_signals"},
            {"agent": "security_agent", "action": "collect_security_signals"},
            {"agent": "scoring_agent", "action": "compute_health_score"},
            {"agent": "deprecation_agent", "action": "scan_deprecated_api_usage"},
            {"agent": "changelog_agent", "action": "analyze_breaking_changes"},
            {"agent": "report_agent", "action": "assemble_report"},
        ]

        report = run_pipeline(repo_url=repo_url, config_path=config_path)
        deprecated_findings: list[dict[str, Any]] = []
        deprecation_scan_status = "skipped"
        deprecation_scan_error = ""
        changelog_analysis_status = "skipped"
        changelog_analysis_error = ""
        breaking_change_analysis: dict[str, Any] = {
            "finding_count": 0,
            "severity_counts": {"high": 0, "medium": 0, "low": 0},
            "findings": [],
        }

        if repo_path:
            deprecation_scan_status = "ok"
            try:
                scanner = DeprecatedAPIScanner("data/deprecation_rules.json")
                findings = scanner.scan_repository_path(repo_path)
                deprecated_findings = [finding.to_dict() for finding in findings]
            except DeprecatedAPIScannerError as exc:
                deprecation_scan_status = "error"
                deprecation_scan_error = str(exc)
            except OSError as exc:
                deprecation_scan_status = "error"
                deprecation_scan_error = str(exc)
        elif Path(".").exists():
            # Explicitly mark why we skipped when repo path was not provided.
            deprecation_scan_status = "skipped_no_repo_path"

        deprecated_risk_summary = self._build_deprecated_risk_summary(deprecated_findings)

        if notes_file:
            changelog_analysis_status = "ok"
            try:
                notes_text = Path(notes_file).read_text(encoding="utf-8")
                analyzer = ChangelogAnalyzer()
                breaking_change_analysis = analyzer.analyze_release_notes(
                    package_name="manual-input",
                    from_version="unknown",
                    to_version="unknown",
                    notes_text=notes_text,
                )
            except OSError as exc:
                changelog_analysis_status = "error"
                changelog_analysis_error = str(exc)
            except Exception as exc:  # noqa: BLE001
                changelog_analysis_status = "error"
                changelog_analysis_error = str(exc)
        else:
            changelog_analysis_status = "skipped_no_notes_file"

        return {
            "mode": "agent",
            "agent_plan": {
                "strategy": "sequential_tool_orchestration",
                "version": "v2_skeleton",
            },
            "agent_trace": agent_trace,
            "deprecated_api_findings": deprecated_findings,
            "deprecated_risk_summary": deprecated_risk_summary,
            "deprecation_scan_status": deprecation_scan_status,
            "deprecation_scan_error": deprecation_scan_error,
            "breaking_change_analysis": breaking_change_analysis,
            "changelog_analysis_status": changelog_analysis_status,
            "changelog_analysis_error": changelog_analysis_error,
            "report": report.to_dict(),
        }
