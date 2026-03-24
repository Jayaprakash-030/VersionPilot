import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.agent_orchestrator import AgentOrchestrator


class TestAgentOrchestrator(unittest.TestCase):
    def test_agent_mode_includes_deprecated_api_findings_when_repo_path_provided(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_path = Path(tmpdir)
            (repo_path / "sample.py").write_text(
                "from flask.ext import sqlalchemy\n",
                encoding="utf-8",
            )

            orchestrator = AgentOrchestrator()
            result = orchestrator.analyze_repository(
                repo_url="https://github.com/org/repo",
                repo_path=str(repo_path),
            )

            self.assertEqual(result["mode"], "agent")
            self.assertEqual(result["deprecation_scan_status"], "ok")
            self.assertGreaterEqual(len(result["deprecated_api_findings"]), 1)
            summary = result["deprecated_risk_summary"]
            self.assertEqual(summary["total_findings"], len(result["deprecated_api_findings"]))
            self.assertEqual(summary["severity_counts"]["high"], 1)
            self.assertGreaterEqual(len(summary["top_symbols"]), 1)
            self.assertIn("report", result)

    def test_agent_mode_includes_breaking_change_analysis_when_notes_file_provided(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            notes_path = Path(tmpdir) / "notes.txt"
            notes_path.write_text(
                "- BREAKING: Removed old auth hook\n- Deprecated client initialization\n",
                encoding="utf-8",
            )

            orchestrator = AgentOrchestrator()
            result = orchestrator.analyze_repository(
                repo_url="https://github.com/org/repo",
                notes_file=str(notes_path),
            )

            self.assertEqual(result["changelog_analysis_status"], "ok")
            analysis = result["breaking_change_analysis"]
            self.assertEqual(analysis["finding_count"], 2)
            self.assertEqual(analysis["severity_counts"]["high"], 1)
            self.assertEqual(analysis["severity_counts"]["medium"], 1)

    @patch("app.agent_orchestrator.fetch_release_notes")
    def test_agent_mode_auto_fetches_release_notes_when_notes_file_missing(self, mock_fetch) -> None:
        mock_fetch.return_value = "- BREAKING: Removed old hook\n- Deprecated setup path\n"
        orchestrator = AgentOrchestrator()

        result = orchestrator.analyze_repository(
            repo_url="https://github.com/org/repo",
            notes_file=None,
        )

        self.assertEqual(result["changelog_analysis_status"], "ok")
        self.assertEqual(result["changelog_source"], "github_latest_release")
        analysis = result["breaking_change_analysis"]
        self.assertEqual(analysis["finding_count"], 2)


if __name__ == "__main__":
    unittest.main()
